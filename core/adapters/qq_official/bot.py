"""QQ 官方机器人 Bot 实现:提供与 OneBot Bot 同名方法,内部转译为官方 API。

官方消息发送接口:
  POST /v2/groups/{group_openid}/messages  群消息
  POST /v2/users/{openid}/messages         C2C 私聊消息

msg_type 取值(官方):
  0 文本消息
  2 markdown
  3 ark
  4 embed
  7 media 富媒体(图片)

被动回复限制:
  - 群聊:5 分钟有效,每条消息最多回复 5 次
  - 单聊:60 分钟有效,每条消息最多回复 4 次
  - msg_id + msg_seq 联合去重,相同组合重复发送会失败
"""
import logging
import itertools
from typing import Any, Dict

from core.onebot.models import Message, MessageSegment

logger = logging.getLogger("qq_official_bot")


class QQOfficialBot:
    """QQ 官方机器人 Bot 客户端。

    提供与 OneBot v11 Bot 同名的方法签名(send/send_group_msg/send_private_msg 等),
    内部转译为官方 HTTPS API 调用。不支持的 API 抛 NotImplementedError。
    """

    adapter_type = "qq_official"

    def __init__(self, client, self_id: str, app: Any = None):
        """
        Args:
            client: QQOfficialClient 实例
            self_id: 机器人 AppID(作为 self_id)
        """
        self.client = client
        self.self_id = str(self_id)
        self.app = app
        # 每个 msg_id 对应一个递增序号生成器,避免相同 msg_id+msg_seq 重复发送被拒
        self._msg_seq_counters: Dict[str, Any] = {}

    def _next_msg_seq(self, msg_id: str) -> int:
        """为指定 msg_id 生成下一个递增 msg_seq(从 1 开始)。

        官方规则:相同的 msg_id + msg_seq 重复发送会失败。
        所以对同一 msg_id 多次回复时,msg_seq 必须递增。
        """
        if msg_id not in self._msg_seq_counters:
            self._msg_seq_counters[msg_id] = itertools.count(1)
        return next(self._msg_seq_counters[msg_id])

    async def send(self, event, message: Any) -> Any:
        """根据事件类型自动调 send_group_msg 或 send_private_msg。"""
        message_type = getattr(event, "message_type", None)
        group_id = getattr(event, "group_id", None)
        if message_type == "group" and group_id:
            # 官方回复群消息需带 msg_id(被动回复)
            msg_id = getattr(event, "message_id", "")
            return await self.send_group_msg(group_id, message, msg_id=msg_id)
        if message_type == "private":
            msg_id = getattr(event, "message_id", "")
            return await self.send_private_msg(event.user_id, message, msg_id=msg_id)
        raise ValueError("Cannot determine send target from event")

    def _convert_message(self, message: Any) -> dict:
        """将 OneBot 风格 message 转译为官方消息体。

        返回 dict,可能包含字段:
          - msg_type: int (0=文本, 2=markdown, 3=ark, 7=media)
          - content: str
          - markdown: dict
          - ark: dict
          - image: str (图片 URL,需以 msg_type=7 + media 方式发送)

        优先级: ark(3) > markdown(2) > image(7) > text(0)
        """
        if isinstance(message, str):
            return {"msg_type": 0, "content": message}
        if isinstance(message, MessageSegment):
            message = Message([message])
        if not isinstance(message, Message):
            message = Message(message)

        content_parts = []
        image_url = None
        ark_data = None
        markdown_data = None
        for seg in message:
            if seg.type == "text":
                content_parts.append(seg.data.get("text", ""))
            elif seg.type == "at":
                # 官方 @ 用户需用 markdown 的 <@userid> 标签,纯文本 @ 无效,跳过
                pass
            elif seg.type == "image":
                url = seg.data.get("file") or seg.data.get("url", "")
                if url:
                    image_url = url
            elif seg.type == "ark":
                ark_data = {
                    "template_id": seg.data.get("template_id"),
                    "kv": seg.data.get("kv", []),
                }
            elif seg.type == "markdown":
                markdown_data = {"content": seg.data.get("content", "")}

        content = "".join(content_parts)
        # 优先级: ark > markdown > image(media) > text
        if ark_data is not None:
            return {"msg_type": 3, "content": content, "ark": ark_data}
        if markdown_data is not None:
            return {"msg_type": 2, "content": content, "markdown": markdown_data}
        if image_url:
            # 图片使用 msg_type=7 (media),content 可同时携带文本
            return {"msg_type": 7, "content": content, "image": image_url}
        return {"msg_type": 0, "content": content}

    def _build_payload(self, body: dict, msg_id: str = "") -> dict:
        """根据消息体构造官方 API 请求 payload。

        Args:
            body: _convert_message 返回的 dict
            msg_id: 被动回复时携带的原消息 ID,空则主动消息
        """
        payload: Dict[str, Any] = {
            "content": body.get("content", ""),
            "msg_type": body.get("msg_type", 0),
        }
        # 被动回复需带 msg_id;相同 msg_id+msg_seq 会重复,需递增 msg_seq
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = self._next_msg_seq(msg_id)
        # 附加类型特定字段
        if body.get("image"):
            # 官方 media 字段:file_info 为 JSON 字符串
            # 简化:直接用 URL 作为 file_info,由官方拉取
            # 正式做法应先调 /files 接口上传获取 file_uuid,这里用简化方式
            payload["media"] = {"file_info": body["image"]}
        if body.get("ark"):
            payload["ark"] = body["ark"]
        if body.get("markdown"):
            payload["markdown"] = body["markdown"]
        return payload

    async def send_group_msg(self, group_id: str, message: Any, msg_id: str = "") -> Any:
        """发送群消息。group_id 这里是官方的 group_openid。

        Args:
            group_id: 群 openid
            message: 消息内容(str/Message/MessageSegment)
            msg_id: 被动回复时携带的原消息 ID(5 分钟有效,最多 5 次)
        """
        body = self._convert_message(message)
        payload = self._build_payload(body, msg_id)
        return await self.client.call_api(
            "POST", f"/v2/groups/{group_id}/messages", json=payload
        )

    async def send_private_msg(self, user_id: str, message: Any, msg_id: str = "") -> Any:
        """发送 C2C 私聊消息。user_id 这里是 user_openid。

        Args:
            user_id: 用户 openid
            message: 消息内容
            msg_id: 被动回复时携带的原消息 ID(60 分钟有效,最多 4 次)
        """
        body = self._convert_message(message)
        payload = self._build_payload(body, msg_id)
        return await self.client.call_api(
            "POST", f"/v2/users/{user_id}/messages", json=payload
        )

    async def get_login_info(self) -> Any:
        """获取登录信息(本地返回,不调用 API)。

        webui /api/status 接口会调用此方法,直接返回本地信息即可。
        """
        return {
            "user_id": self.self_id,
            "nickname": f"QQ官方Bot-{self.self_id}",
        }

    async def delete_msg(self, message_id: str) -> Any:
        """撤回消息(官方:删除群消息)。"""
        raise NotImplementedError("QQ 官方适配器暂不支持撤回消息")

    async def get_group_list(self) -> Any:
        """获取群列表。官方适配器暂不支持。"""
        raise NotImplementedError("QQ 官方适配器不支持 get_group_list,请通过事件回调获取 group_openid")

    async def get_group_info(self, group_id: str, no_cache: bool = False) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 get_group_info")

    async def get_group_member_list(self, group_id: str, no_cache: bool = False) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 get_group_member_list")

    async def get_group_member_info(self, group_id: str, user_id: str, no_cache: bool = False) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 get_group_member_info")

    async def get_stranger_info(self, user_id: str, no_cache: bool = False) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 get_stranger_info")

    async def get_friend_list(self) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 get_friend_list")

    async def set_group_whole_ban(self, group_id: str, enable: bool) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_whole_ban")

    async def set_group_ban(self, group_id: str, user_id: str, duration: int = 1800) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_ban")

    async def set_group_kick(self, group_id: str, user_id: str, reject_add_request: bool = False) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_kick")

    async def set_group_admin(self, group_id: str, user_id: str, enable: bool) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_admin")

    async def set_group_leave(self, group_id: str) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_leave")

    async def send_like(self, user_id: str, times: int = 10) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 send_like")

    async def set_group_special_title(self, group_id: str, user_id: str, special_title: str = "") -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_special_title")

    async def set_group_name(self, group_id: str, group_name: str) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_name")

    async def set_group_card(self, group_id: str, user_id: str, card: str = "") -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_group_card")

    async def send_group_notice(self, group_id: str, content: str) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 send_group_notice")

    async def delete_friend(self, user_id: str) -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 delete_friend")

    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> Any:
        raise NotImplementedError("QQ 官方适配器不支持 set_friend_add_request")

    async def call_api(self, action: str, **params) -> Any:
        """通用 API 调用入口(用于兼容)。官方适配器大部分 API 不支持。"""
        raise NotImplementedError(f"QQ 官方适配器不支持 API: {action}")
