from core import on_command, on_notice, GROUP_ADMIN, GROUP_OWNER, SUPERUSER, CommandArg
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
    NoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
    GroupAdminNoticeEvent,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

enable_welcome = on_command("开启欢迎词", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_welcome = on_command("关闭欢迎词", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_welcome_text = on_command("设置欢迎提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_join_private = on_command("开启进群私聊", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_join_private = on_command("关闭进群私聊", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_join_private_text = on_command("设置进群私聊", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_kick_notify = on_command("开启踢人提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_kick_notify = on_command("关闭踢人提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_kick_text = on_command("设置踢人提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_admin_set_notify = on_command("开启上管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_admin_set_notify = on_command("关闭上管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_admin_set_text = on_command("设置上管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_admin_unset_notify = on_command("开启下管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_admin_unset_notify = on_command("关闭下管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_admin_unset_text = on_command("设置下管提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_leave_notify = on_command("开启退群提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_leave_notify = on_command("关闭退群提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_leave_text = on_command("设置退群提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

group_increase_notify = on_notice(priority=15, block=False)
group_decrease_notify = on_notice(priority=15, block=False)
group_admin_notify = on_notice(priority=15, block=False)


async def _get_user_nickname(bot: Bot, group_id: int, user_id: int) -> str:
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        return member_info.get("card") or member_info.get("nickname", str(user_id))
    except Exception:
        try:
            user_info = await bot.get_stranger_info(user_id=user_id)
            return user_info.get("nickname", str(user_id))
        except Exception:
            return str(user_id)


async def _get_group_name(bot: Bot, group_id: int) -> str:
    try:
        group_info = await bot.get_group_info(group_id=group_id)
        return group_info.get("group_name", str(group_id))
    except Exception:
        return str(group_id)


def _format_text(text: str, nickname: str = "", user_id: int = 0, group_name: str = "") -> str:
    return text.replace("{nickname}", nickname).replace("{user_id}", str(user_id)).replace("{group_name}", group_name)


@enable_welcome.handle()
async def handle_enable_welcome(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_welcome_enabled(group_id, True)
    await enable_welcome.finish(reply_msg(event, "✅ 欢迎词已开启"))


@disable_welcome.handle()
async def handle_disable_welcome(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_welcome_enabled(group_id, False)
    await disable_welcome.finish(reply_msg(event, "❌ 欢迎词已关闭"))


@set_welcome_text.handle()
async def handle_set_welcome_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_welcome_text.finish(reply_msg(event, "请提供欢迎词内容，例如：设置欢迎提示欢迎加入本群"))
    group_id = event.group_id
    config_manager.set_notify_welcome_text(group_id, text)
    await set_welcome_text.finish(reply_msg(event, f"✅ 欢迎提示已设置为：{text}"))


@enable_join_private.handle()
async def handle_enable_join_private(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_join_private_enabled(group_id, True)
    await enable_join_private.finish(reply_msg(event, "✅ 进群私聊已开启"))


@disable_join_private.handle()
async def handle_disable_join_private(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_join_private_enabled(group_id, False)
    await disable_join_private.finish(reply_msg(event, "❌ 进群私聊已关闭"))


@set_join_private_text.handle()
async def handle_set_join_private_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_join_private_text.finish(reply_msg(event, "请提供进群私聊内容，例如：设置进群私聊欢迎加入，请遵守群规"))
    group_id = event.group_id
    config_manager.set_notify_join_private_text(group_id, text)
    await set_join_private_text.finish(reply_msg(event, f"✅ 进群私聊内容已设置为：{text}"))


@enable_kick_notify.handle()
async def handle_enable_kick_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_kick_enabled(group_id, True)
    await enable_kick_notify.finish(reply_msg(event, "✅ 踢人提示已开启"))


@disable_kick_notify.handle()
async def handle_disable_kick_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_kick_enabled(group_id, False)
    await disable_kick_notify.finish(reply_msg(event, "❌ 踢人提示已关闭"))


@set_kick_text.handle()
async def handle_set_kick_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_kick_text.finish(reply_msg(event, "请提供踢人提示内容，例如：设置踢人提示已被踢出本群"))
    group_id = event.group_id
    config_manager.set_notify_kick_text(group_id, text)
    await set_kick_text.finish(reply_msg(event, f"✅ 踢人提示已设置为：{text}"))


@enable_admin_set_notify.handle()
async def handle_enable_admin_set_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_admin_set_enabled(group_id, True)
    await enable_admin_set_notify.finish(reply_msg(event, "✅ 上管提示已开启"))


@disable_admin_set_notify.handle()
async def handle_disable_admin_set_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_admin_set_enabled(group_id, False)
    await disable_admin_set_notify.finish(reply_msg(event, "❌ 上管提示已关闭"))


@set_admin_set_text.handle()
async def handle_set_admin_set_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_admin_set_text.finish(reply_msg(event, "请提供上管提示内容，例如：设置上管提示恭喜成为管理员"))
    group_id = event.group_id
    config_manager.set_notify_admin_set_text(group_id, text)
    await set_admin_set_text.finish(reply_msg(event, f"✅ 上管提示已设置为：{text}"))


@enable_admin_unset_notify.handle()
async def handle_enable_admin_unset_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_admin_unset_enabled(group_id, True)
    await enable_admin_unset_notify.finish(reply_msg(event, "✅ 下管提示已开启"))


@disable_admin_unset_notify.handle()
async def handle_disable_admin_unset_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_admin_unset_enabled(group_id, False)
    await disable_admin_unset_notify.finish(reply_msg(event, "❌ 下管提示已关闭"))


@set_admin_unset_text.handle()
async def handle_set_admin_unset_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_admin_unset_text.finish(reply_msg(event, "请提供下管提示内容，例如：设置下管提示已被取消管理员"))
    group_id = event.group_id
    config_manager.set_notify_admin_unset_text(group_id, text)
    await set_admin_unset_text.finish(reply_msg(event, f"✅ 下管提示已设置为：{text}"))


@enable_leave_notify.handle()
async def handle_enable_leave_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_leave_enabled(group_id, True)
    await enable_leave_notify.finish(reply_msg(event, "✅ 退群提示已开启"))


@disable_leave_notify.handle()
async def handle_disable_leave_notify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_notify_leave_enabled(group_id, False)
    await disable_leave_notify.finish(reply_msg(event, "❌ 退群提示已关闭"))


@set_leave_text.handle()
async def handle_set_leave_text(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_leave_text.finish(reply_msg(event, "请提供退群提示内容，例如：设置退群提示已离开本群"))
    group_id = event.group_id
    config_manager.set_notify_leave_text(group_id, text)
    await set_leave_text.finish(reply_msg(event, f"✅ 退群提示已设置为：{text}"))


@group_increase_notify.handle()
async def handle_group_increase_notify(bot: Bot, event: NoticeEvent):
    if not isinstance(event, GroupIncreaseNoticeEvent):
        return

    user_id = event.user_id
    if user_id == int(bot.self_id):
        return

    group_id = event.group_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "提示系统"):
        return

    notify_config = config_manager.get_notify_config(group_id)

    nickname = ""
    group_name = ""
    need_info = notify_config.get("welcome_enabled", False) or notify_config.get("join_private_enabled", False)
    if need_info:
        nickname = await _get_user_nickname(bot, group_id, user_id)
        group_name = await _get_group_name(bot, group_id)

    if notify_config.get("welcome_enabled", False):
        welcome_text = notify_config.get("welcome_text", "欢迎加入本群！")
        formatted = _format_text(welcome_text, nickname, user_id, group_name)
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {formatted}")
            )
        except Exception as e:
            log_manager.log_error("notify_welcome", str(e))

    if notify_config.get("join_private_enabled", False):
        join_private_text = notify_config.get("join_private_text", "欢迎加入本群，请遵守群规！")
        formatted = _format_text(join_private_text, nickname, user_id, group_name)
        try:
            await bot.send_private_msg(user_id=user_id, message=Message(formatted))
        except Exception as e:
            log_manager.log_error("notify_join_private", str(e))

    log_manager.log_notice("notify_join", f"User {user_id} joined group {group_id}")


@group_decrease_notify.handle()
async def handle_group_decrease_notify(bot: Bot, event: NoticeEvent):
    if not isinstance(event, GroupDecreaseNoticeEvent):
        return

    user_id = event.user_id
    if user_id == int(bot.self_id):
        return

    group_id = event.group_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "提示系统"):
        return

    notify_config = config_manager.get_notify_config(group_id)
    sub_type = event.sub_type

    nickname = ""
    group_name = ""
    need_info = (sub_type == "kick" and notify_config.get("kick_enabled", False)) or \
                (sub_type == "leave" and notify_config.get("leave_enabled", False))
    if need_info:
        nickname = await _get_user_nickname(bot, group_id, user_id)
        group_name = await _get_group_name(bot, group_id)

    if sub_type == "kick" and notify_config.get("kick_enabled", False):
        kick_text = notify_config.get("kick_text", "已被踢出本群")
        formatted = _format_text(kick_text, nickname, user_id, group_name)
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {formatted}")
            )
        except Exception as e:
            log_manager.log_error("notify_kick", str(e))

    if sub_type == "leave" and notify_config.get("leave_enabled", False):
        leave_text = notify_config.get("leave_text", "已离开本群")
        formatted = _format_text(leave_text, nickname, user_id, group_name)
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"{nickname} {formatted}")
            )
        except Exception as e:
            log_manager.log_error("notify_leave", str(e))

    log_manager.log_notice("notify_decrease", f"User {user_id} left group {group_id} ({sub_type})")


@group_admin_notify.handle()
async def handle_group_admin_notify(bot: Bot, event: NoticeEvent):
    if not isinstance(event, GroupAdminNoticeEvent):
        return

    group_id = event.group_id
    user_id = event.user_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "提示系统"):
        return

    notify_config = config_manager.get_notify_config(group_id)
    sub_type = event.sub_type

    nickname = ""
    group_name = ""
    need_info = (sub_type == "set" and notify_config.get("admin_set_enabled", False)) or \
                (sub_type == "unset" and notify_config.get("admin_unset_enabled", False))
    if need_info:
        nickname = await _get_user_nickname(bot, group_id, user_id)
        group_name = await _get_group_name(bot, group_id)

    if sub_type == "set" and notify_config.get("admin_set_enabled", False):
        admin_set_text = notify_config.get("admin_set_text", "恭喜成为本群管理员！")
        formatted = _format_text(admin_set_text, nickname, user_id, group_name)
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {formatted}")
            )
        except Exception as e:
            log_manager.log_error("notify_admin_set", str(e))

    if sub_type == "unset" and notify_config.get("admin_unset_enabled", False):
        admin_unset_text = notify_config.get("admin_unset_text", "已被取消管理员身份")
        formatted = _format_text(admin_unset_text, nickname, user_id, group_name)
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {formatted}")
            )
        except Exception as e:
            log_manager.log_error("notify_admin_unset", str(e))

    log_manager.log_notice("notify_admin", f"User {user_id} admin {sub_type} in group {group_id}")


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_NOTIFY_MENU_ITEMS = {
    "开启欢迎词": "✅ 开启欢迎词",
    "关闭欢迎词": "❌ 关闭欢迎词",
    "设置欢迎提示": "🔔 设置欢迎提示",
    "开启进群私聊": "✅ 开启进群私聊",
    "关闭进群私聊": "❌ 关闭进群私聊",
    "设置进群私聊": "🔔 设置进群私聊",
    "开启踢人提示": "✅ 开启踢人提示",
    "关闭踢人提示": "❌ 关闭踢人提示",
    "设置踢人提示": "🔔 设置踢人提示",
    "开启上管提示": "✅ 开启上管提示",
    "关闭上管提示": "❌ 关闭上管提示",
    "设置上管提示": "🔔 设置上管提示",
    "开启下管提示": "✅ 开启下管提示",
    "关闭下管提示": "❌ 关闭下管提示",
    "设置下管提示": "🔔 设置下管提示",
    "开启退群提示": "✅ 开启退群提示",
    "关闭退群提示": "❌ 关闭退群提示",
    "设置退群提示": "🔔 设置退群提示",
}

for _item_name, _text in _NOTIFY_MENU_ITEMS.items():
    menu_registry.register(
        category="群通知",
        item_name=_item_name,
        text=_text,
        category_title="🔔◇━群通知━◇🔔",
        category_trigger="群通知",
        category_description="欢迎词·进群私聊·踢人/上管/下管/退群提示",
    )
