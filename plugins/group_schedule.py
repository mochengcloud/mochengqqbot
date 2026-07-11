import asyncio
import re
from datetime import datetime
from typing import Any, Dict, Optional

from core import get_driver, get_bot, on_command, on_startup
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
)
from core import GROUP_ADMIN, GROUP_OWNER, SUPERUSER
from core import CommandArg
from core.menu_registry import menu_registry

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg


# ============ 检查函数 ============
def _check_enabled(group_id: int) -> tuple:
    """返回 (通过, 提示消息)"""
    if not config_manager.is_group_enabled(group_id):
        return False, ""
    if not config_manager.is_feature_authorized(group_id, "定时功能"):
        return False, ""
    schedule_config = config_manager.get_schedule_config(group_id)
    if not schedule_config.get("enabled", False):
        return False, "⚠️ 定时功能未开启，管理员请使用「开启定时功能」"
    return True, ""


def _check_base(group_id: int) -> bool:
    """仅检查群开关和授权"""
    if not config_manager.is_group_enabled(group_id):
        return False
    if not config_manager.is_feature_authorized(group_id, "定时功能"):
        return False
    return True


def _parse_time(text: str) -> Optional[tuple]:
    """解析时间文本，返回 (hour, minute) 或 None"""
    text = text.strip()
    # 匹配 "22点30分" "22:30" "22点30" "7点0分" "7:00" 等
    m = re.match(r'(\d{1,2})[点时:：](\d{1,2})分?$', text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    # 匹配 "22点" "7时" 等省略分钟
    m = re.match(r'(\d{1,2})[点时]$', text)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            return hour, 0
    return None


# ============ 定时任务后台循环 ============
_last_executed: Dict[str, datetime] = {}


def _should_execute(task_key: str, now: datetime) -> bool:
    """检查是否应该执行，同一任务60秒内不重复"""
    last = _last_executed.get(task_key)
    if last and (now - last).total_seconds() < 60:
        return False
    _last_executed[task_key] = now
    return True


async def _schedule_loop():
    """后台定时任务循环，每30秒检查一次"""
    await asyncio.sleep(10)  # 启动后等待10秒，确保Bot连接就绪
    while True:
        try:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute

            # 遍历所有群的配置
            group_settings = config_manager.config.get("group_settings", {})
            for group_id_str, settings in group_settings.items():
                try:
                    group_id = int(group_id_str)
                except (ValueError, TypeError):
                    continue

                schedule_config = settings.get("schedule", {})
                if not schedule_config.get("enabled", False):
                    continue

                # 获取Bot实例
                try:
                    bot = get_bot()
                except ValueError:
                    break  # Bot未连接，跳出内层循环等待下次

                # 检查定时禁言
                mute_config = schedule_config.get("mute", {})
                if mute_config.get("enabled", False):
                    mute_hour = mute_config.get("hour", -1)
                    mute_minute = mute_config.get("minute", -1)
                    if current_hour == mute_hour and current_minute == mute_minute:
                        task_key = f"{group_id}_mute"
                        if _should_execute(task_key, now):
                            prompt = mute_config.get("prompt", "")
                            try:
                                if prompt:
                                    await bot.send_group_msg(group_id=group_id, message=prompt)
                                await bot.set_group_whole_ban(group_id=group_id, enable=True)
                                log_manager.log_notice("schedule", f"Auto mute group {group_id} at {mute_hour}:{mute_minute:02d}")
                            except Exception as e:
                                log_manager.log_notice("schedule", f"Failed to mute group {group_id}: {e}")

                # 检查定时解除
                unmute_config = schedule_config.get("unmute", {})
                if unmute_config.get("enabled", False):
                    unmute_hour = unmute_config.get("hour", -1)
                    unmute_minute = unmute_config.get("minute", -1)
                    if current_hour == unmute_hour and current_minute == unmute_minute:
                        task_key = f"{group_id}_unmute"
                        if _should_execute(task_key, now):
                            prompt = unmute_config.get("prompt", "")
                            try:
                                if prompt:
                                    await bot.send_group_msg(group_id=group_id, message=prompt)
                                await bot.set_group_whole_ban(group_id=group_id, enable=False)
                                log_manager.log_notice("schedule", f"Auto unmute group {group_id} at {unmute_hour}:{unmute_minute:02d}")
                            except Exception as e:
                                log_manager.log_notice("schedule", f"Failed to unmute group {group_id}: {e}")

                # 检查定时广播
                for bc in schedule_config.get("broadcasts", []):
                    if not bc.get("enabled", True):
                        continue
                    bc_hour = bc.get("hour", -1)
                    bc_minute = bc.get("minute", -1)
                    if current_hour == bc_hour and current_minute == bc_minute:
                        bc_id = bc.get("id", 0)
                        task_key = f"{group_id}_broadcast_{bc_id}"
                        if _should_execute(task_key, now):
                            content = bc.get("content", "")
                            try:
                                if content:
                                    await bot.send_group_msg(group_id=group_id, message=content)
                                    log_manager.log_notice("schedule", f"Auto broadcast in group {group_id}, id={bc_id}")
                            except Exception as e:
                                log_manager.log_notice("schedule", f"Failed to broadcast in group {group_id}: {e}")

                # 检查整点报时
                chime_config = schedule_config.get("hourly_chime", {})
                if chime_config.get("enabled", False) and current_minute == 0:
                    task_key = f"{group_id}_chime_{current_hour}"
                    if _should_execute(task_key, now):
                        template = chime_config.get("template", "现在是{hour}点整")
                        msg = template.replace("{hour}", str(current_hour))
                        try:
                            await bot.send_group_msg(group_id=group_id, message=msg)
                            log_manager.log_notice("schedule", f"Hourly chime in group {group_id} at {current_hour}:00")
                        except Exception as e:
                            log_manager.log_notice("schedule", f"Failed to chime in group {group_id}: {e}")

        except Exception as e:
            log_manager.log_notice("schedule", f"Schedule loop error: {e}")

        await asyncio.sleep(30)


@on_startup
async def start_scheduler():
    asyncio.create_task(_schedule_loop())


# ============ 查看本群定时任务 ============
view_schedule = on_command("查看本群定时任务", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@view_schedule.handle()
async def handle_view_schedule(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await view_schedule.finish(reply_msg(event, msg))
        return

    schedule_config = config_manager.get_schedule_config(group_id)

    lines = ["📋 本群定时任务", "━━━━━━━━━━━━━"]

    # 禁言任务
    mute_config = schedule_config.get("mute", {})
    if mute_config.get("enabled", False):
        mute_h = mute_config.get("hour", 0)
        mute_m = mute_config.get("minute", 0)
        mute_prompt = mute_config.get("prompt", "")
        lines.append(f"🔇 定时禁言：{mute_h:02d}:{mute_m:02d}")
        if mute_prompt:
            lines.append(f"   💬 提示：{mute_prompt}")
    else:
        lines.append("🔇 定时禁言：未设置")

    # 解除任务
    unmute_config = schedule_config.get("unmute", {})
    if unmute_config.get("enabled", False):
        unmute_h = unmute_config.get("hour", 0)
        unmute_m = unmute_config.get("minute", 0)
        unmute_prompt = unmute_config.get("prompt", "")
        lines.append(f"🔊 定时解除：{unmute_h:02d}:{unmute_m:02d}")
        if unmute_prompt:
            lines.append(f"   💬 提示：{unmute_prompt}")
    else:
        lines.append("🔊 定时解除：未设置")

    # 广播任务
    broadcasts = schedule_config.get("broadcasts", [])
    if broadcasts:
        lines.append("📢 定时广播：")
        for bc in broadcasts:
            bc_h = bc.get("hour", 0)
            bc_m = bc.get("minute", 0)
            bc_id = bc.get("id", 0)
            bc_content = bc.get("content", "")
            bc_status = "✅" if bc.get("enabled", True) else "❌"
            lines.append(f"   {bc_status} [ID:{bc_id}] {bc_h:02d}:{bc_m:02d} - {bc_content}")
    else:
        lines.append("📢 定时广播：无")

    # 整点报时
    chime_config = schedule_config.get("hourly_chime", {})
    chime_status = "✅ 已开启" if chime_config.get("enabled", False) else "❌ 未开启"
    lines.append(f"🕐 整点报时：{chime_status}")

    lines.append("━━━━━━━━━━━━━")
    await view_schedule.finish(reply_msg(event, "\n".join(lines)))


# ============ 清空本群定时任务 ============
clear_schedule = on_command("清空本群定时任务", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@clear_schedule.handle()
async def handle_clear_schedule(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await clear_schedule.finish(reply_msg(event, msg))
        return

    config_manager.clear_schedule(group_id)
    await clear_schedule.finish(reply_msg(event, "✅ 已清空本群所有定时任务"))


# ============ 设置定时禁言时间 ============
set_mute_time = on_command("设置定时禁言时间", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_mute_time.handle()
async def handle_set_mute_time(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_mute_time.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await set_mute_time.finish(reply_msg(event, "格式：设置定时禁言时间 22点30分\n支持格式：22点30分 / 22:30 / 22点"))

    result = _parse_time(text)
    if not result:
        await set_mute_time.finish(reply_msg(event, "❌ 时间格式错误\n支持格式：22点30分 / 22:30 / 22点"))

    hour, minute = result
    config_manager.set_mute_time(group_id, hour, minute)
    await set_mute_time.finish(reply_msg(event, f"✅ 定时禁言已设置\n🔇 禁言时间：{hour:02d}:{minute:02d}"))


# ============ 设置禁言提示 ============
set_mute_prompt = on_command("设置禁言提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_mute_prompt.handle()
async def handle_set_mute_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_mute_prompt.finish(reply_msg(event, msg))
        return

    prompt = args.extract_plain_text().strip()
    if not prompt:
        await set_mute_prompt.finish(reply_msg(event, "格式：设置禁言提示 提示内容\n例如：设置禁言提示 晚安时间到，请保持安静~"))

    config_manager.set_mute_prompt(group_id, prompt)
    await set_mute_prompt.finish(reply_msg(event, f"✅ 禁言提示已设置\n💬 提示内容：{prompt}"))


# ============ 设置定时解除时间 ============
set_unmute_time = on_command("设置定时解除时间", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_unmute_time.handle()
async def handle_set_unmute_time(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_unmute_time.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await set_unmute_time.finish(reply_msg(event, "格式：设置定时解除时间 7点0分\n支持格式：7点0分 / 7:00 / 7点"))

    result = _parse_time(text)
    if not result:
        await set_unmute_time.finish(reply_msg(event, "❌ 时间格式错误\n支持格式：7点0分 / 7:00 / 7点"))

    hour, minute = result
    config_manager.set_unmute_time(group_id, hour, minute)
    await set_unmute_time.finish(reply_msg(event, f"✅ 定时解除已设置\n🔊 解除时间：{hour:02d}:{minute:02d}"))


# ============ 设置解除提示 ============
set_unmute_prompt = on_command("设置解除提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_unmute_prompt.handle()
async def handle_set_unmute_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_unmute_prompt.finish(reply_msg(event, msg))
        return

    prompt = args.extract_plain_text().strip()
    if not prompt:
        await set_unmute_prompt.finish(reply_msg(event, "格式：设置解除提示 提示内容\n例如：设置解除提示 早上好，解除禁言啦~"))

    config_manager.set_unmute_prompt(group_id, prompt)
    await set_unmute_prompt.finish(reply_msg(event, f"✅ 解除提示已设置\n💬 提示内容：{prompt}"))


# ============ 添加定时广播 ============
add_broadcast = on_command("添加定时广播", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@add_broadcast.handle()
async def handle_add_broadcast(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await add_broadcast.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await add_broadcast.finish(reply_msg(event, "格式：添加定时广播 时间 内容\n例如：添加定时广播 12点0分 午餐时间到！"))

    # 解析时间和内容
    parts = text.split(None, 1)
    if len(parts) < 2:
        await add_broadcast.finish(reply_msg(event, "格式：添加定时广播 时间 内容\n例如：添加定时广播 12点0分 午餐时间到！"))

    time_str = parts[0]
    content = parts[1].strip()

    result = _parse_time(time_str)
    if not result:
        await add_broadcast.finish(reply_msg(event, "❌ 时间格式错误\n支持格式：12点0分 / 12:00 / 12点"))

    if not content:
        await add_broadcast.finish(reply_msg(event, "❌ 广播内容不能为空"))

    hour, minute = result
    broadcast_id = config_manager.add_broadcast(group_id, hour, minute, content)
    await add_broadcast.finish(reply_msg(event, f"✅ 定时广播已添加\n🆔 ID：{broadcast_id}\n⏰ 时间：{hour:02d}:{minute:02d}\n📢 内容：{content}"))


# ============ 删除定时广播 ============
del_broadcast = on_command("删除定时广播", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@del_broadcast.handle()
async def handle_del_broadcast(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await del_broadcast.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    try:
        broadcast_id = int(text)
    except ValueError:
        await del_broadcast.finish(reply_msg(event, "请输入广播ID，例如：删除定时广播 1\n使用「查看本群定时任务」查看ID"))

    if config_manager.remove_broadcast(group_id, broadcast_id):
        await del_broadcast.finish(reply_msg(event, f"✅ 广播 [ID:{broadcast_id}] 已删除"))
    else:
        await del_broadcast.finish(reply_msg(event, f"❌ 广播 [ID:{broadcast_id}] 不存在"))


# ============ 开启/关闭整点报时 ============
enable_chime = on_command("开启整点报时", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_chime = on_command("关闭整点报时", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@enable_chime.handle()
async def handle_enable_chime(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await enable_chime.finish(reply_msg(event, msg))
        return

    config_manager.set_hourly_chime(group_id, True)
    await enable_chime.finish(reply_msg(event, "✅ 整点报时已开启"))


@disable_chime.handle()
async def handle_disable_chime(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await disable_chime.finish(reply_msg(event, msg))
        return

    config_manager.set_hourly_chime(group_id, False)
    await disable_chime.finish(reply_msg(event, "❌ 整点报时已关闭"))


# ============ 开启/关闭定时功能 ============
enable_schedule = on_command("开启定时功能", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_schedule = on_command("关闭定时功能", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@enable_schedule.handle()
async def handle_enable_schedule(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_schedule_enabled(group_id, True)
    await enable_schedule.finish(reply_msg(event, "✅ 定时功能已开启"))


@disable_schedule.handle()
async def handle_disable_schedule(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_schedule_enabled(group_id, False)
    await disable_schedule.finish(reply_msg(event, "❌ 定时功能已关闭"))


# ============ 注册菜单 ============
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 定时功能(无子分类)
_SCHEDULE_MENU_ITEMS = {
    "查看本群定时任务": "🌟查看本群定时任务",
    "清空本群定时任务": "🌟清空本群定时任务",
    "设置定时禁言时间": "🌟设置定时禁言时间*点*分",
    "设置禁言提示": "🌟设置禁言提示*",
    "设置定时解除时间": "🌟设置定时解除时间*点*分",
    "设置解除提示": "🌟设置解除提示*",
    "添加定时广播": "🌟添加定时广播X点X分*",
    "删除定时广播": "🌟删除定时广播ID",
    "开启整点报时": "🌟开启整点报时",
    "关闭整点报时": "🌟关闭整点报时",
    "开启定时功能": "🌟开启定时功能",
    "关闭定时功能": "🌟关闭定时功能",
}

for _item_name, _text in _SCHEDULE_MENU_ITEMS.items():
    menu_registry.register(
        category="定时功能",
        item_name=_item_name,
        text=_text,
        category_title="🌱◇━定时功能━◇🌱",
        category_trigger="定时功能",
        category_description="定时禁言·解除·广播·报时",
    )
