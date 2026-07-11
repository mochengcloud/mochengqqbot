import re
import os
import sys
import threading
import time as time_module
import importlib
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from core import (
    on_message,
    on_command,
    get_driver,
    on_bot_connect,
    on_bot_disconnect,
    GROUP_ADMIN,
    GROUP_OWNER,
    SUPERUSER,
    FinishedException,
    CommandArg,
    ArgStr,
    T_State,
)
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    NoticeEvent,
    GroupRecallNoticeEvent,
)

from config_manager import config_manager, AVAILABLE_FEATURES
from core.menu_registry import menu_registry
from log_manager import log_manager
from plugins.utils import reply_msg

AUTH_WHITELIST_COMMANDS = {"授权群聊", "查看授权", "解除授权", "我的群聊", "退群", "群发", "私聊", "我的好友", "删除好友", "同意好友", "主人帮助"}

msg_logger = on_message(priority=-1, block=False)


@msg_logger.handle()
async def handle_msg_logger(event: GroupMessageEvent):
    log_manager.log_message(
        direction="receive",
        user_id=event.user_id,
        group_id=event.group_id,
        message=event.raw_message
    )


auth_check = on_message(priority=0, block=False)


@auth_check.handle()
async def handle_auth_check(bot: Bot, event: GroupMessageEvent):
    if await SUPERUSER(bot, event):
        return
    if not config_manager.is_authorization_enabled():
        return
    group_id = event.group_id
    raw_message = event.raw_message.strip()
    for cmd in AUTH_WHITELIST_COMMANDS:
        if raw_message.startswith(cmd):
            return
    if not config_manager.is_group_authorized(group_id):
        await auth_check.finish(reply_msg(event, "⚠️ 本群未授权，请使用「授权群聊 授权码」进行授权后使用"))


authorize_group = on_command("授权群聊", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
view_authorization = on_command("查看授权", priority=1, block=True)
revoke_authorization = on_command("解除授权", priority=1, block=True, permission=SUPERUSER)


@authorize_group.handle()
async def handle_authorize_group(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    code = args.extract_plain_text().strip()
    if not code:
        await authorize_group.finish(reply_msg(event, "请提供授权码，例如：授权群聊 XXXX-XXXX-XXXX"))

    existing_auth = config_manager.get_group_authorization(group_id)
    if existing_auth:
        success = config_manager.rebind_group_authorization(group_id, code)
        if success:
            new_auth = config_manager.get_group_authorization(group_id)
            auth_group = new_auth.get("auth_group", "未知")
            expire = new_auth.get("expire_time")
            expire_text = "永久" if not expire else expire
            await authorize_group.finish(reply_msg(event, f"✅ 授权已更新，旧授权已释放\n📋 授权分组：{auth_group}\n⏰ 到期时间：{expire_text}"))
        else:
            await authorize_group.finish(reply_msg(event, "❌ 授权码无效、已用完或已过期"))
    else:
        success = config_manager.use_auth_code(code, group_id)
        if success:
            auth_info = config_manager.get_group_authorization(group_id)
            auth_group = auth_info.get("auth_group", "未知")
            expire = auth_info.get("expire_time")
            expire_text = "永久" if not expire else expire
            await authorize_group.finish(reply_msg(event, f"✅ 授权成功\n📋 授权分组：{auth_group}\n⏰ 到期时间：{expire_text}"))
        else:
            codes = config_manager.get_auth_codes()
            if code not in codes:
                await authorize_group.finish(reply_msg(event, "❌ 授权码不存在"))
            code_data = codes[code]
            if code_data.get("expire_time"):
                try:
                    from datetime import datetime as dt
                    expire_dt = dt.fromisoformat(code_data["expire_time"])
                    if expire_dt < dt.now():
                        await authorize_group.finish(reply_msg(event, "❌ 授权码已过期"))
                except (ValueError, TypeError):
                    pass
            if code_data["max_uses"] > 0 and code_data["use_count"] >= code_data["max_uses"]:
                await authorize_group.finish(reply_msg(event, "❌ 授权码已用完"))
            await authorize_group.finish(reply_msg(event, "❌ 授权码无效"))


@view_authorization.handle()
async def handle_view_authorization(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_authorization_enabled():
        await view_authorization.finish(reply_msg(event, "授权系统未启用"))
    auth_info = config_manager.get_group_authorization(group_id)
    if not auth_info:
        await view_authorization.finish(reply_msg(event, "⚠️ 本群未授权\n请使用「授权群聊 授权码」进行授权"))
    auth_group = auth_info.get("auth_group", "未知")
    expire = auth_info.get("expire_time")
    activate_time = auth_info.get("activate_time", "未知")
    code = auth_info.get("code", "未知")
    permissions = config_manager.get_group_permissions(group_id)
    expire_text = "永久" if not expire else expire
    is_expired = False
    if expire:
        try:
            from datetime import datetime as dt
            if dt.fromisoformat(expire) < dt.now():
                is_expired = True
                expire_text = f"{expire}（已过期）"
        except (ValueError, TypeError):
            pass
    status = "❌ 已过期" if is_expired else "✅ 有效"
    perm_text = "、".join(permissions) if permissions else "无"
    msg = (
        f"📋 授权信息\n"
        f"━━━━━━━━━━━━━\n"
        f"📌 状态：{status}\n"
        f"📦 授权分组：{auth_group}\n"
        f"⏰ 到期时间：{expire_text}\n"
        f"🕐 激活时间：{activate_time}\n"
        f"🔑 授权码：{code}\n"
        f"🔓 可用功能：{perm_text}\n"
        f"━━━━━━━━━━━━━"
    )
    await view_authorization.finish(reply_msg(event, msg))


@revoke_authorization.handle()
async def handle_revoke_authorization(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.get_group_authorization(group_id):
        await revoke_authorization.finish(reply_msg(event, "本群未授权"))
    config_manager.remove_group_authorization(group_id)
    await revoke_authorization.finish(reply_msg(event, "✅ 本群授权已解除"))

main_menu = on_message(priority=1, block=False)


@main_menu.handle()
async def handle_main_menu(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    raw_message = event.raw_message.strip()
    
    if not config_manager.is_group_enabled(group_id):
        return
    
    if not config_manager.is_menu_enabled(group_id):
        return
    
    menu_cfg = config_manager.get_menu_config()
    # 先判断是否匹配主菜单触发词
    if raw_message == menu_cfg.get("trigger", "菜单"):
        menu_text = menu_registry.get_main_menu_text(
            global_title=menu_cfg.get("title"),
            global_desc=menu_cfg.get("description")
        )
        log_manager.log_message("send", event.user_id, group_id, menu_text[:100])
        await main_menu.finish(reply_msg(event, Message(menu_text)))
        return
    
    # 再判断是否匹配分类/子分类触发词
    category_key = menu_registry.get_category_by_trigger(raw_message)
    if category_key:
        menu_text = menu_registry.get_category_menu_text(category_key)
        if menu_text:
            log_manager.log_message("send", event.user_id, group_id, menu_text[:100])
            await main_menu.finish(reply_msg(event, Message(menu_text)))


enable_group = on_command("分群开机", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_group = on_command("分群关机", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_menu = on_command("打开菜单", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_menu = on_command("关闭菜单", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_whole_ban = on_command("开启全体禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_whole_ban = on_command("解除全体禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

ban_user = on_command("禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
unban_user = on_command("解除禁言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

recall_by_at = on_command("撤回", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
recall_by_keyword = on_command("撤回关键词", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
recall_recent = on_command("撤回最近", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

ban_list = on_command("禁言列表", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
unban_all = on_command("全部解禁", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

kick_user = on_command("踢出", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

check_never_speak = on_command("查看从未发言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
kick_never_speak = on_command("踢出从未发言", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

set_admin = on_command("上群管", priority=1, block=True, permission=GROUP_OWNER | SUPERUSER)
unset_admin = on_command("下群管", priority=1, block=True, permission=GROUP_OWNER | SUPERUSER)

set_title = on_command("设置头衔", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

clear_screen = on_command("清屏", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

send_notice = on_command("发送公告", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

group_message_history: dict = {}


def extract_at_user(event: GroupMessageEvent) -> Optional[int]:
    for seg in event.message:
        if seg.type == "at":
            return int(seg.data.get("qq", 0))
    return None


def extract_text_after_command(message: Message) -> str:
    text = message.extract_plain_text().strip()
    return text


@enable_group.handle()
async def handle_enable_group(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_group_enabled(group_id, True)
    await enable_group.finish(reply_msg(event, "✅ 本群机器人已开启"))


@disable_group.handle()
async def handle_disable_group(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_group_enabled(group_id, False)
    await disable_group.finish(reply_msg(event, "❌ 本群机器人已关闭"))


@enable_menu.handle()
async def handle_enable_menu(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_menu_enabled(group_id, True)
    await enable_menu.finish(reply_msg(event, "✅ 菜单功能已开启"))


@disable_menu.handle()
async def handle_disable_menu(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_menu_enabled(group_id, False)
    await disable_menu.finish(reply_msg(event, "❌ 菜单功能已关闭"))


@enable_whole_ban.handle()
async def handle_enable_whole_ban(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    await bot.set_group_whole_ban(group_id=group_id, enable=True)
    await enable_whole_ban.finish(reply_msg(event, "✅ 已开启全体禁言"))


@disable_whole_ban.handle()
async def handle_disable_whole_ban(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    await bot.set_group_whole_ban(group_id=group_id, enable=False)
    await disable_whole_ban.finish(reply_msg(event, "✅ 已解除全体禁言"))


@ban_user.handle()
async def handle_ban_user(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = extract_at_user(event)
    if not user_id:
        await ban_user.finish(reply_msg(event, "请@要禁言的用户"))
    
    text = args.extract_plain_text().strip()
    duration = 60
    
    if text:
        match = re.match(r"(\d+)([smhd]?)", text)
        if match:
            num = int(match.group(1))
            unit = match.group(2) or "m"
            unit_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            duration = num * unit_map.get(unit, 60)
    
    group_id = event.group_id
    await bot.set_group_ban(group_id=group_id, user_id=user_id, duration=duration)
    await ban_user.finish(reply_msg(event, f"✅ 已禁言用户 {duration} 秒"))


@unban_user.handle()
async def handle_unban_user(bot: Bot, event: GroupMessageEvent):
    user_id = extract_at_user(event)
    if not user_id:
        await unban_user.finish(reply_msg(event, "请@要解除禁言的用户"))
    
    group_id = event.group_id
    await bot.set_group_ban(group_id=group_id, user_id=user_id, duration=0)
    await unban_user.finish(reply_msg(event, "✅ 已解除禁言"))


@recall_by_at.handle()
async def handle_recall_by_at(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = extract_at_user(event)
    if not user_id:
        await recall_by_at.finish(reply_msg(event, "请@要撤回消息的用户"))
    
    group_id = event.group_id
    
    text = args.extract_plain_text().strip()
    count = 1
    if text:
        try:
            count = int(text)
        except ValueError:
            pass
    
    history = group_message_history.get(group_id, [])
    user_messages = [msg for msg in history if msg["user_id"] == user_id]
    
    recalled = 0
    for msg in user_messages[-count:]:
        try:
            await bot.delete_msg(message_id=msg["message_id"])
            recalled += 1
        except Exception:
            pass
    
    await recall_by_at.finish(reply_msg(event, f"✅ 已撤回 {recalled} 条消息"))


@recall_by_keyword.handle()
async def handle_recall_by_keyword(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await recall_by_keyword.finish(reply_msg(event, "请提供关键词"))
    
    group_id = event.group_id
    history = group_message_history.get(group_id, [])
    
    recalled = 0
    for msg in history:
        if keyword in msg.get("raw_message", ""):
            try:
                await bot.delete_msg(message_id=msg["message_id"])
                recalled += 1
            except Exception:
                pass
    
    await recall_by_keyword.finish(reply_msg(event, f"✅ 已撤回包含关键词「{keyword}」的 {recalled} 条消息"))


@recall_recent.handle()
async def handle_recall_recent(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    count = 1
    if text:
        try:
            count = int(text)
        except ValueError:
            pass
    
    group_id = event.group_id
    history = group_message_history.get(group_id, [])
    
    recalled = 0
    for msg in history[-count:]:
        try:
            await bot.delete_msg(message_id=msg["message_id"])
            recalled += 1
        except Exception:
            pass
    
    await recall_recent.finish(reply_msg(event, f"✅ 已撤回最近 {recalled} 条消息"))


@ban_list.handle()
async def handle_ban_list(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    
    try:
        member_list = await bot.get_group_member_list(group_id=group_id)
        banned_users = [m for m in member_list if m.get("shut_up_timestamp", 0) > 0]
        
        if not banned_users:
            await ban_list.finish(reply_msg(event, "当前没有禁言用户"))
        
        lines = ["禁言列表："]
        now = datetime.now()
        for user in banned_users:
            shut_time = user.get("shut_up_timestamp", 0)
            remaining = shut_time - int(now.timestamp())
            if remaining > 0:
                minutes = remaining // 60
                lines.append(f"• {user.get('card') or user.get('nickname', '未知')} - 剩余 {minutes} 分钟")
        
        await ban_list.finish(reply_msg(event, "\n".join(lines)))
    except FinishedException:
        raise
    except Exception as e:
        await ban_list.finish(reply_msg(event, f"获取禁言列表失败: {e}"))


@unban_all.handle()
async def handle_unban_all(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    
    try:
        member_list = await bot.get_group_member_list(group_id=group_id)
        unbanned = 0
        for member in member_list:
            if member.get("shut_up_timestamp", 0) > 0:
                try:
                    await bot.set_group_ban(group_id=group_id, user_id=member["user_id"], duration=0)
                    unbanned += 1
                except Exception:
                    pass
        
        await unban_all.finish(reply_msg(event, f"✅ 已解除 {unbanned} 人的禁言"))
    except FinishedException:
        raise
    except Exception as e:
        await unban_all.finish(reply_msg(event, f"操作失败: {e}"))


@kick_user.handle()
async def handle_kick_user(bot: Bot, event: GroupMessageEvent):
    user_id = extract_at_user(event)
    if not user_id:
        await kick_user.finish(reply_msg(event, "请@要踢出的用户"))
    
    group_id = event.group_id
    
    try:
        await bot.set_group_kick(group_id=group_id, user_id=user_id, reject_add_request=False)
        await kick_user.finish(reply_msg(event, "✅ 已踢出该用户"))
    except FinishedException:
        raise
    except Exception as e:
        await kick_user.finish(reply_msg(event, f"踢出失败: {e}"))


@check_never_speak.handle()
async def handle_check_never_speak(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    
    try:
        member_list = await bot.get_group_member_list(group_id=group_id)
        never_speak_users = [m for m in member_list if m.get("last_speak_time", 0) == 0]
        
        if not never_speak_users:
            await check_never_speak.finish(reply_msg(event, "没有从未发言的用户"))
        
        lines = [f"从未发言用户列表（共 {len(never_speak_users)} 人）："]
        for i, user in enumerate(never_speak_users[:20], 1):
            name = user.get("card") or user.get("nickname", "未知")
            lines.append(f"{i}. {name} (QQ: {user['user_id']})")
        
        if len(never_speak_users) > 20:
            lines.append(f"... 还有 {len(never_speak_users) - 20} 人")
        
        await check_never_speak.finish(reply_msg(event, "\n".join(lines)))
    except FinishedException:
        raise
    except Exception as e:
        await check_never_speak.finish(reply_msg(event, f"获取失败: {e}"))


@kick_never_speak.handle()
async def handle_kick_never_speak(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    
    try:
        member_list = await bot.get_group_member_list(group_id=group_id)
        never_speak_users = [m for m in member_list if m.get("last_speak_time", 0) == 0]
        
        kicked = 0
        for user in never_speak_users:
            try:
                await bot.set_group_kick(group_id=group_id, user_id=user["user_id"], reject_add_request=False)
                kicked += 1
            except Exception:
                pass
        
        await kick_never_speak.finish(reply_msg(event, f"✅ 已踢出 {kicked} 名从未发言用户"))
    except FinishedException:
        raise
    except Exception as e:
        await kick_never_speak.finish(reply_msg(event, f"操作失败: {e}"))


@set_admin.handle()
async def handle_set_admin(bot: Bot, event: GroupMessageEvent):
    user_id = extract_at_user(event)
    if not user_id:
        await set_admin.finish(reply_msg(event, "请@要设置管理员的用户"))
    
    group_id = event.group_id
    
    try:
        await bot.set_group_admin(group_id=group_id, user_id=user_id, enable=True)
        await set_admin.finish(reply_msg(event, "✅ 已设置该用户为管理员"))
    except FinishedException:
        raise
    except Exception as e:
        await set_admin.finish(reply_msg(event, f"设置失败: {e}"))


@unset_admin.handle()
async def handle_unset_admin(bot: Bot, event: GroupMessageEvent):
    user_id = extract_at_user(event)
    if not user_id:
        await unset_admin.finish(reply_msg(event, "请@要取消管理员的用户"))
    
    group_id = event.group_id
    
    try:
        await bot.set_group_admin(group_id=group_id, user_id=user_id, enable=False)
        await unset_admin.finish(reply_msg(event, "✅ 已取消该用户的管理员身份"))
    except FinishedException:
        raise
    except Exception as e:
        await unset_admin.finish(reply_msg(event, f"操作失败: {e}"))


@set_title.handle()
async def handle_set_title(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = extract_at_user(event)
    if not user_id:
        await set_title.finish(reply_msg(event, "请@要设置头衔的用户"))
    
    title = args.extract_plain_text().strip()
    if not title:
        await set_title.finish(reply_msg(event, "请提供头衔内容"))
    
    group_id = event.group_id
    
    try:
        await bot.set_group_special_title(group_id=group_id, user_id=user_id, special_title=title)
        await set_title.finish(reply_msg(event, f"✅ 已设置头衔：{title}"))
    except FinishedException:
        raise
    except Exception as e:
        await set_title.finish(reply_msg(event, f"设置失败: {e}"))


@clear_screen.handle()
async def handle_clear_screen(bot: Bot, event: GroupMessageEvent):
    await clear_screen.finish(reply_msg(event, "✅ 已清屏"))


@send_notice.handle()
async def handle_send_notice(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    notice_text = args.extract_plain_text().strip()
    if not notice_text:
        await send_notice.finish(reply_msg(event, "请提供公告内容"))
    
    group_id = event.group_id
    
    try:
        await bot.call_api("_send_group_notice", group_id=group_id, content=notice_text)
        await send_notice.finish(reply_msg(event, "✅ 群公告已发布"))
    except FinishedException:
        raise
    except Exception:
        try:
            await bot.send_group_msg(group_id=group_id, message=f"📢 公告\n\n{notice_text}")
            await send_notice.finish(reply_msg(event, "✅ 已通过消息发送公告"))
        except FinishedException:
            raise
        except Exception as e:
            await send_notice.finish(reply_msg(event, f"发送公告失败: {e}"))


message_collector = on_message(priority=99, block=False)


@message_collector.handle()
async def collect_message(event: GroupMessageEvent):
    group_id = event.group_id
    
    if group_id not in group_message_history:
        group_message_history[group_id] = []
    
    now = int(time_module.time())
    group_message_history[group_id] = [
        msg for msg in group_message_history[group_id]
        if now - msg["time"] <= 120
    ]
    
    group_message_history[group_id].append({
        "message_id": event.message_id,
        "user_id": event.user_id,
        "raw_message": event.raw_message,
        "time": event.time
    })
    
    if len(group_message_history[group_id]) > 100:
        group_message_history[group_id] = group_message_history[group_id][-100:]
    
    log_manager.log_message(
        direction="receive",
        user_id=event.user_id,
        group_id=group_id,
        message=event.raw_message
    )


@on_bot_connect
async def on_bot_connect(bot: Bot):
    log_manager.log_connection("connected", f"OneBot connected: {bot.self_id}")
    try:
        groups = await bot.get_group_list()
        added, removed = config_manager.sync_group_list(groups)
        parts = []
        if added > 0:
            parts.append(f"新增 {added} 个群")
        if removed > 0:
            parts.append(f"移除 {removed} 个已退出的群")
        if parts:
            log_manager.log_connection("synced", f"同步群列表完成，{', '.join(parts)}")
        else:
            log_manager.log_connection("synced", "同步群列表完成，无变更")
    except Exception as e:
        log_manager.log_connection("error", f"同步群列表失败: {e}")


@on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    log_manager.log_connection("disconnected", f"OneBot disconnected: {bot.self_id}")


hot_reload = on_command("热重启", priority=1, block=True, permission=SUPERUSER)


@hot_reload.handle()
async def handle_hot_reload(bot: Bot, event: GroupMessageEvent):
    from core.plugin_loader import reload_plugin

    plugin_names = [
        "group_admin",
        "group_verify",
        "group_newcomer",
        "group_checkin",
        "group_stats",
        "group_notify",
        "group_owner",
    ]

    reloaded = []
    failed = []

    for name in plugin_names:
        try:
            success = reload_plugin(name)
            if success:
                reloaded.append(name)
            else:
                failed.append(name)
        except Exception as e:
            failed.append(f"{name}({e})")
            log_manager.log_error("hot_reload", f"Failed to reload {name}: {e}")

    config_manager.load()

    msg_parts = ["🔄 热重启完成"]
    if reloaded:
        msg_parts.append(f"✅ 重载成功：{', '.join(reloaded)}")
    if failed:
        msg_parts.append(f"❌ 重载失败：{', '.join(failed)}")

    log_manager.log_notice("hot_reload", f"Hot reload completed: {len(reloaded)} success, {len(failed)} failed")
    await hot_reload.finish(reply_msg(event, "\n".join(msg_parts)))


restart_framework = on_command("重启框架", priority=1, block=True, permission=SUPERUSER)


@restart_framework.handle()
async def handle_restart_framework(bot: Bot, event: GroupMessageEvent):
    await restart_framework.send(reply_msg(event, "🔄 框架即将重启，请稍候..."))
    log_manager.log_notice("restart_framework", f"Superuser {event.user_id} triggered framework restart from group {event.group_id}")
    threading.Thread(target=_do_restart, daemon=True).start()


def _do_restart():
    threading.Event().wait(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ==================== 菜单注册 ====================
_GROUP_ADMIN_MENU_ITEMS = {
    "授权群聊": "🔧 授权群聊",
    "查看授权": "🔧 查看授权",
    "解除授权": "🔧 解除授权",
    "分群开机": "🔧 分群开机",
    "分群关机": "🔧 分群关机",
    "打开菜单": "🔧 打开菜单",
    "关闭菜单": "🔧 关闭菜单",
    "开启全体禁言": "🔧 开启全体禁言",
    "解除全体禁言": "🔧 解除全体禁言",
    "禁言": "🔧 禁言",
    "解除禁言": "🔧 解除禁言",
    "禁言列表": "🔧 禁言列表",
    "全部解禁": "🔧 全部解禁",
    "撤回": "🔧 撤回",
    "撤回关键词": "🔧 撤回关键词",
    "撤回最近": "🔧 撤回最近",
    "踢出": "🔧 踢出",
    "查看从未发言": "🔧 查看从未发言",
    "踢出从未发言": "🔧 踢出从未发言",
    "上群管": "🔧 上群管",
    "下群管": "🔧 下群管",
    "设置头衔": "🔧 设置头衔",
    "清屏": "🔧 清屏",
    "发送公告": "🔧 发送公告",
    "热重启": "🔧 热重启",
    "重启框架": "🔧 重启框架",
}

for _item_name, _text in _GROUP_ADMIN_MENU_ITEMS.items():
    menu_registry.register(
        category="群管理",
        item_name=_item_name,
        text=_text,
        category_title="🔧◇━群管理━◇🔧",
        category_trigger="群管理",
        category_description="授权·禁言·撤回·踢人·群管设置",
    )
