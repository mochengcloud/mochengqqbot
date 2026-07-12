"""插件共享工具函数。

所有插件应优先使用本模块提供的函数进行消息构造,保证输出格式统一。
"""
import os
import json
import threading
from pathlib import Path
from typing import Any, Optional

from core.onebot import (
    GroupMessageEvent,
    PrivateMessageEvent,
    Message,
    MessageSegment,
    MessageEvent,
)


# ============ 消息构造 ============

def reply_msg(event: GroupMessageEvent, msg) -> Message:
    """群消息回复:引用 + @用户 + 内容。

    参数:
        event: 群消息事件
        msg: 文本字符串 / MessageSegment / Message
    """
    result = Message()
    result.append(MessageSegment.reply(event.message_id))
    result.append(MessageSegment.at(event.user_id))
    _append_content(result, msg)
    return result


def reply_private(event: PrivateMessageEvent, msg) -> Message:
    """私聊消息回复:仅内容(无私聊引用)。"""
    result = Message()
    _append_content(result, msg)
    return result


def reply(event: MessageEvent, msg) -> Message:
    """通用回复:自动识别群/私聊事件,选择对应的回复格式。

    参数:
        event: 消息事件(群或私聊)
        msg: 文本字符串 / MessageSegment / Message
    """
    if isinstance(event, GroupMessageEvent):
        return reply_msg(event, msg)
    if isinstance(event, PrivateMessageEvent):
        return reply_private(event, msg)
    # 兜底:按是否有 group_id 判断
    if getattr(event, "group_id", None):
        return reply_msg(event, msg)  # type: ignore
    return reply_private(event, msg)  # type: ignore


def at_msg(user_id: int, msg) -> Message:
    """@用户 + 内容(无引用,适用于通知场景)。"""
    result = Message()
    result.append(MessageSegment.at(user_id))
    _append_content(result, msg)
    return result


def text_msg(text: str) -> Message:
    """纯文本消息。"""
    return Message(MessageSegment.text(text))


def _append_content(result: Message, msg) -> None:
    """将 msg 追加到 result Message 中。"""
    if isinstance(msg, Message):
        result.extend(msg)
    elif isinstance(msg, MessageSegment):
        result.append(msg)
    else:
        result.append(MessageSegment.text(str(msg)))


# ============ 消息段构造快捷方法 ============

def at(user_id: int) -> MessageSegment:
    """@某人。"""
    return MessageSegment.at(user_id)


def reply_segment(message_id: int) -> MessageSegment:
    """引用回复段。"""
    return MessageSegment.reply(message_id)


def image(url: str = "", file: str = "", path: str = "", base64: str = "") -> MessageSegment:
    """图片消息段。

    参数任选其一:
        url: 图片 URL
        file: 图片文件名(需协议端支持)
        path: 图片本地路径(需协议端支持)
        base64: Base64 编码(不含 data:image 前缀)
    """
    if base64:
        return MessageSegment.image(f"base64://{base64}")
    if url:
        return MessageSegment.image(url)
    if file:
        return MessageSegment.image(f"file://{file}")
    if path:
        return MessageSegment.image(f"file://{path}")
    raise ValueError("image() 需要提供 url / file / path / base64 之一")


def face(face_id: int) -> MessageSegment:
    """QQ 表情。"""
    return MessageSegment.face(face_id)


def record(url: str = "", file: str = "", base64: str = "") -> MessageSegment:
    """语音消息。"""
    if base64:
        return MessageSegment.record(f"base64://{base64}")
    if url:
        return MessageSegment.record(url)
    if file:
        return MessageSegment.record(f"file://{file}")
    raise ValueError("record() 需要提供 url / file / base64 之一")


# ============ JSON 数据管理基类 ============

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "data",
)


class JsonDataManager:
    """JSON 文件数据管理基类。

    提供懒加载、线程安全、延迟保存、阈值保存功能。
    子类只需设置 ``self.data`` 为具体数据结构即可。

    用法::

        class MyDataManager(JsonDataManager):
            def __init__(self):
                super().__init__("my_plugin.json", default_data={})

        mgr = MyDataManager()
        mgr.data["key"] = "value"
        mgr.mark_dirty()  # 标记需要保存
    """

    def __init__(
        self,
        filename: str,
        default_data: Any = None,
        data_dir: Optional[str] = None,
        save_delay: float = 3.0,
        save_threshold: int = 30,
    ):
        """
        参数:
            filename: 数据文件名(如 "checkin_data.json")
            default_data: 默认数据(文件不存在或解析失败时使用)
            data_dir: 数据目录,默认为 config/data/
            save_delay: 延迟保存秒数
            save_threshold: 脏操作次数阈值,达到后立即保存
        """
        if data_dir is None:
            data_dir = _DATA_DIR
        self.data_path = Path(os.path.join(data_dir, filename))
        self._default_data = default_data if default_data is not None else {}
        self._lock = threading.Lock()
        self._dirty = False
        self._dirty_count = 0
        self._save_delay = save_delay
        self._save_threshold = save_threshold
        self._save_timer: Optional[threading.Timer] = None
        self._loaded = False
        self.data: Any = self._default_data

    def load(self) -> Any:
        """加载数据(懒加载,首次调用时读取文件)。"""
        with self._lock:
            if self._loaded:
                return self.data
            try:
                if self.data_path.exists():
                    with open(self.data_path, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = self._default_data
            self._loaded = True
            return self.data

    def save(self) -> None:
        """立即保存数据到文件。"""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            try:
                self.data_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                self._dirty = False
                self._dirty_count = 0
            except OSError:
                pass

    def mark_dirty(self) -> None:
        """标记数据已修改,触发延迟保存。"""
        with self._lock:
            self._dirty = True
            self._dirty_count += 1
            if self._dirty_count >= self._save_threshold:
                # 达到阈值,立即保存(在新线程中异步执行)
                if self._save_timer is not None:
                    self._save_timer.cancel()
                    self._save_timer = None
                threading.Thread(target=self._save_sync, daemon=True).start()
            elif self._save_timer is None:
                self._save_timer = threading.Timer(
                    self._save_delay, self._save_sync
                )
                self._save_timer.daemon = True
                self._save_timer.start()

    def _save_sync(self) -> None:
        """同步保存(线程安全内部方法)。"""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            try:
                self.data_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                self._dirty = False
                self._dirty_count = 0
            except OSError:
                pass

    def shutdown(self) -> None:
        """关闭时强制保存(在 on_shutdown 钩子中调用)。"""
        if self._dirty:
            self.save()


def get_data_dir() -> str:
    """获取插件数据目录(config/data/),确保目录存在。"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    return _DATA_DIR
