from core import on_command, FinishedException, CommandArg, SUPERUSER
from core.onebot import (
    Bot,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageEvent,
    Message,
)

from plugins.utils import reply_msg, reply_private


async def _reply(event: MessageEvent, msg: str) -> Message:
    if isinstance(event, GroupMessageEvent):
        return reply_msg(event, msg)
    return reply_private(event, msg)


owner_help = on_command("主人帮助", priority=1, block=True, permission=SUPERUSER)


@owner_help.handle()
async def handle_owner_help(bot: Bot, event: MessageEvent):
    text = (
        "👑 主人功能帮助\n"
        "━━━━━━━━━━━━━\n"
        "📋 我的群聊 — 查看机器人加入的所有群聊\n"
        "📋 退群 <群号> — 退出指定群聊\n"
        "📋 群发 <群号> <内容> — 向指定群发送消息\n"
        "📋 私聊 <QQ号> <内容> — 向指定用户发送私聊\n"
        "📋 我的好友 — 查看机器人所有好友\n"
        "📋 删除好友 <QQ号> — 删除指定好友\n"
        "📋 同意好友 <flag> — 同意好友添加请求\n"
        "━━━━━━━━━━━━━"
    )
    await owner_help.finish(await _reply(event, text))


my_groups = on_command("我的群聊", priority=1, block=True, permission=SUPERUSER)


@my_groups.handle()
async def handle_my_groups(bot: Bot, event: MessageEvent):
    try:
        groups = await bot.get_group_list()
        if not groups:
            await my_groups.finish(await _reply(event, "❌ 机器人没有加入任何群聊"))
        lines = [f"📋 我的群聊（共 {len(groups)} 个）："]
        for g in groups:
            name = g.get("group_name", "未知")
            gid = g.get("group_id", "")
            lines.append(f"• {name}（{gid}）")
        await my_groups.finish(await _reply(event, "\n".join(lines)))
    except FinishedException:
        raise
    except Exception as e:
        await my_groups.finish(await _reply(event, f"❌ 获取群列表失败：{e}"))


leave_group = on_command("退群", priority=1, block=True, permission=SUPERUSER)


@leave_group.handle()
async def handle_leave_group(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text or not text.isdigit():
        await leave_group.finish(await _reply(event, "请提供群号，例如：退群 123456789"))
    try:
        group_id = int(text)
        await bot.set_group_leave(group_id=group_id)
        await leave_group.finish(await _reply(event, f"✅ 已退出群聊 {group_id}"))
    except FinishedException:
        raise
    except Exception as e:
        await leave_group.finish(await _reply(event, f"❌ 退群失败：{e}"))


send_group = on_command("群发", priority=1, block=True, permission=SUPERUSER)


@send_group.handle()
async def handle_send_group(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await send_group.finish(await _reply(event, "请提供群号和消息内容，例如：群发 123456789 大家好"))
    parts = text.split(" ", 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await send_group.finish(await _reply(event, "格式错误，请使用：群发 <群号> <消息内容>"))
    group_id = int(parts[0])
    content = parts[1]
    try:
        await bot.send_group_msg(group_id=group_id, message=content)
        await send_group.finish(await _reply(event, f"✅ 已向群 {group_id} 发送消息"))
    except FinishedException:
        raise
    except Exception as e:
        await send_group.finish(await _reply(event, f"❌ 发送失败：{e}"))


send_private = on_command("私聊", priority=1, block=True, permission=SUPERUSER)


@send_private.handle()
async def handle_send_private(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await send_private.finish(await _reply(event, "请提供QQ号和消息内容，例如：私聊 123456789 你好"))
    parts = text.split(" ", 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await send_private.finish(await _reply(event, "格式错误，请使用：私聊 <QQ号> <消息内容>"))
    user_id = int(parts[0])
    content = parts[1]
    try:
        await bot.send_private_msg(user_id=user_id, message=content)
        await send_private.finish(await _reply(event, f"✅ 已向用户 {user_id} 发送消息"))
    except FinishedException:
        raise
    except Exception as e:
        await send_private.finish(await _reply(event, f"❌ 发送失败：{e}"))


my_friends = on_command("我的好友", priority=1, block=True, permission=SUPERUSER)


@my_friends.handle()
async def handle_my_friends(bot: Bot, event: MessageEvent):
    try:
        friends = await bot.get_friend_list()
        if not friends:
            await my_friends.finish(await _reply(event, "❌ 好友列表为空"))
        lines = [f"📋 我的好友（共 {len(friends)} 人）："]
        for f in friends:
            name = f.get("nickname", "未知")
            uid = f.get("user_id", "")
            remark = f.get("remark", "")
            remark_str = f"（{remark}）" if remark else ""
            lines.append(f"• {name}{remark_str} {uid}")
        await my_friends.finish(await _reply(event, "\n".join(lines)))
    except FinishedException:
        raise
    except Exception as e:
        await my_friends.finish(await _reply(event, f"❌ 获取好友列表失败：{e}"))


delete_friend = on_command("删除好友", priority=1, block=True, permission=SUPERUSER)


@delete_friend.handle()
async def handle_delete_friend(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text or not text.isdigit():
        await delete_friend.finish(await _reply(event, "请提供要删除的好友QQ号，例如：删除好友 123456789"))
    try:
        user_id = int(text)
        await bot.call_api("delete_friend", user_id=user_id)
        await delete_friend.finish(await _reply(event, f"✅ 已删除好友 {user_id}"))
    except FinishedException:
        raise
    except Exception as e:
        await delete_friend.finish(await _reply(event, f"❌ 删除好友失败：{e}"))


approve_friend = on_command("同意好友", priority=1, block=True, permission=SUPERUSER)


@approve_friend.handle()
async def handle_approve_friend(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await approve_friend.finish(await _reply(event, "请提供好友请求标识(flag)，例如：同意好友 abc123"))
    try:
        await bot.call_api("set_friend_add_request", flag=text, approve=True)
        await approve_friend.finish(await _reply(event, "✅ 已同意好友请求"))
    except FinishedException:
        raise
    except Exception as e:
        await approve_friend.finish(await _reply(event, f"❌ 操作失败：{e}"))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_OWNER_MENU_ITEMS = {
    "主人帮助": "👑 主人帮助",
    "我的群聊": "👑 我的群聊",
    "退群": "👑 退群",
    "群发": "👑 群发",
    "私聊": "👑 私聊",
    "我的好友": "👑 我的好友",
    "删除好友": "👑 删除好友",
    "同意好友": "👑 同意好友",
}

for _item_name, _text in _OWNER_MENU_ITEMS.items():
    menu_registry.register(
        category="主人功能",
        item_name=_item_name,
        text=_text,
        category_title="👑◇━主人功能━◇👑",
        category_trigger="主人功能",
        category_description="超管专用·群聊管理·消息群发",
    )
