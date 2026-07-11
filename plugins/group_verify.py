import asyncio
import io
import os
import random
import string
import tempfile
import time as time_module
from typing import Dict, Any

from core import (
    on_command,
    on_notice,
    on_message,
    get_driver,
    GROUP_ADMIN,
    GROUP_OWNER,
    SUPERUSER,
    FinishedException,
    CommandArg,
    T_State,
)
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
    NoticeEvent,
    GroupIncreaseNoticeEvent,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

verify_state: Dict[str, Dict[str, Dict[str, Any]]] = {}
_verified_users: Dict[str, float] = {}

enable_verify = on_command("开启进群验证", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_verify = on_command("关闭进群验证", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_timeout_kick = on_command("开启超时踢出", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_timeout_kick = on_command("关闭超时踢出", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

use_number_mode = on_command("使用数字验证模式", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
use_speech_mode = on_command("使用发言验证模式", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
use_image_mode = on_command("使用图片验证模式", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

set_verify_time = on_command("设置验证时间", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_welcome_prompt = on_command("设置进群验证提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_success_prompt = on_command("设置验证成功提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_timeout_prompt = on_command("设置验证超时提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

group_increase_handler = on_notice(priority=5, block=False)
verify_message_handler = on_message(priority=5, block=False)


def _generate_number_code() -> str:
    return ''.join([str(random.randint(0, 9)) for _ in range(4)])


def _generate_image_code() -> str:
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('L', '')
    return ''.join([random.choice(chars) for _ in range(4)])


def _generate_captcha_image(code: str) -> str:
    if not PIL_AVAILABLE:
        return ""

    width, height = 200, 80
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("msyh.ttc", 40)
        except (IOError, OSError):
            font = ImageFont.load_default()

    for i, ch in enumerate(code):
        x = 20 + i * 42
        y = random.randint(5, 25)
        color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw.text((x, y), ch, fill=color, font=font)

    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

    for _ in range(100):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
        draw.point((x, y), fill=color)

    tmp_dir = tempfile.gettempdir()
    filename = f"captcha_{int(time_module.time() * 1000)}_{random.randint(1000, 9999)}.png"
    filepath = os.path.join(tmp_dir, filename)
    img.save(filepath, 'PNG')

    return filepath


async def _timeout_kick_task(bot: Bot, group_id: int, user_id: int, delay: float, timeout_prompt: str):
    await asyncio.sleep(delay)
    gid = str(group_id)
    uid = str(user_id)
    if gid in verify_state and uid in verify_state[gid]:
        state = verify_state[gid].pop(uid)
        if state.get("task"):
            pass
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {timeout_prompt}")
            )
        except Exception:
            pass
        try:
            await bot.set_group_kick(group_id=group_id, user_id=user_id, reject_add_request=False)
        except Exception:
            pass
        log_manager.log_notice("verify_timeout", f"User {user_id} kicked from group {group_id}")


def _cleanup_verify_state(group_id: int, user_id: int):
    gid = str(group_id)
    uid = str(user_id)
    if gid in verify_state and uid in verify_state[gid]:
        state = verify_state[gid].pop(uid)
        task = state.get("task")
        if task and not task.done():
            task.cancel()
        if gid in verify_state and not verify_state[gid]:
            del verify_state[gid]


@enable_verify.handle()
async def handle_enable_verify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_enabled(group_id, True)
    await enable_verify.finish(reply_msg(event, "✅ 进群验证已开启"))


@disable_verify.handle()
async def handle_disable_verify(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_enabled(group_id, False)
    gid = str(group_id)
    if gid in verify_state:
        for uid, state in list(verify_state[gid].items()):
            task = state.get("task")
            if task and not task.done():
                task.cancel()
        del verify_state[gid]
    await disable_verify.finish(reply_msg(event, "❌ 进群验证已关闭"))


@enable_timeout_kick.handle()
async def handle_enable_timeout_kick(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_timeout_kick(group_id, True)
    await enable_timeout_kick.finish(reply_msg(event, "✅ 超时踢出已开启"))


@disable_timeout_kick.handle()
async def handle_disable_timeout_kick(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_timeout_kick(group_id, False)
    await disable_timeout_kick.finish(reply_msg(event, "❌ 超时踢出已关闭"))


@use_number_mode.handle()
async def handle_use_number_mode(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_mode(group_id, "number")
    await use_number_mode.finish(reply_msg(event, "✅ 已切换为数字验证模式"))


@use_speech_mode.handle()
async def handle_use_speech_mode(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_verify_mode(group_id, "speech")
    await use_speech_mode.finish(reply_msg(event, "✅ 已切换为发言验证模式"))


@use_image_mode.handle()
async def handle_use_image_mode(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not PIL_AVAILABLE:
        await use_image_mode.finish(reply_msg(event, "❌ 图片验证模式需要安装 Pillow 库（pip install Pillow）"))
    config_manager.set_verify_mode(group_id, "image")
    await use_image_mode.finish(reply_msg(event, "✅ 已切换为图片验证模式"))


@set_verify_time.handle()
async def handle_set_verify_time(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_verify_time.finish(reply_msg(event, "请提供验证时间（分钟），例如：设置验证时间5"))
    try:
        minutes = int(text)
        if minutes < 1:
            raise ValueError
    except ValueError:
        await set_verify_time.finish(reply_msg(event, "❌ 验证时间必须为正整数（分钟）"))

    group_id = event.group_id
    config_manager.set_verify_timeout_minutes(group_id, minutes)
    await set_verify_time.finish(reply_msg(event, f"✅ 验证时间已设置为 {minutes} 分钟"))


@set_welcome_prompt.handle()
async def handle_set_welcome_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_welcome_prompt.finish(reply_msg(event, "请提供进群验证提示内容，例如：设置进群验证提示欢迎进群，请完成验证"))
    group_id = event.group_id
    config_manager.set_verify_welcome_prompt(group_id, text)
    await set_welcome_prompt.finish(reply_msg(event, f"✅ 进群验证提示已设置为：{text}"))


@set_success_prompt.handle()
async def handle_set_success_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_success_prompt.finish(reply_msg(event, "请提供验证成功提示内容，例如：设置验证成功提示验证通过，欢迎加入"))
    group_id = event.group_id
    config_manager.set_verify_success_prompt(group_id, text)
    await set_success_prompt.finish(reply_msg(event, f"✅ 验证成功提示已设置为：{text}"))


@set_timeout_prompt.handle()
async def handle_set_timeout_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_timeout_prompt.finish(reply_msg(event, "请提供验证超时提示内容，例如：设置验证超时提示验证超时，你已被移出"))
    group_id = event.group_id
    config_manager.set_verify_timeout_prompt(group_id, text)
    await set_timeout_prompt.finish(reply_msg(event, f"✅ 验证超时提示已设置为：{text}"))


async def _send_verify_prompt(bot: Bot, group_id: int, user_id: int, verify_config: dict) -> bool:
    gid = str(group_id)
    uid = str(user_id)

    # 已成功发送过提示,不重复发送
    if gid in verify_state and uid in verify_state[gid]:
        existing = verify_state[gid][uid]
        if existing.get("prompt_sent", False):
            return True

    mode = verify_config.get("mode", "number")
    welcome_prompt = verify_config.get("welcome_prompt", "欢迎加入本群！请完成验证以继续")
    timeout_kick = verify_config.get("timeout_kick", False)
    timeout_minutes = verify_config.get("timeout_minutes", 5)
    timeout_prompt = verify_config.get("timeout_prompt", "⏰ 验证超时，你已被移出群聊")

    # 重新发送时复用已有验证码,避免验证码不一致
    existing_state = verify_state.get(gid, {}).get(uid, {})
    code = existing_state.get("code", "")

    msg_parts = [f"[CQ:at,qq={user_id}] {welcome_prompt}\n"]

    if mode == "number":
        if not code:
            code = _generate_number_code()
        msg_parts.append(f"请在群内发送验证码：{code}")
    elif mode == "speech":
        msg_parts.append("请在群内发送任意消息完成验证")
    elif mode == "image":
        if not PIL_AVAILABLE:
            if not code:
                code = _generate_number_code()
            msg_parts.append(f"图片验证不可用，请发送验证码：{code}")
        else:
            if not code:
                code = _generate_image_code()
            image_path = _generate_captcha_image(code)
            if image_path:
                msg_parts.append("请输入图片中的验证码：")
                msg_parts.append(f"[CQ:image,file=file:///{image_path}]")
            else:
                if not code:
                    code = _generate_number_code()
                msg_parts.append(f"图片生成失败，请发送验证码：{code}")

    msg_text = "\n".join(msg_parts)

    if gid not in verify_state:
        verify_state[gid] = {}

    # 取消原有的超时任务(如有)
    if uid in verify_state[gid]:
        old_task = verify_state[gid][uid].get("task")
        if old_task and not old_task.done():
            old_task.cancel()

    task = None
    if timeout_kick:
        delay = timeout_minutes * 60
        task = asyncio.create_task(
            _timeout_kick_task(bot, group_id, user_id, delay, timeout_prompt)
        )

    verify_state[gid][uid] = {
        "code": code,
        "mode": mode,
        "join_time": time_module.time(),
        "task": task,
        "prompt_sent": False
    }

    try:
        await bot.send_group_msg(group_id=group_id, message=Message(msg_text))
        verify_state[gid][uid]["prompt_sent"] = True
        return True
    except Exception as e:
        log_manager.log_error("verify_send", str(e))
        return False


@group_increase_handler.handle()
async def handle_group_increase(bot: Bot, event: NoticeEvent):
    if not isinstance(event, GroupIncreaseNoticeEvent):
        return

    group_id = event.group_id
    user_id = event.user_id

    if user_id == int(bot.self_id):
        return

    verify_config = config_manager.get_verify_config(group_id)
    if not verify_config.get("enabled", False):
        return

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "验证系统"):
        return

    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        role = member_info.get("role", "member")
        if role in ("admin", "owner"):
            return
    except Exception:
        pass

    await _send_verify_prompt(bot, group_id, user_id, verify_config)
    log_manager.log_notice("verify_join", f"User {user_id} joined group {group_id}")


@verify_message_handler.handle()
async def handle_verify_message(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    gid = str(group_id)
    uid = str(user_id)

    # 验证仅在进群通知时触发,消息处理只针对已在验证流程中的用户
    if gid not in verify_state or uid not in verify_state[gid]:
        return

    state = verify_state[gid][uid]
    mode = state.get("mode", "number")
    code = state.get("code", "")

    # 如果提示发送失败,重新发送(复用原验证码)
    if not state.get("prompt_sent", True):
        verify_config = config_manager.get_verify_config(group_id)
        await _send_verify_prompt(bot, group_id, user_id, verify_config)
        return

    passed = False

    if mode == "speech":
        passed = True
    elif mode in ("number", "image"):
        user_input = event.raw_message.strip()
        if user_input.upper() == code.upper():
            passed = True

    if passed:
        verify_config = config_manager.get_verify_config(group_id)
        success_prompt = verify_config.get("success_prompt", "✅ 验证通过，欢迎加入！")

        verify_key = f"{gid}_{uid}"
        _verified_users[verify_key] = time_module.time()

        _cleanup_verify_state(group_id, user_id)

        now = time_module.time()
        expired_keys = [k for k, v in _verified_users.items() if now - v > 3600]
        for k in expired_keys:
            del _verified_users[k]

        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"[CQ:at,qq={user_id}] {success_prompt}")
            )
        except Exception:
            pass

        log_manager.log_notice("verify_pass", f"User {user_id} verified in group {group_id}")
        await verify_message_handler.finish()
    else:
        try:
            await bot.delete_msg(message_id=event.message_id)
        except Exception:
            pass
        await verify_message_handler.finish(reply_msg(event, "❌ 验证码错误，请重新输入"))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_VERIFY_MENU_ITEMS = {
    "开启进群验证": "✅ 开启进群验证",
    "关闭进群验证": "❌ 关闭进群验证",
    "开启超时踢出": "✅ 开启超时踢出",
    "关闭超时踢出": "❌ 关闭超时踢出",
    "使用数字验证模式": "🔐 使用数字验证模式",
    "使用发言验证模式": "🔐 使用发言验证模式",
    "使用图片验证模式": "🔐 使用图片验证模式",
    "设置验证时间": "🔐 设置验证时间",
    "设置进群验证提示": "🔐 设置进群验证提示",
    "设置验证成功提示": "🔐 设置验证成功提示",
    "设置验证超时提示": "🔐 设置验证超时提示",
}

for _item_name, _text in _VERIFY_MENU_ITEMS.items():
    menu_registry.register(
        category="进群验证",
        item_name=_item_name,
        text=_text,
        category_title="🔐◇━进群验证━◇🔐",
        category_trigger="进群验证",
        category_description="数字/发言/图片验证·超时踢出",
    )
