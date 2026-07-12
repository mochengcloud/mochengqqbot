"""QQ 官方事件 → 内部 OneBot 风格事件转换器。

官方事件 payload 结构:
  {
    "op": 0,                              # 0=Dispatch 事件推送
    "s": 4,                               # 序列号
    "t": "GROUP_AT_MESSAGE_CREATE",       # 事件类型
    "id": "event_id",                     # 事件 ID
    "d": {...}                            # 事件数据(因事件类型而异)
  }

支持的群机器人事件(需订阅 intent 1<<25 GROUP_AND_C2C_EVENT):
  - GROUP_AT_MESSAGE_CREATE: 群@机器人消息(被动回复,所有机器人可订阅)
      d = {
        "id": "msg_id",
        "group_openid": "...",
        "content": "消息文本(可能含 <qqbotuser> 标签前缀)",
        "author": {"member_openid": "..."},
        "timestamp": "2026-07-12T20:00:00+08:00",
        "attachments": [{"content_type": "image/png", "url": "https://..."}]
      }
  - GROUP_MESSAGE_CREATE: 群全量消息(需申请"全量消息"权限白名单)
      d 结构同 GROUP_AT_MESSAGE_CREATE,但不一定 @机器人
  - AT_MESSAGE_CREATE: 频道@机器人消息(转为 GroupMessageEvent)
  - C2C_MESSAGE_CREATE: C2C 私聊消息
      d = {
        "id": "msg_id",
        "content": "...",
        "author": {"user_openid": "..."},
        "timestamp": "...",
        "attachments": [...]
      }
  - GROUP_ADD_ROBOT / GROUP_DEL_ROBOT: 机器人被加入/移出群(通知事件)
  - FRIEND_ADD / FRIEND_DEL: 添加/删除好友(通知事件)

权限说明:
  - GROUP_AT_MESSAGE_CREATE: 所有机器人默认可订阅(被动回复)
  - GROUP_MESSAGE_CREATE: 需申请"全量消息"权限白名单,开通后才会推送
  - 两者事件结构相同,但 GROUP_MESSAGE_CREATE 不一定 @机器人
"""
import time
from typing import Any, Dict, Optional

from core.onebot.models import (
    Event,
    GroupMessageEvent,
    Message,
    MessageSegment,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
    Sender,
)


# 机器人用户名标签正则: <qqbotuser id="xxx" name="xxx" />
# @机器人时,content 前面会带这个标签,需要剥离以获取实际文本
import re
_QQBOT_TAG_PATTERN = re.compile(r'<qqbotuser[^>]*/>')


def _strip_bot_mention(content: str) -> str:
    """剥离 content 中的 <qqbotuser> 标签(群@机器人消息会带此前缀)。"""
    if not content:
        return ""
    # 移除 <qqbotuser .../> 标签
    content = _QQBOT_TAG_PATTERN.sub('', content)
    # 去除前后空白
    return content.strip()


def _build_message_from_content(content: str, attachments: list = None) -> Message:
    """从官方 content(纯文本)与 attachments(附件)构建 Message。

    官方 attachments 结构:
      [{"content_type": "image/png", "filename": "xx.png", "url": "https://..."}]
    """
    msg = Message()
    if content:
        msg.append(MessageSegment.text(content))
    if attachments:
        for att in attachments:
            # 官方附件用 content_type 字段标识类型(非 type)
            ctype = att.get("content_type", "") or att.get("type", "")
            url = att.get("url", "")
            if not url:
                continue
            if ctype.startswith("image") or ctype == "image":
                msg.append(MessageSegment.image(url))
            # 其他附件类型暂不处理
    return msg


def convert_event(payload: dict, self_id: str, adapter_type: str = "qq_official") -> Optional[Event]:
    """将 QQ 官方 WS 事件 payload 转换为内部 Event。

    返回 None 表示非业务事件或暂不支持的事件类型。
    """
    # 事件推送 op=0;非事件(Hello/心跳/IDENTIFY 等)直接丢弃
    op = payload.get("op")
    if op is not None and op != 0:
        return None
    # 事件类型在 t 字段(不是 type)
    event_type = payload.get("t", "")
    if not event_type:
        return None

    d = payload.get("d", {}) or {}
    now = int(time.time())

    # ---------------- 消息事件 ----------------
    # GROUP_AT_MESSAGE_CREATE: 群@机器人消息(被动,to_me=True)
    # GROUP_MESSAGE_CREATE: 群全量消息(需白名单,to_me=False)
    # AT_MESSAGE_CREATE: 频道@机器人消息(转为群消息处理)
    if event_type in ("GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
        return _convert_group_message(d, self_id, now, adapter_type, to_me=True)
    if event_type == "GROUP_MESSAGE_CREATE":
        return _convert_group_message(d, self_id, now, adapter_type, to_me=False)
    if event_type == "C2C_MESSAGE_CREATE":
        return _convert_c2c_message(d, self_id, now, adapter_type)

    # ---------------- 通知事件 ----------------
    if event_type in ("GROUP_ADD_ROBOT", "GROUP_DEL_ROBOT"):
        return _convert_group_robot_event(d, self_id, now, event_type, adapter_type)
    if event_type in ("FRIEND_ADD", "FRIEND_DEL"):
        return _convert_friend_event(d, self_id, now, event_type, adapter_type)

    # 其他事件(READY/RESUMED 等连接状态事件不应进入此函数)
    return None


def _convert_group_message(d: dict, self_id: str, now: int, adapter_type: str, to_me: bool = True) -> GroupMessageEvent:
    """转换 GROUP_AT_MESSAGE_CREATE / GROUP_MESSAGE_CREATE / AT_MESSAGE_CREATE 事件。

    Args:
        to_me: 是否 @机器人。GROUP_AT_MESSAGE_CREATE 为 True,GROUP_MESSAGE_CREATE 为 False。
    """
    author = d.get("author", {}) or {}
    user_id = author.get("member_openid") or author.get("id") or ""
    group_id = d.get("group_openid") or d.get("channel_id") or ""
    message_id = d.get("id", "")
    content = d.get("content", "") or ""
    # 剥离 <qqbotuser> @机器人标签(仅 @机器人消息会有此标签)
    content = _strip_bot_mention(content)
    attachments = d.get("attachments", []) or []
    message = _build_message_from_content(content, attachments)

    raw = {
        "post_type": "message",
        "time": now,
        "self_id": self_id,
        "message_id": message_id,
        "message": message,
        "raw_message": content,
        "sender": {"nickname": author.get("nickname", ""), "user_id": user_id},
        "message_type": "group",
        "sub_type": "at" if to_me else "normal",
        "group_id": group_id,
        "user_id": user_id,
        "to_me": to_me,
    }
    event = GroupMessageEvent(raw)
    event.adapter_type = adapter_type
    return event


def _convert_c2c_message(d: dict, self_id: str, now: int, adapter_type: str) -> PrivateMessageEvent:
    """转换 C2C_MESSAGE_CREATE 事件。"""
    author = d.get("author", {}) or {}
    user_id = author.get("user_openid") or author.get("id") or ""
    message_id = d.get("id", "")
    content = d.get("content", "") or ""
    attachments = d.get("attachments", []) or []
    message = _build_message_from_content(content, attachments)

    raw = {
        "post_type": "message",
        "time": now,
        "self_id": self_id,
        "message_id": message_id,
        "message": message,
        "raw_message": content,
        "sender": {"nickname": author.get("nickname", ""), "user_id": user_id},
        "message_type": "private",
        "sub_type": "friend",
        "user_id": user_id,
    }
    event = PrivateMessageEvent(raw)
    event.adapter_type = adapter_type
    return event


def _convert_group_robot_event(d: dict, self_id: str, now: int, event_type: str, adapter_type: str) -> NoticeEvent:
    """转换 GROUP_ADD_ROBOT / GROUP_DEL_ROBOT 事件(机器人被加入/移出群)。"""
    group_id = d.get("group_openid", "")
    op_member = d.get("op_member_openid", "")  # 操作者 openid
    raw = {
        "post_type": "notice",
        "time": now,
        "self_id": self_id,
        "notice_type": "group_increase" if event_type == "GROUP_ADD_ROBOT" else "group_decrease",
        "sub_type": "invite" if event_type == "GROUP_ADD_ROBOT" else "kick",
        "group_id": group_id,
        "user_id": op_member,
        "operator_id": op_member,
    }
    event = NoticeEvent(raw)
    event.adapter_type = adapter_type
    return event


def _convert_friend_event(d: dict, self_id: str, now: int, event_type: str, adapter_type: str) -> NoticeEvent:
    """转换 FRIEND_ADD / FRIEND_DEL 事件。"""
    user_id = d.get("openid", "")
    raw = {
        "post_type": "notice",
        "time": now,
        "self_id": self_id,
        "notice_type": "friend_add" if event_type == "FRIEND_ADD" else "friend_del",
        "sub_type": "",
        "user_id": user_id,
    }
    event = NoticeEvent(raw)
    event.adapter_type = adapter_type
    return event
