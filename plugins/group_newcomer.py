from core import on_command, on_notice, on_request, GROUP_ADMIN, GROUP_OWNER, SUPERUSER, CommandArg
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
    NoticeEvent,
    RequestEvent,
    GroupIncreaseNoticeEvent,
    GroupRequestEvent,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

set_auto_accept = on_command("设置进群自动同意", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_auto_reject = on_command("设置进群自动拒绝", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_auto_ignore = on_command("设置进群自动忽略", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_no_handle = on_command("设置进群不处理", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

set_reject_level = on_command("拒绝等级低于", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_reject_nickname = on_command("拒绝昵称包含", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_reject_sign = on_command("拒绝签名包含", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

set_join_mute = on_command("设置进群禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
close_join_mute = on_command("关闭进群禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

group_request_handler = on_request(priority=5, block=False)
group_increase_mute_handler = on_notice(priority=10, block=False)


@set_auto_accept.handle()
async def handle_set_auto_accept(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_newcomer_join_mode(group_id, "auto_accept")
    await set_auto_accept.finish(reply_msg(event, "✅ 已设置进群自动同意"))


@set_auto_reject.handle()
async def handle_set_auto_reject(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_newcomer_join_mode(group_id, "auto_reject")
    await set_auto_reject.finish(reply_msg(event, "✅ 已设置进群自动拒绝"))


@set_auto_ignore.handle()
async def handle_set_auto_ignore(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_newcomer_join_mode(group_id, "auto_ignore")
    await set_auto_ignore.finish(reply_msg(event, "✅ 已设置进群自动忽略（请求将留在列表中不处理）"))


@set_no_handle.handle()
async def handle_set_no_handle(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_newcomer_join_mode(group_id, "none")
    await set_no_handle.finish(reply_msg(event, "✅ 已设置进群不处理（恢复手动审批）"))


@set_reject_level.handle()
async def handle_set_reject_level(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_reject_level.finish(reply_msg(event, "请提供等级数值，例如：拒绝等级低于10"))
    try:
        level = int(text)
        if level < 1:
            raise ValueError
    except ValueError:
        await set_reject_level.finish(reply_msg(event, "❌ 等级必须为正整数"))

    group_id = event.group_id
    config_manager.set_newcomer_reject_level(group_id, level)
    await set_reject_level.finish(reply_msg(event, f"✅ 已设置拒绝等级低于 {level} 的加群请求"))


@set_reject_nickname.handle()
async def handle_set_reject_nickname(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await set_reject_nickname.finish(reply_msg(event, "请提供关键词，例如：拒绝昵称包含广告"))

    group_id = event.group_id
    newcomer_config = config_manager.get_newcomer_config(group_id)
    existing = newcomer_config.get("reject_nickname_contains", [])
    if keyword in existing:
        await set_reject_nickname.finish(reply_msg(event, f"关键词「{keyword}」已在拒绝昵称列表中"))

    config_manager.add_newcomer_reject_nickname(group_id, keyword)
    updated = config_manager.get_newcomer_config(group_id).get("reject_nickname_contains", [])
    await set_reject_nickname.finish(reply_msg(event, f"✅ 已添加拒绝昵称关键词「{keyword}」\n当前关键词列表：{', '.join(updated)}"))


@set_reject_sign.handle()
async def handle_set_reject_sign(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await set_reject_sign.finish(reply_msg(event, "请提供关键词，例如：拒绝签名包含广告"))

    group_id = event.group_id
    newcomer_config = config_manager.get_newcomer_config(group_id)
    existing = newcomer_config.get("reject_sign_contains", [])
    if keyword in existing:
        await set_reject_sign.finish(reply_msg(event, f"关键词「{keyword}」已在拒绝签名列表中"))

    config_manager.add_newcomer_reject_sign(group_id, keyword)
    updated = config_manager.get_newcomer_config(group_id).get("reject_sign_contains", [])
    await set_reject_sign.finish(reply_msg(event, f"✅ 已添加拒绝签名关键词「{keyword}」\n当前关键词列表：{', '.join(updated)}"))


@set_join_mute.handle()
async def handle_set_join_mute(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_join_mute.finish(reply_msg(event, "请提供禁言分钟数，例如：设置进群禁言5"))
    try:
        minutes = int(text)
        if minutes < 1:
            raise ValueError
    except ValueError:
        await set_join_mute.finish(reply_msg(event, "❌ 禁言分钟数必须为正整数"))

    group_id = event.group_id
    config_manager.set_newcomer_mute_minutes(group_id, minutes)
    await set_join_mute.finish(reply_msg(event, f"✅ 已设置进群禁言 {minutes} 分钟"))


@close_join_mute.handle()
async def handle_close_join_mute(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_newcomer_mute_minutes(group_id, 0)
    await close_join_mute.finish(reply_msg(event, "✅ 已关闭进群禁言"))


@group_request_handler.handle()
async def handle_group_request(bot: Bot, event: RequestEvent):
    if not isinstance(event, GroupRequestEvent):
        return

    if event.sub_type != "add":
        return

    group_id = event.group_id
    user_id = event.user_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "新人系统"):
        return

    newcomer_config = config_manager.get_newcomer_config(group_id)
    join_mode = newcomer_config.get("join_mode", "none")

    if join_mode == "none":
        return

    nickname = ""
    level = 0
    sign = ""

    need_check_filters = (
        newcomer_config.get("reject_level_below", 0) > 0
        or newcomer_config.get("reject_nickname_contains", [])
        or newcomer_config.get("reject_sign_contains", [])
    )

    if need_check_filters:
        try:
            user_info = await bot.get_stranger_info(user_id=user_id)
            nickname = user_info.get("nickname", "")
            level = user_info.get("level", 0)
            sign = user_info.get("sign", "")
        except Exception as e:
            log_manager.log_error("newcomer_info", f"Failed to get user info: {e}")

    reject_level = newcomer_config.get("reject_level_below", 0)
    if reject_level > 0:
        try:
            user_level = int(level)
        except (ValueError, TypeError):
            user_level = 0
        if 0 < user_level < reject_level:
            try:
                await event.reject(bot, reason=f"QQ等级低于{reject_level}")
                log_manager.log_notice("newcomer_reject", f"User {user_id} rejected from group {group_id}: level {user_level} < {reject_level}")
            except Exception as e:
                log_manager.log_error("newcomer_reject", f"Failed to reject: {e}")
            return

    for keyword in newcomer_config.get("reject_nickname_contains", []):
        if keyword in nickname:
            try:
                await event.reject(bot, reason="昵称包含违规关键词")
                log_manager.log_notice("newcomer_reject", f"User {user_id} rejected from group {group_id}: nickname contains '{keyword}'")
            except Exception as e:
                log_manager.log_error("newcomer_reject", f"Failed to reject: {e}")
            return

    for keyword in newcomer_config.get("reject_sign_contains", []):
        if keyword in sign:
            try:
                await event.reject(bot, reason="签名包含违规关键词")
                log_manager.log_notice("newcomer_reject", f"User {user_id} rejected from group {group_id}: sign contains '{keyword}'")
            except Exception as e:
                log_manager.log_error("newcomer_reject", f"Failed to reject: {e}")
            return

    if join_mode == "auto_accept":
        try:
            await event.approve(bot)
            log_manager.log_notice("newcomer_accept", f"User {user_id} auto-accepted to group {group_id}")
        except Exception as e:
            log_manager.log_error("newcomer_accept", f"Failed to approve: {e}")
    elif join_mode == "auto_reject":
        try:
            await event.reject(bot, reason="群主设置了自动拒绝")
            log_manager.log_notice("newcomer_reject", f"User {user_id} auto-rejected from group {group_id}")
        except Exception as e:
            log_manager.log_error("newcomer_reject", f"Failed to reject: {e}")
    elif join_mode == "auto_ignore":
        log_manager.log_notice("newcomer_ignore", f"User {user_id} request ignored in group {group_id}")


@group_increase_mute_handler.handle()
async def handle_group_increase_mute(bot: Bot, event: NoticeEvent):
    if not isinstance(event, GroupIncreaseNoticeEvent):
        return

    user_id = event.user_id
    if user_id == int(bot.self_id):
        return

    group_id = event.group_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "新人系统"):
        return

    newcomer_config = config_manager.get_newcomer_config(group_id)
    mute_minutes = newcomer_config.get("mute_minutes", 0)

    if mute_minutes > 0:
        try:
            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=mute_minutes * 60
            )
            log_manager.log_notice("newcomer_mute", f"User {user_id} muted for {mute_minutes} minutes in group {group_id}")
        except Exception as e:
            log_manager.log_error("newcomer_mute", f"Failed to mute: {e}")


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_NEWCOMER_MENU_ITEMS = {
    "设置进群自动同意": "👋 设置进群自动同意",
    "设置进群自动拒绝": "👋 设置进群自动拒绝",
    "设置进群自动忽略": "👋 设置进群自动忽略",
    "设置进群不处理": "👋 设置进群不处理",
    "拒绝等级低于": "👋 拒绝等级低于",
    "拒绝昵称包含": "👋 拒绝昵称包含",
    "拒绝签名包含": "👋 拒绝签名包含",
    "设置进群禁言": "👋 设置进群禁言",
    "关闭进群禁言": "👋 关闭进群禁言",
}

for _item_name, _text in _NEWCOMER_MENU_ITEMS.items():
    menu_registry.register(
        category="新人管理",
        item_name=_item_name,
        text=_text,
        category_title="👋◇━新人管理━◇👋",
        category_trigger="新人管理",
        category_description="进群处理·拒绝条件·进群禁言",
    )
