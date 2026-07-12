"""OneBot v11 Bot 客户端:通过 WebSocket 调用 API。"""
import asyncio
import inspect
import json
from typing import Any, List, Optional

from .models import (
    Event,
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)


class ApiError(Exception):
    """OneBot API 调用失败异常。"""

    def __init__(self, action: str, retcode: int, msg: str = "", wording: str = ""):
        self.action = action
        self.retcode = retcode
        self.msg = msg
        self.wording = wording
        super().__init__(f"API '{action}' failed: retcode={retcode}, msg={msg}, wording={wording}")


class Bot:
    """OneBot v11 Bot 客户端。

    WebSocket 连接由外部传入(支持 ``send`` 或 ``send_str`` 接口)。
    """

    def __init__(self, ws, self_id: str, app: Any = None, adapter_type: str = "onebot_v11"):
        self.ws = ws
        self.self_id = self_id
        self.app = app
        self.adapter_type = adapter_type
        self._api_futures = {}  # echo -> Future
        self._echo_counter = 0

    async def _send_json(self, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        sender = getattr(self.ws, "send", None)
        if sender is not None:
            result = sender(text)
            if inspect.isawaitable(result):
                await result
            return
        sender = getattr(self.ws, "send_str", None)
        if sender is not None:
            result = sender(text)
            if inspect.isawaitable(result):
                await result
            return
        raise RuntimeError("WebSocket connection has no send/send_str method")

    async def call_api(self, action: str, **params) -> Any:
        """调用 OneBot API,等待对应 echo 的响应,超时 30 秒。"""
        self._echo_counter += 1
        echo = str(self._echo_counter)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._api_futures[echo] = (future, action)

        payload = {"action": action, "params": params, "echo": echo}
        try:
            await self._send_json(payload)
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            raise TimeoutError(f"API call '{action}' timed out after 30s")
        finally:
            self._api_futures.pop(echo, None)

    def handle_api_response(self, data: dict) -> None:
        """处理收到的 API 响应,根据 echo 找到对应 Future 并 set_result。"""
        echo = data.get("echo")
        if echo is None:
            return
        entry = self._api_futures.pop(echo, None)
        if entry is None:
            return
        future, action = entry
        if future.done():
            return
        retcode = data.get("retcode", 0)
        if retcode == 0:
            future.set_result(data.get("data"))
        else:
            future.set_exception(
                ApiError(
                    action=action,
                    retcode=retcode,
                    msg=data.get("msg", ""),
                    wording=data.get("wording", ""),
                )
            )

    def message_to_onebot(self, message: Any) -> List[dict]:
        """将 str/Message/MessageSegment 转为 OneBot 格式(list of dict)。"""
        if isinstance(message, str):
            return [{"type": "text", "data": {"text": message}}]
        if isinstance(message, MessageSegment):
            return [dict(message)]
        if isinstance(message, Message):
            return [dict(seg) for seg in message]
        if isinstance(message, list):
            result = []
            for seg in message:
                if isinstance(seg, MessageSegment):
                    result.append(dict(seg))
                elif isinstance(seg, dict):
                    result.append(dict(seg))
                elif isinstance(seg, str):
                    result.append({"type": "text", "data": {"text": seg}})
            return result
        if isinstance(message, dict):
            return [dict(message)]
        return [{"type": "text", "data": {"text": str(message)}}]

    async def send(self, event, message: Any) -> Any:
        """根据事件类型自动调用 send_group_msg 或 send_private_msg。"""
        post_type = getattr(event, "post_type", None)
        message_type = getattr(event, "message_type", None)
        group_id = getattr(event, "group_id", None)

        if post_type == "message" and message_type == "group" and group_id:
            return await self.send_group_msg(group_id, message)
        if post_type == "message" and message_type == "private":
            return await self.send_private_msg(event.user_id, message)

        # Fallback: duck typing
        if group_id:
            return await self.send_group_msg(group_id, message)
        user_id = getattr(event, "user_id", None)
        if user_id:
            return await self.send_private_msg(user_id, message)
        raise ValueError("Cannot determine send target from event")

    async def send_group_msg(self, group_id: int, message: Any) -> Any:
        return await self.call_api(
            "send_group_msg",
            group_id=group_id,
            message=self.message_to_onebot(message),
        )

    async def send_private_msg(self, user_id: int, message: Any) -> Any:
        return await self.call_api(
            "send_private_msg",
            user_id=user_id,
            message=self.message_to_onebot(message),
        )

    async def delete_msg(self, message_id: int) -> Any:
        return await self.call_api("delete_msg", message_id=message_id)

    async def get_group_list(self) -> Any:
        return await self.call_api("get_group_list")

    async def get_group_info(self, group_id: int, no_cache: bool = False) -> Any:
        return await self.call_api(
            "get_group_info", group_id=group_id, no_cache=no_cache
        )

    async def get_group_member_list(
        self, group_id: int, no_cache: bool = False
    ) -> Any:
        return await self.call_api(
            "get_group_member_list", group_id=group_id, no_cache=no_cache
        )

    async def get_group_member_info(
        self, group_id: int, user_id: int, no_cache: bool = False
    ) -> Any:
        return await self.call_api(
            "get_group_member_info",
            group_id=group_id,
            user_id=user_id,
            no_cache=no_cache,
        )

    async def get_stranger_info(
        self, user_id: int, no_cache: bool = False
    ) -> Any:
        return await self.call_api(
            "get_stranger_info", user_id=user_id, no_cache=no_cache
        )

    async def get_friend_list(self) -> Any:
        return await self.call_api("get_friend_list")

    async def set_group_whole_ban(self, group_id: int, enable: bool) -> Any:
        return await self.call_api(
            "set_group_whole_ban", group_id=group_id, enable=enable
        )

    async def set_group_ban(
        self, group_id: int, user_id: int, duration: int = 1800
    ) -> Any:
        return await self.call_api(
            "set_group_ban",
            group_id=group_id,
            user_id=user_id,
            duration=duration,
        )

    async def set_group_kick(
        self,
        group_id: int,
        user_id: int,
        reject_add_request: bool = False,
    ) -> Any:
        return await self.call_api(
            "set_group_kick",
            group_id=group_id,
            user_id=user_id,
            reject_add_request=reject_add_request,
        )

    async def set_group_admin(
        self, group_id: int, user_id: int, enable: bool
    ) -> Any:
        return await self.call_api(
            "set_group_admin",
            group_id=group_id,
            user_id=user_id,
            enable=enable,
        )

    async def set_group_leave(self, group_id: int) -> Any:
        return await self.call_api("set_group_leave", group_id=group_id)

    async def send_like(self, user_id: int, times: int = 10) -> Any:
        return await self.call_api("send_like", user_id=user_id, times=times)

    async def set_group_special_title(
        self, group_id: int, user_id: int, special_title: str = ""
    ) -> Any:
        """设置群头衔。"""
        return await self.call_api(
            "set_group_special_title",
            group_id=group_id,
            user_id=user_id,
            special_title=special_title,
        )

    async def set_group_name(self, group_id: int, group_name: str) -> Any:
        """设置群名。"""
        return await self.call_api(
            "set_group_name", group_id=group_id, group_name=group_name
        )

    async def set_group_card(
        self, group_id: int, user_id: int, card: str = ""
    ) -> Any:
        """设置群名片。"""
        return await self.call_api(
            "set_group_card",
            group_id=group_id,
            user_id=user_id,
            card=card,
        )

    async def send_group_notice(
        self, group_id: int, content: str
    ) -> Any:
        """发送群公告。"""
        return await self.call_api(
            "_send_group_notice",
            group_id=group_id,
            content=content,
        )

    async def delete_friend(self, user_id: int) -> Any:
        """删除好友。"""
        return await self.call_api("delete_friend", user_id=user_id)

    async def set_friend_add_request(
        self, flag: str, approve: bool = True, remark: str = ""
    ) -> Any:
        """处理加好友请求。"""
        return await self.call_api(
            "set_friend_add_request",
            flag=flag,
            approve=approve,
            remark=remark,
        )

    async def set_group_add_request(
        self, flag: str, sub_type: str, approve: bool = True
    ) -> Any:
        """处理加群请求。"""
        return await self.call_api(
            "set_group_add_request",
            flag=flag,
            sub_type=sub_type,
            approve=approve,
        )

    async def get_msg(self, message_id: int) -> Any:
        """获取消息。"""
        return await self.call_api("get_msg", message_id=message_id)

    async def get_login_info(self) -> Any:
        """获取登录号信息。"""
        return await self.call_api("get_login_info")

    async def get_image(self, file: str) -> Any:
        """获取图片信息。"""
        return await self.call_api("get_image", file=file)

    async def can_send_image(self) -> Any:
        """检查是否支持发送图片。"""
        return await self.call_api("can_send_image")

    async def can_send_record(self) -> Any:
        """检查是否支持发送语音。"""
        return await self.call_api("can_send_record")

    async def get_status(self) -> Any:
        """获取运行状态。"""
        return await self.call_api("get_status")

    async def get_version_info(self) -> Any:
        """获取版本信息。"""
        return await self.call_api("get_version_info")

    async def reload_event_filter(self) -> Any:
        """重载事件过滤器。"""
        return await self.call_api("reload_event_filter")

    async def set_group_anonymous_ban(
        self,
        group_id: int,
        anonymous: Optional[dict] = None,
        anonymous_flag: str = "",
        duration: int = 1800,
    ) -> Any:
        """禁言匿名成员。"""
        return await self.call_api(
            "set_group_anonymous_ban",
            group_id=group_id,
            anonymous=anonymous or {},
            anonymous_flag=anonymous_flag,
            duration=duration,
        )

    async def set_group_anonymous(
        self, group_id: int, enable: bool
    ) -> Any:
        """设置群匿名。"""
        return await self.call_api(
            "set_group_anonymous", group_id=group_id, enable=enable
        )

    async def set_essence_msg(self, message_id: int) -> Any:
        """设为精华消息。"""
        return await self.call_api(
            "set_essence_msg", message_id=message_id
        )

    async def delete_essence_msg(self, message_id: int) -> Any:
        """移除精华消息。"""
        return await self.call_api(
            "delete_essence_msg", message_id=message_id
        )

    async def get_essence_msg_list(
        self, group_id: int
    ) -> Any:
        """获取群精华消息列表。"""
        return await self.call_api(
            "get_essence_msg_list", group_id=group_id
        )
