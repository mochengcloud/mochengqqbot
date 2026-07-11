"""OneBot v11 协议类型:消息段、消息与事件。"""
import re
from typing import Any, Dict, List, Optional, Union


class MessageSegment(dict):
    """OneBot v11 消息段。

    dict-like 对象,同时提供 ``type`` / ``data`` 属性访问。
    序列化后即为 OneBot 标准的 ``{"type": ..., "data": {...}}`` 结构。
    """

    def __init__(self, type: str, data: Optional[Dict[str, Any]] = None):
        super().__init__()
        self["type"] = type
        self["data"] = data or {}

    @property
    def type(self) -> str:
        return self["type"]

    @type.setter
    def type(self, value: str) -> None:
        self["type"] = value

    @property
    def data(self) -> Dict[str, Any]:
        return self["data"]

    @data.setter
    def data(self, value: Dict[str, Any]) -> None:
        self["data"] = value

    @classmethod
    def text(cls, text: str) -> "MessageSegment":
        return cls("text", {"text": text})

    @classmethod
    def at(cls, user_id: int) -> "MessageSegment":
        return cls("at", {"qq": str(user_id)})

    @classmethod
    def reply(cls, message_id: int) -> "MessageSegment":
        return cls("reply", {"id": str(message_id)})

    @classmethod
    def image(cls, file: str) -> "MessageSegment":
        return cls("image", {"file": file})

    @classmethod
    def face(cls, face_id: int) -> "MessageSegment":
        return cls("face", {"id": str(face_id)})

    def __str__(self) -> str:
        if self.type == "text":
            return self.data.get("text", "")
        return ""

    def __or__(self, other: Any) -> "Message":
        return Message(self).__or__(other)

    def __ror__(self, other: Any) -> "Message":
        return Message(other).__or__(self)

    def __repr__(self) -> str:
        return f"MessageSegment(type={self.type!r}, data={self.data!r})"


class Message(list):
    """消息段集合,继承自 ``list[MessageSegment]``。"""

    # CQ 码正则: [CQ:type,key=value,key=value]
    _CQ_PATTERN = re.compile(r"\[CQ:(\w+)((?:,[^,\]]+=[^\]]*)*)\]")

    @staticmethod
    def _unescape_cq(text: str) -> str:
        """反转义 CQ 码特殊字符。"""
        return (
            text.replace("&#44;", ",")
                .replace("&#91;", "[")
                .replace("&#93;", "]")
                .replace("&amp;", "&")
        )

    @classmethod
    def _parse_cq_string(cls, text: str) -> List[MessageSegment]:
        """解析包含 CQ 码的字符串,返回消息段列表。"""
        segments: List[MessageSegment] = []
        last_end = 0

        for match in cls._CQ_PATTERN.finditer(text):
            # CQ 码之前的纯文本
            if match.start() > last_end:
                segments.append(MessageSegment.text(text[last_end:match.start()]))

            cq_type = match.group(1)
            params_str = match.group(2)

            # 解析参数
            data: Dict[str, str] = {}
            if params_str:
                for param in params_str.split(",")[1:]:  # 跳过第一个空字符串
                    if "=" in param:
                        key, value = param.split("=", 1)
                        data[key.strip()] = cls._unescape_cq(value)

            segments.append(MessageSegment(cq_type, data))
            last_end = match.end()

        # 末尾纯文本
        if last_end < len(text):
            segments.append(MessageSegment.text(text[last_end:]))

        return segments

    def __init__(self, message: Any = None):
        super().__init__()
        for seg in self._collect(message):
            list.append(self, seg)

    @classmethod
    def _collect(cls, message: Any) -> List[MessageSegment]:
        """将 str/MessageSegment/list/Message/dict 统一规整为段列表。

        字符串中的 CQ 码(如 ``[CQ:at,qq=12345]``)会被自动解析。
        """
        segments: List[MessageSegment] = []
        if message is None:
            return segments
        if isinstance(message, str):
            segments.extend(cls._parse_cq_string(message))
        elif isinstance(message, MessageSegment):
            segments.append(message)
        elif isinstance(message, (list, Message)):
            for seg in message:
                if isinstance(seg, MessageSegment):
                    segments.append(seg)
                elif isinstance(seg, dict):
                    segments.append(MessageSegment(seg.get("type"), seg.get("data", {})))
                elif isinstance(seg, str):
                    segments.extend(cls._parse_cq_string(seg))
        elif isinstance(message, dict):
            segments.append(MessageSegment(message.get("type"), message.get("data", {})))
        else:
            segments.append(MessageSegment.text(str(message)))
        return segments

    def __str__(self) -> str:
        return "".join(str(seg) for seg in self)

    def __add__(self, other: Any) -> "Message":
        result = Message()
        for seg in self:
            list.append(result, seg)
        for seg in self._collect(other):
            list.append(result, seg)
        return result

    def __radd__(self, other: Any) -> "Message":
        result = Message()
        for seg in self._collect(other):
            list.append(result, seg)
        for seg in self:
            list.append(result, seg)
        return result

    def __or__(self, other: Any) -> "Message":
        return self.__add__(other)

    def __ror__(self, other: Any) -> "Message":
        return self.__radd__(other)

    def __getitem__(self, index):  # type: ignore[override]
        if isinstance(index, slice):
            return Message(list.__getitem__(self, index))
        return list.__getitem__(self, index)

    def append(self, obj: Any) -> "Message":
        for seg in self._collect(obj):
            list.append(self, seg)
        return self

    def extend(self, obj: Any) -> "Message":
        for seg in self._collect(obj):
            list.append(self, seg)
        return self

    def extract_plain_text(self) -> str:
        return "".join(
            seg.data.get("text", "") for seg in self if seg.type == "text"
        )

    @classmethod
    def log_message(cls, message: "Message") -> None:
        """记录消息日志的钩子,默认空实现。"""
        return None


class Sender(dict):
    """消息发送者信息。

    dict-like 对象,同时支持属性访问(如 ``sender.nickname``)。
    OneBot v11 中 sender 通常包含 nickname/card/role/sex/age/area/level/title 等。
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class Event:
    """基础事件,从原始 JSON dict 构造。"""

    def __init__(self, raw: dict):
        self._raw = raw
        self.post_type = raw.get("post_type")
        self.time = raw.get("time")
        self.self_id = raw.get("self_id")


class MessageEvent(Event):
    """消息事件基类。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.message_type = raw.get("message_type")
        self.sub_type = raw.get("sub_type")
        self.user_id = raw.get("user_id")
        self.message_id = raw.get("message_id")
        self.message = Message(raw.get("message"))
        self.raw_message = raw.get("raw_message", "")
        self.sender = Sender(raw.get("sender", {}) or {})
        self.font = raw.get("font")
        self.group_id = raw.get("group_id")

    def get_plaintext(self) -> str:
        return self.message.extract_plain_text()

    @property
    def to_me(self) -> bool:
        """消息是否@了机器人或发往机器人私聊。

        优先使用 OneBot 实现提供的 to_me 字段,
        若未提供则回退到检查消息中是否包含 @bot 的消息段。
        """
        if "to_me" in self._raw:
            return bool(self._raw["to_me"])
        return self.is_tome()

    def is_tome(self, bot_id: Optional[Union[int, str]] = None) -> bool:
        """检查消息是否 @ 了 bot。

        优先使用传入的 bot_id,否则回退到事件本身的 self_id(接收 bot 的 QQ 号)。
        """
        target = bot_id if bot_id is not None else self.self_id
        if target is None:
            return False
        target_str = str(target)
        for seg in self.message:
            if seg.type == "at" and str(seg.data.get("qq", "")) == target_str:
                return True
        return False


class GroupMessageEvent(MessageEvent):
    """群消息事件。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.group_id = raw.get("group_id")
        self.anonymous = raw.get("anonymous")


class PrivateMessageEvent(MessageEvent):
    """私聊消息事件,无 group_id。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.group_id = None

    @property
    def to_me(self) -> bool:
        """私聊消息始终视为发给机器人。"""
        return True


class NoticeEvent(Event):
    """通知事件基类。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.notice_type = raw.get("notice_type")
        self.group_id = raw.get("group_id")
        self.user_id = raw.get("user_id")
        self.operator_id = raw.get("operator_id")
        self.sub_type = raw.get("sub_type")


class GroupIncreaseNoticeEvent(NoticeEvent):
    """群成员增加通知。sub_type: approve / invite。"""


class GroupDecreaseNoticeEvent(NoticeEvent):
    """群成员减少通知。sub_type: leave / kick / kick_me。"""


class GroupAdminNoticeEvent(NoticeEvent):
    """群管理员变动通知。sub_type: set / unset。"""


class GroupRecallNoticeEvent(NoticeEvent):
    """群消息撤回通知。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.message_id = raw.get("message_id")
        self.operator_id = raw.get("operator_id")
        self.user_id = raw.get("user_id")


class RequestEvent(Event):
    """请求事件基类。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.request_type = raw.get("request_type")


class GroupRequestEvent(RequestEvent):
    """群请求事件。sub_type: add / invite。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.group_id = raw.get("group_id")
        self.user_id = raw.get("user_id")
        self.comment = raw.get("comment", "")
        self.flag = raw.get("flag", "")
        self.sub_type = raw.get("sub_type")


class MetaEvent(Event):
    """元事件基类。"""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.meta_event_type = raw.get("meta_event_type")
        self.sub_type = raw.get("sub_type")


class LifecycleMetaEvent(MetaEvent):
    """生命周期元事件。sub_type: enable / disable / connect。"""


def parse_event(data: dict) -> Optional[Event]:
    """根据原始 JSON dict 构造对应的 Event 子类实例。

    无法识别的事件类型时返回 None。
    """
    if not isinstance(data, dict):
        return None
    post_type = data.get("post_type")

    if post_type == "message":
        message_type = data.get("message_type")
        if message_type == "group":
            return GroupMessageEvent(data)
        if message_type == "private":
            return PrivateMessageEvent(data)
        return MessageEvent(data)

    if post_type == "notice":
        notice_type = data.get("notice_type")
        if notice_type == "group_increase":
            return GroupIncreaseNoticeEvent(data)
        if notice_type == "group_decrease":
            return GroupDecreaseNoticeEvent(data)
        if notice_type == "group_admin":
            return GroupAdminNoticeEvent(data)
        if notice_type == "group_recall":
            return GroupRecallNoticeEvent(data)
        return NoticeEvent(data)

    if post_type == "request":
        request_type = data.get("request_type")
        if request_type == "group":
            return GroupRequestEvent(data)
        return RequestEvent(data)

    if post_type == "meta_event":
        meta_event_type = data.get("meta_event_type")
        if meta_event_type == "lifecycle":
            return LifecycleMetaEvent(data)
        return MetaEvent(data)

    return None
