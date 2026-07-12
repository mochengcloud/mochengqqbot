"""事件总线:替代 nonebot 的 matcher 工厂与事件分发。

提供 on_message/on_command/on_notice/on_request 工厂函数、Matcher 类,
以及 EventBus 事件分发器。
"""
import contextvars
import inspect
import logging
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Set, Union

from core.onebot.models import (
    Event,
    Message,
    MessageEvent,
    MessageSegment,
    NoticeEvent,
    RequestEvent,
)

logger = logging.getLogger("event_bus")

# 当前协程绑定的 bot/event,用于 Matcher.send 正确路由到触发当前 handler 的事件
# 解决 Matcher 单例在并发 dispatch 下 bot/event 被覆盖导致的串群问题
_current_bot: "contextvars.ContextVar[Any]" = contextvars.ContextVar("current_bot")
_current_event: "contextvars.ContextVar[Any]" = contextvars.ContextVar("current_event")

# 类型别名(兼容 nonebot.typing.T_State)
T_State = Dict[str, Any]


class FinishedException(Exception):
    """当 matcher.finish() 被调用时抛出,用于中断 handler 执行。

    兼容原 nonebot 的 FinishedException 用法。
    """


# 命令参数标记对象(单例),dispatch 时会替换为实际的命令参数
_COMMAND_ARG_MARKER: Any = object()
_ARG_STR_MARKER: Any = object()


def CommandArg() -> Any:
    """在 handler 参数中用作默认值: ``args: Message = CommandArg()``。

    返回一个特殊的标记对象,EventBus.dispatch 时会替换为命令参数(Message 对象)。
    """
    return _COMMAND_ARG_MARKER


def ArgStr() -> Any:
    """类似 CommandArg,但返回纯文本字符串。"""
    return _ARG_STR_MARKER


class Matcher:
    """事件处理器。每个 matcher 对应一个事件处理函数。

    通过 on_message/on_command/on_notice/on_request 工厂函数创建,
    再通过 ``@matcher.handle()`` 装饰器注册 handler。
    """

    def __init__(
        self,
        event_type: str = "message",
        priority: int = 1,
        block: bool = True,
        permission: Optional[Callable] = None,
        cmd: Optional[Union[str, List[str]]] = None,
        aliases: Optional[Set[str]] = None,
        rule: Optional[Callable] = None,
    ):
        self.handler: Optional[Callable] = None
        self.priority: int = priority
        self.block: bool = block
        self.permission: Optional[Callable] = permission
        self.cmd: Optional[Union[str, List[str]]] = cmd
        self.aliases: Set[str] = aliases or set()
        self.event_type: str = event_type
        self.rule: Optional[Callable] = rule

        # 运行时上下文(handler 调用前由 dispatch 设置)
        self.bot: Any = None
        self.event: Any = None
        self._stopped: bool = False

    # ----- 装饰器 -----

    def handle(self) -> Callable[[Callable], Callable]:
        """装饰器:注册 handler 函数,返回函数本身。"""

        def decorator(func: Callable) -> Callable:
            self.handler = func
            return func

        return decorator

    def got(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
        """装饰器(简化实现,只需保存 handler 即可)。"""

        def decorator(func: Callable) -> Callable:
            self.handler = func
            return func

        return decorator

    # ----- handler 内调用的实例方法 -----

    async def send(self, message: Any) -> Any:
        """通过当前 bot/event 发送消息。

        优先使用 ContextVar 中绑定的 bot/event(由 dispatch 设置),
        确保 handler 内 await 期间即使单例属性被并发覆盖,仍路由到正确的事件目标。
        fallback 到 self.bot/self.event 以兼容未走 dispatch 的调用。

        message 可为 str/Message/MessageSegment。
        GroupMessageEvent 调 send_group_msg,PrivateMessageEvent 调 send_private_msg
        (由 Bot.send 内部判断)。
        """
        try:
            bot = _current_bot.get()
        except LookupError:
            bot = self.bot
        try:
            event = _current_event.get()
        except LookupError:
            event = self.event
        if bot is None or event is None:
            raise RuntimeError(
                "Matcher has no bot/event context; "
                "send() must be called within handler"
            )
        return await bot.send(event, message)

    async def finish(self, message: Any = None) -> None:
        """如果 message 不为 None,先 send(message),然后抛出 FinishedException。"""
        if message is not None:
            await self.send(message)
        raise FinishedException()

    async def reject(self, message: Any = None) -> None:
        """简化实现:发送消息(如有)并抛出 FinishedException。"""
        if message is not None:
            await self.send(message)
        raise FinishedException()

    async def pause(self, message: Any = None) -> None:
        """简化实现:发送消息(如有)并抛出 FinishedException。"""
        if message is not None:
            await self.send(message)
        raise FinishedException()

    def get_plaintext(self) -> str:
        """返回 event 的纯文本。"""
        if self.event is None:
            return ""
        getter = getattr(self.event, "get_plaintext", None)
        if getter is not None:
            return getter()
        return ""

    def stop(self) -> None:
        """设置标志,停止后续 matcher 执行(等同 block)。"""
        self._stopped = True

    async def __call__(self, **kwargs: Any) -> Any:
        """调用 handler,将 kwargs 传入。"""
        if self.handler is None:
            raise RuntimeError("Matcher has no handler registered")
        return await self.handler(**kwargs)


# MatcherPersistence 是 Matcher 的别名,支持 @matcher.handle() 装饰器语法
MatcherPersistence = Matcher


def _get_command_start() -> List[str]:
    """从 config_manager 获取 command_start,默认 ``[""]``。"""
    try:
        from config_manager import config_manager

        starts = config_manager.get_bot_config().get("command_start", [""])
        if isinstance(starts, list) and starts:
            return [str(s) for s in starts]
    except Exception:
        pass
    return [""]


# ----- 工厂函数 -----


def on_message(
    priority: int = 1,
    block: bool = True,
    permission: Optional[Callable] = None,
    rule: Optional[Callable] = None,
) -> Matcher:
    """注册消息事件处理器。返回 Matcher 对象。

    用法::

        matcher = on_message(priority=0, block=False)

        @matcher.handle()
        async def handler(bot, event):
            ...
    """
    matcher = Matcher(
        event_type="message",
        priority=priority,
        block=block,
        permission=permission,
        rule=rule,
    )
    _event_bus.register(matcher)
    return matcher


def on_command(
    cmd: Union[str, List[str]],
    priority: int = 1,
    block: bool = True,
    permission: Optional[Callable] = None,
    aliases: Optional[Union[Set[str], List[str]]] = None,
    rule: Optional[Callable] = None,
) -> Matcher:
    """注册命令事件处理器。

    Args:
        cmd: 命令名(str)或命令名列表。
        priority: 优先级(越小越先执行)。
        block: 是否阻止后续 matcher 执行。
        permission: 权限检查函数或 Permission 对象。
        aliases: 命令别名集合(set 或 list)。
        rule: 规则检查(仅存储,不强制执行)。
    """
    # 规范化 aliases 为 set
    alias_set: Set[str] = set()
    if aliases:
        if isinstance(aliases, (set, list)):
            alias_set = set(aliases)
        else:
            alias_set = {aliases}

    matcher = Matcher(
        event_type="command",
        priority=priority,
        block=block,
        permission=permission,
        cmd=cmd,
        aliases=alias_set,
        rule=rule,
    )
    _event_bus.register(matcher)
    return matcher


def on_notice(
    priority: int = 1,
    block: bool = True,
    permission: Optional[Callable] = None,
    rule: Optional[Callable] = None,
) -> Matcher:
    """注册通知事件处理器。"""
    matcher = Matcher(
        event_type="notice",
        priority=priority,
        block=block,
        permission=permission,
        rule=rule,
    )
    _event_bus.register(matcher)
    return matcher


def on_request(
    priority: int = 1,
    block: bool = True,
    permission: Optional[Callable] = None,
    rule: Optional[Callable] = None,
) -> Matcher:
    """注册请求事件处理器。"""
    matcher = Matcher(
        event_type="request",
        priority=priority,
        block=block,
        permission=permission,
        rule=rule,
    )
    _event_bus.register(matcher)
    return matcher


class EventBus:
    """事件总线:管理所有 matcher 并提供事件分发。"""

    def __init__(self) -> None:
        self._matchers: List[Matcher] = []
        self._api_warn_cache: Dict[str, float] = {}

    def register(self, matcher: Matcher) -> None:
        """注册 matcher。"""
        self._matchers.append(matcher)

    def _warn_api_error(self, error: Exception) -> None:
        key = f"{getattr(error, 'action', '')}:{getattr(error, 'retcode', '')}:{getattr(error, 'wording', '')}"
        now = time.time()
        last = self._api_warn_cache.get(key, 0)
        if now - last < 60:
            return
        self._api_warn_cache[key] = now
        logger.warning(
            f"API '{getattr(error, 'action', '')}' failed: "
            f"retcode={getattr(error, 'retcode', '')}, "
            f"wording={getattr(error, 'wording', '')}"
        )

    # ----- 内部辅助方法 -----

    def _match_command(
        self,
        event: MessageEvent,
        matcher: Matcher,
        command_starts: List[str],
    ) -> Optional[tuple]:
        """检查消息是否匹配命令名。

        Returns:
            (cmd_name, args_text) 或 None。
        """
        text = event.get_plaintext()
        if not text:
            return None
        text = text.strip()
        if not text:
            return None

        # 收集所有可接受的命令名
        cmd_names: List[str] = []
        if matcher.cmd:
            if isinstance(matcher.cmd, str):
                cmd_names.append(matcher.cmd)
            else:
                cmd_names.extend(matcher.cmd)
        cmd_names.extend(matcher.aliases)

        if not cmd_names:
            return None

        for start in command_starts:
            if start:
                if not text.startswith(start):
                    continue
                rest = text[len(start):]
            else:
                rest = text

            # 提取第一个词作为命令名,剩余作为参数
            parts = rest.split(maxsplit=1)
            if not parts:
                continue
            cmd_text = parts[0]
            args_text = parts[1] if len(parts) > 1 else ""

            if cmd_text in cmd_names:
                return (cmd_text, args_text)

        return None

    def _build_args_message(
        self,
        event: MessageEvent,
        args_text: str,
    ) -> Message:
        """构建命令参数 Message:文本部分 + 原始消息中的非文本段。"""
        args_msg = Message()
        if args_text:
            args_msg.append(MessageSegment.text(args_text))
        # 附加原始消息中的非文本段(如图片等)
        for seg in event.message:
            if seg.type != "text":
                args_msg.append(seg)
        return args_msg

    def _build_kwargs(
        self,
        handler: Callable,
        bot: Any,
        event: Event,
        matcher: Matcher,
        cmd_args: Optional[Message],
    ) -> Dict[str, Any]:
        """根据 handler 参数签名构建调用参数。

        - 名为 "bot" → 传入 bot 实例
        - 名为 "event" → 传入 event 对象
        - 名为 "matcher" → 传入 matcher 实例
        - 默认值为 _COMMAND_ARG_MARKER → 传入命令参数 Message
        - 默认值为 _ARG_STR_MARKER → 传入命令参数纯文本
        - 名为 "state" → 传入空 dict {}
        - 其他 → 跳过(使用默认值)
        """
        kwargs: Dict[str, Any] = {}
        try:
            sig = inspect.signature(handler)
        except (ValueError, TypeError):
            return kwargs

        for name, param in sig.parameters.items():
            if name == "bot":
                kwargs["bot"] = bot
            elif name == "event":
                kwargs["event"] = event
            elif name == "matcher":
                kwargs["matcher"] = matcher
            elif param.default is _COMMAND_ARG_MARKER:
                kwargs[name] = cmd_args if cmd_args is not None else Message()
            elif param.default is _ARG_STR_MARKER:
                if cmd_args is not None:
                    kwargs[name] = cmd_args.extract_plain_text()
                else:
                    kwargs[name] = ""
            elif name == "state":
                kwargs["state"] = {}
            # 其他参数:跳过(让 handler 使用其默认值)

        return kwargs

    # ----- 事件分发 -----

    async def dispatch(self, bot: Any, event: Event) -> None:
        """分发事件到所有匹配的 matcher。

        1. 根据 event 类型筛选 matcher
        2. 对 on_command 的 matcher 检查命令名匹配
        3. 按 priority 从小到大排序
        4. 依次调用:检查 permission → 设置上下文 → 调用 handler
           - FinishedException:捕获并停止后续
           - block==True 且正常完成:停止后续
        """
        # 1. 根据事件类型筛选
        post_type = getattr(event, "post_type", None)
        if post_type == "message":
            event_types = ("message", "command")
        elif post_type == "notice":
            event_types = ("notice",)
        elif post_type == "request":
            event_types = ("request",)
        else:
            return

        # 消息事件接收日志(便于排查事件是否到达 dispatch)
        if post_type == "message":
            adapter_type = getattr(bot, "adapter_type", "onebot_v11")
            msg_type = getattr(event, "message_type", "?")
            gid = getattr(event, "group_id", "-")
            uid = getattr(event, "user_id", "?")
            raw = getattr(event, "raw_message", "") or ""
            if isinstance(raw, str):
                raw = raw[:50]
            logger.info(
                f"[消息] 适配器={adapter_type} 类型={msg_type} 群={gid} 用户={uid} 内容={raw!r}"
            )

        # 获取 command_start(仅消息事件需要)
        command_starts = _get_command_start() if "command" in event_types else []

        # 2. 收集匹配的 matcher
        matched: List[tuple] = []  # (matcher, cmd_args, cmd_name)
        # 统计命令匹配情况(诊断用)
        cmd_match_count = 0
        cmd_total = 0
        for matcher in self._matchers:
            if matcher.event_type not in event_types:
                continue

            cmd_args: Optional[Message] = None
            cmd_name: Optional[str] = None

            # 命令匹配
            if matcher.event_type == "command":
                cmd_total += 1
                result = self._match_command(event, matcher, command_starts)
                if result is None:
                    continue
                cmd_name, args_text = result
                cmd_args = self._build_args_message(event, args_text)
                cmd_match_count += 1

            matched.append((matcher, cmd_args, cmd_name))

        # 命令匹配诊断:如果有命令但没匹配上,输出详情
        if cmd_total > 0 and cmd_match_count == 0:
            text = event.get_plaintext().strip()[:50] if event.get_plaintext() else ""
            logger.info(
                f"[命令] 未匹配 消息={text!r} 命令总数={cmd_total} "
                f"command_starts={command_starts}"
            )

        if not matched:
            return

        # 3. 按 priority 从小到大排序
        matched.sort(key=lambda x: x[0].priority)

        # 4. 依次调用
        for matcher, cmd_args, cmd_name in matched:
            # 设置 _matched_cmd
            if cmd_name is not None:
                try:
                    event._matched_cmd = cmd_name
                except Exception:
                    pass

            # 检查 permission
            if matcher.permission is not None:
                try:
                    permitted = await matcher.permission(bot, event)
                except Exception as e:
                    permitted = False
                    logger.warning(f"[权限] 检查异常 cmd={cmd_name} error={e}")
                if not permitted:
                    if cmd_name is not None:
                        adapter_type = getattr(bot, "adapter_type", "onebot_v11")
                        uid = getattr(event, "user_id", "?")
                        logger.info(
                            f"[权限] 拒绝 cmd={cmd_name} 用户={uid} 适配器={adapter_type}"
                        )
                    continue

            # 跳过未注册 handler 的 matcher
            if matcher.handler is None:
                continue

            # 设置运行时上下文
            matcher.bot = bot
            matcher.event = event
            matcher._stopped = False

            # 构建 handler 参数
            kwargs = self._build_kwargs(
                matcher.handler, bot, event, matcher, cmd_args
            )

            if cmd_name is not None:
                adapter_type = getattr(bot, "adapter_type", "onebot_v11")
                logger.info(f"[命令] {cmd_name} | 用户={getattr(event, 'user_id', '?')} 群={getattr(event, 'group_id', '-')} | 适配器={adapter_type}")
            # 调用 handler
            # 绑定当前 bot/event 到 ContextVar,防止并发 dispatch 覆盖单例属性导致串群
            bot_token = _current_bot.set(bot)
            event_token = _current_event.set(event)
            try:
                await matcher.handler(**kwargs)
            except FinishedException:
                _current_bot.reset(bot_token)
                _current_event.reset(event_token)
                break
            except Exception as e:
                _current_bot.reset(bot_token)
                _current_event.reset(event_token)
                # API 错误简洁输出,其他错误打印完整 traceback
                from core.onebot.bot import ApiError
                if isinstance(e, ApiError):
                    self._warn_api_error(e)
                else:
                    logger.error(f"Handler error: {e}", exc_info=True)
                continue
            else:
                _current_bot.reset(bot_token)
                _current_event.reset(event_token)

            # 检查 block / stop(仅 handler 正常执行完毕时)
            if matcher._stopped or matcher.block:
                break


# 全局 EventBus 单例
_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例。"""
    return _event_bus


def register(matcher: Matcher) -> None:
    """注册 matcher 到全局 EventBus。"""
    _event_bus.register(matcher)


async def dispatch(bot: Any, event: Event) -> None:
    """分发事件到全局 EventBus。"""
    await _event_bus.dispatch(bot, event)
