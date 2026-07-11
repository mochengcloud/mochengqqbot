import json
import random
import threading
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

from core import on_command, CommandArg, GROUP_ADMIN, GROUP_OWNER, SUPERUSER
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class CheckinDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "checkin_data.json")
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Dict[str, Any]]] = None
        self._lock = threading.Lock()
        self._dirty = False
        self._save_timer: Optional[threading.Timer] = None
        self._save_delay = 3.0
        self._save_threshold = 30
        self._update_count = 0
        self._ranking_cache: Dict[str, List[tuple]] = {}
        self._rank_valid = False

    def _ensure_loaded(self):
        if self.data is None:
            self.load()

    def load(self) -> None:
        if self.data_path.exists():
            with open(self.data_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {}
            self.save()

    def _invalidate_cache(self):
        self._rank_valid = False
        self._ranking_cache.clear()

    def _mark_dirty(self):
        self._invalidate_cache()
        self._dirty = True
        self._update_count += 1
        if self._update_count >= self._save_threshold:
            self.save()
            return
        if self._save_timer and self._save_timer.is_alive():
            return
        self._save_timer = threading.Timer(self._save_delay, self._flush)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _flush(self):
        if self._dirty:
            self.save()

    def save(self) -> None:
        with self._lock:
            self._dirty = False
            self._update_count = 0
            if self._save_timer and self._save_timer.is_alive():
                self._save_timer.cancel()
                self._save_timer = None
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_user_data(self, group_id: int, user_id: int) -> Dict[str, Any]:
        self._ensure_loaded()
        gid = str(group_id)
        uid = str(user_id)
        if gid not in self.data:
            self.data[gid] = {}
        if uid not in self.data[gid]:
            self.data[gid][uid] = {
                "points": 0,
                "total_checkins": 0,
                "consecutive_days": 0,
                "max_consecutive_days": 0,
                "last_checkin_date": ""
            }
        return self.data[gid][uid]

    def update_user_data(self, group_id: int, user_id: int, data: Dict[str, Any]) -> None:
        self._ensure_loaded()
        gid = str(group_id)
        uid = str(user_id)
        if gid not in self.data:
            self.data[gid] = {}
        self.data[gid][uid] = data
        self._mark_dirty()

    def _ensure_ranking(self, group_id: int):
        self._ensure_loaded()
        gid = str(group_id)
        if gid not in self._ranking_cache:
            if gid not in self.data:
                self._ranking_cache[gid] = []
            else:
                self._ranking_cache[gid] = sorted(
                    self.data[gid].items(),
                    key=lambda x: x[1].get("points", 0),
                    reverse=True
                )

    def get_user_rank(self, group_id: int, user_id: int) -> int:
        gid = str(group_id)
        uid = str(user_id)
        self._ensure_ranking(group_id)
        for i, (u, _) in enumerate(self._ranking_cache[gid], 1):
            if u == uid:
                return i
        return 0

    def get_group_ranking(self, group_id: int, limit: int = 10) -> List[tuple]:
        self._ensure_ranking(group_id)
        return self._ranking_cache.get(str(group_id), [])[:limit]


checkin_data = CheckinDataManager()

checkin_cmd = on_command("签到", priority=1, block=True)
checkin_rank = on_command("签到排行", priority=1, block=True)

enable_checkin = on_command("开启签到", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_checkin = on_command("关闭签到", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_checkin_like = on_command("开启签到送赞", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_checkin_like = on_command("关闭签到送赞", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

set_checkin_reward = on_command("设置签到奖励", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_checkin_penalty = on_command("开启签到惩罚", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_checkin_penalty = on_command("关闭签到惩罚", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_penalty_deduction = on_command("设置惩罚扣除", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

enable_low_points_block = on_command("开启积分过低禁签", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_low_points_block = on_command("关闭积分过低禁签", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
set_low_points_threshold = on_command("设置积分过低阈值", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@checkin_cmd.handle()
async def handle_checkin(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "签到系统"):
        return

    checkin_config = config_manager.get_checkin_config(group_id)
    if not checkin_config.get("enabled", False):
        return

    user_data = checkin_data.get_user_data(group_id, user_id)
    today = date.today()
    yesterday = today - timedelta(days=1)

    low_points_block = checkin_config.get("low_points_block_enabled", False)
    low_points_threshold = checkin_config.get("low_points_threshold", 0)
    if low_points_block and user_data["points"] < low_points_threshold:
        await checkin_cmd.finish(reply_msg(event, f"❌ 你的积分过低（当前：{user_data['points']}），无法签到\n积分门槛：{low_points_threshold}"))

    last_date_str = user_data.get("last_checkin_date", "")
    if last_date_str:
        try:
            last_date = date.fromisoformat(last_date_str)
        except ValueError:
            last_date = None
    else:
        last_date = None

    if last_date == today:
        await checkin_cmd.finish(reply_msg(event, "❌ 你今天已经签到过了，明天再来吧！"))

    penalty_info = ""
    if last_date == yesterday:
        user_data["consecutive_days"] += 1
    else:
        if user_data["consecutive_days"] > 0 and checkin_config.get("penalty_enabled", False):
            deduction = checkin_config.get("penalty_deduction", 5)
            old_points = user_data["points"]
            user_data["points"] = max(0, user_data["points"] - deduction)
            actual_deduction = old_points - user_data["points"]
            if actual_deduction > 0:
                penalty_info = f"\n⚠️ 断签惩罚：-{actual_deduction}积分"
        user_data["consecutive_days"] = 1

    if user_data["consecutive_days"] > user_data.get("max_consecutive_days", 0):
        user_data["max_consecutive_days"] = user_data["consecutive_days"]

    reward_min = checkin_config.get("reward_min", 1)
    reward_max = checkin_config.get("reward_max", 10)
    reward = random.randint(reward_min, reward_max)
    user_data["points"] += reward
    user_data["total_checkins"] += 1
    user_data["last_checkin_date"] = today.isoformat()

    checkin_data.update_user_data(group_id, user_id, user_data)

    rank = checkin_data.get_user_rank(group_id, user_id)

    if checkin_config.get("send_like", False):
        try:
            await bot.send_like(user_id=user_id, times=1)
        except Exception as e:
            log_manager.log_error("checkin_like", f"Failed to send like to {user_id}: {e}")

    msg = (
        f"🍃 签到成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"🎁 获得积分：{reward}\n"
        f"💰 当前积分：{user_data['points']}\n"
        f"📅 连续签到：{user_data['consecutive_days']}天\n"
        f"🏆 最高连续：{user_data['max_consecutive_days']}天\n"
        f"📊 累计签到：{user_data['total_checkins']}次\n"
        f"🏅 签到排名：第{rank}名\n"
        f"━━━━━━━━━━━━━"
    )
    if penalty_info:
        msg = msg.replace("━━━━━━━━━━━━━", penalty_info, 1)

    log_manager.log_notice("checkin", f"User {user_id} checked in group {group_id}, reward: {reward}")
    await checkin_cmd.finish(reply_msg(event, msg))


@checkin_rank.handle()
async def handle_checkin_rank(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "签到系统"):
        return

    checkin_config = config_manager.get_checkin_config(group_id)
    if not checkin_config.get("enabled", False):
        await checkin_rank.finish(reply_msg(event, "本群签到功能未开启"))

    ranking = checkin_data.get_group_ranking(group_id, limit=10)

    if not ranking:
        await checkin_rank.finish(reply_msg(event, "暂无签到数据"))

    lines = ["🏅 签到积分排行榜", "━━━━━━━━━━━━━"]

    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, data) in enumerate(ranking, 1):
        medal = medals[i - 1] if i <= 3 else f"  {i}."
        points = data.get("points", 0)
        consecutive = data.get("consecutive_days", 0)

        nickname = uid
        try:
            member_info = await bot.get_group_member_info(group_id=group_id, user_id=int(uid))
            nickname = member_info.get("card") or member_info.get("nickname", uid)
        except Exception:
            pass

        lines.append(f"{medal} {nickname} — {points}积分 (连续{consecutive}天)")

    lines.append("━━━━━━━━━━━━━")

    await checkin_rank.finish(reply_msg(event, "\n".join(lines)))


@enable_checkin.handle()
async def handle_enable_checkin(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_enabled(group_id, True)
    await enable_checkin.finish(reply_msg(event, "✅ 签到功能已开启"))


@disable_checkin.handle()
async def handle_disable_checkin(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_enabled(group_id, False)
    await disable_checkin.finish(reply_msg(event, "❌ 签到功能已关闭"))


@enable_checkin_like.handle()
async def handle_enable_checkin_like(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_send_like(group_id, True)
    await enable_checkin_like.finish(reply_msg(event, "✅ 签到送赞已开启"))


@disable_checkin_like.handle()
async def handle_disable_checkin_like(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_send_like(group_id, False)
    await disable_checkin_like.finish(reply_msg(event, "❌ 签到送赞已关闭"))


@set_checkin_reward.handle()
async def handle_set_checkin_reward(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_checkin_reward.finish(reply_msg(event, "请提供奖励范围，例如：设置签到奖励1-10"))

    try:
        parts = text.split("-")
        if len(parts) != 2:
            raise ValueError
        min_val = int(parts[0].strip())
        max_val = int(parts[1].strip())
        if min_val < 1 or max_val < 1 or min_val > max_val:
            raise ValueError
    except ValueError:
        await set_checkin_reward.finish(reply_msg(event, "❌ 格式错误，请使用：设置签到奖励X-Y（X和Y为正整数，X≤Y）"))

    group_id = event.group_id
    config_manager.set_checkin_reward(group_id, min_val, max_val)
    await set_checkin_reward.finish(reply_msg(event, f"✅ 签到奖励已设置为 {min_val}-{max_val} 积分"))


@enable_checkin_penalty.handle()
async def handle_enable_checkin_penalty(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_penalty_enabled(group_id, True)
    await enable_checkin_penalty.finish(reply_msg(event, "✅ 签到惩罚已开启（断签将扣除积分）"))


@disable_checkin_penalty.handle()
async def handle_disable_checkin_penalty(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_penalty_enabled(group_id, False)
    await disable_checkin_penalty.finish(reply_msg(event, "❌ 签到惩罚已关闭"))


@set_penalty_deduction.handle()
async def handle_set_penalty_deduction(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_penalty_deduction.finish(reply_msg(event, "请提供扣除积分数，例如：设置惩罚扣除5"))
    try:
        deduction = int(text)
        if deduction < 1:
            raise ValueError
    except ValueError:
        await set_penalty_deduction.finish(reply_msg(event, "❌ 扣除积分数必须为正整数"))

    group_id = event.group_id
    config_manager.set_checkin_penalty_deduction(group_id, deduction)
    await set_penalty_deduction.finish(reply_msg(event, f"✅ 断签惩罚扣除已设置为 {deduction} 积分"))


@enable_low_points_block.handle()
async def handle_enable_low_points_block(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_low_points_block(group_id, True)
    checkin_config = config_manager.get_checkin_config(group_id)
    threshold = checkin_config.get("low_points_threshold", 0)
    if threshold == 0:
        await enable_low_points_block.finish(reply_msg(event, "✅ 积分过低禁签已开启\n⚠️ 当前阈值为0，请使用「设置积分过低阈值X」设置阈值"))
    await enable_low_points_block.finish(reply_msg(event, f"✅ 积分过低禁签已开启（当前阈值：{threshold}）"))


@disable_low_points_block.handle()
async def handle_disable_low_points_block(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config_manager.set_checkin_low_points_block(group_id, False)
    await disable_low_points_block.finish(reply_msg(event, "❌ 积分过低禁签已关闭"))


@set_low_points_threshold.handle()
async def handle_set_low_points_threshold(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await set_low_points_threshold.finish(reply_msg(event, "请提供积分阈值，例如：设置积分过低阈值10"))
    try:
        threshold = int(text)
        if threshold < 0:
            raise ValueError
    except ValueError:
        await set_low_points_threshold.finish(reply_msg(event, "❌ 积分阈值必须为非负整数"))

    group_id = event.group_id
    config_manager.set_checkin_low_points_threshold(group_id, threshold)
    await set_low_points_threshold.finish(reply_msg(event, f"✅ 积分过低阈值已设置为 {threshold}"))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_GROUP_CHECKIN_MENU_ITEMS = {
    "签到": "📅 签到",
    "签到排行": "📅 签到排行",
    "开启签到": "✅ 开启签到",
    "关闭签到": "❌ 关闭签到",
    "开启签到送赞": "✅ 开启签到送赞",
    "关闭签到送赞": "❌ 关闭签到送赞",
    "开启签到惩罚": "✅ 开启签到惩罚",
    "关闭签到惩罚": "❌ 关闭签到惩罚",
    "开启积分过低禁签": "✅ 开启积分过低禁签",
    "关闭积分过低禁签": "❌ 关闭积分过低禁签",
    "设置签到奖励": "📅 设置签到奖励",
    "设置惩罚扣除": "📅 设置惩罚扣除",
    "设置积分过低阈值": "📅 设置积分过低阈值",
}

for _item_name, _text in _GROUP_CHECKIN_MENU_ITEMS.items():
    menu_registry.register(
        category="签到功能",
        item_name=_item_name,
        text=_text,
        category_title="📅◇━签到功能━◇📅",
        category_trigger="签到功能",
        category_description="每日签到·排行·奖励·惩罚配置",
    )
