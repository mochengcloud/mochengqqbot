from core.onebot import (
    GroupMessageEvent,
    PrivateMessageEvent,
    Message,
    MessageSegment,
)


def reply_msg(event: GroupMessageEvent, msg) -> Message:
    """将消息包装为引用+@+原始内容的格式"""
    result = Message()
    result.append(MessageSegment.reply(event.message_id))
    result.append(MessageSegment.at(event.user_id))
    if isinstance(msg, Message):
        result.extend(msg)
    elif isinstance(msg, MessageSegment):
        result.append(msg)
    else:
        result.append(MessageSegment.text(str(msg)))
    return result


def reply_private(event: PrivateMessageEvent, msg) -> Message:
    """私聊消息回复包装"""
    result = Message()
    if isinstance(msg, Message):
        result.extend(msg)
    elif isinstance(msg, MessageSegment):
        result.append(msg)
    else:
        result.append(MessageSegment.text(str(msg)))
    return result
