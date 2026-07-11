import json
import time as time_module
import threading
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import on_command, on_message, get_driver, on_bot_disconnect
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
)
from core import CommandArg

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class StatsDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "stats_data.json")
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None
        self._lock = threading.Lock()
        self._dirty = False
        self._update_count = 0

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

    def save(self) -> None:
        self._ensure_loaded()
        with self._lock:
            self._cleanup_old_data()
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self._dirty = False
            self._update_count = 0

    def _cleanup_old_data(self, keep_days: int = 35) -> None:
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        keys_to_delete = [k for k in self.data if k < cutoff]
        for k in keys_to_delete:
            del self.data[k]

    def increment(self, group_id: int, user_id: int, date_str: str) -> None:
        self._ensure_loaded()
        gid = str(group_id)
        uid = str(user_id)
        with self._lock:
            if date_str not in self.data:
                self.data[date_str] = {}
            if gid not in self.data[date_str]:
                self.data[date_str][gid] = {}
            if uid not in self.data[date_str][gid]:
                self.data[date_str][gid][uid] = 0
            self.data[date_str][gid][uid] += 1
            self._dirty = True
            self._update_count += 1

        if self._update_count >= 50:
            self.save()

    def get_group_stats(self, group_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        self._ensure_loaded()
        gid = str(group_id)
        total_messages = 0
        user_counts: Dict[str, int] = {}
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        for date_str, groups in self.data.items():
            if start_str <= date_str <= end_str and gid in groups:
                for uid, count in groups[gid].items():
                    total_messages += count
                    user_counts[uid] = user_counts.get(uid, 0) + count

        active_users = len(user_counts)
        most_active_uid = None
        most_active_count = 0
        if user_counts:
            most_active_uid, most_active_count = max(user_counts.items(), key=lambda x: x[1])

        return {
            "total_messages": total_messages,
            "active_users": active_users,
            "most_active_user": most_active_uid,
            "most_active_count": most_active_count,
            "user_counts": dict(user_counts)
        }

    def get_user_stats(self, group_id: int, user_id: int, start_date: date, end_date: date) -> int:
        self._ensure_loaded()
        gid = str(group_id)
        uid = str(user_id)
        total = 0
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        for date_str, groups in self.data.items():
            if start_str <= date_str <= end_str:
                total += groups.get(gid, {}).get(uid, 0)
        return total

    def get_ranking(self, group_id: int, start_date: date, end_date: date, limit: int = 10) -> List[tuple]:
        self._ensure_loaded()
        gid = str(group_id)
        user_counts: Dict[str, int] = {}
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            group_data = self.data.get(date_str, {}).get(gid, {})
            for uid, count in group_data.items():
                user_counts[uid] = user_counts.get(uid, 0) + count
            current += timedelta(days=1)

        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]


stats_data = StatsDataManager()


def _get_today_range():
    today = date.today()
    return today, today


def _get_week_range():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday, today


def _get_month_range():
    today = date.today()
    first_day = today.replace(day=1)
    return first_day, today


async def _get_nickname(bot: Bot, group_id: int, user_id: int) -> str:
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        return member_info.get("card") or member_info.get("nickname", str(user_id))
    except Exception:
        return str(user_id)


def _extract_at_user(event: GroupMessageEvent) -> Optional[int]:
    for seg in event.message:
        if seg.type == "at":
            return int(seg.data.get("qq", 0))
    return None


stats_collector = on_message(priority=98, block=False)

today_group_stats = on_command("查今日群统计", priority=1, block=True)
week_group_stats = on_command("查本周群统计", priority=1, block=True)
month_group_stats = on_command("查本月群统计", priority=1, block=True)

my_stats = on_command("我的发言统计", priority=1, block=True)
user_stats = on_command("查发言统计", priority=1, block=True)

today_ranking = on_command("今日发言排行", priority=1, block=True)
week_ranking = on_command("本周发言排行", priority=1, block=True)
month_ranking = on_command("本月发言排行", priority=1, block=True)


@stats_collector.handle()
async def handle_stats_collect(event: GroupMessageEvent):
    today_str = date.today().isoformat()
    stats_data.increment(event.group_id, event.user_id, today_str)


@today_group_stats.handle()
async def handle_today_group_stats(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_today_range()
    result = stats_data.get_group_stats(group_id, start, end)

    most_active = "暂无"
    if result["most_active_user"]:
        most_active = await _get_nickname(bot, group_id, int(result["most_active_user"]))
        most_active = f"{most_active}（{result['most_active_count']}条）"

    msg = (
        f"📊 今日群统计\n"
        f"━━━━━━━━━━━━━\n"
        f"💬 消息总数：{result['total_messages']}\n"
        f"👥 活跃人数：{result['active_users']}\n"
        f"🔥 最活跃：{most_active}\n"
        f"━━━━━━━━━━━━━"
    )
    await today_group_stats.finish(reply_msg(event, msg))


@week_group_stats.handle()
async def handle_week_group_stats(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_week_range()
    result = stats_data.get_group_stats(group_id, start, end)

    most_active = "暂无"
    if result["most_active_user"]:
        most_active = await _get_nickname(bot, group_id, int(result["most_active_user"]))
        most_active = f"{most_active}（{result['most_active_count']}条）"

    msg = (
        f"📊 本周群统计\n"
        f"━━━━━━━━━━━━━\n"
        f"💬 消息总数：{result['total_messages']}\n"
        f"👥 活跃人数：{result['active_users']}\n"
        f"🔥 最活跃：{most_active}\n"
        f"━━━━━━━━━━━━━"
    )
    await week_group_stats.finish(reply_msg(event, msg))


@month_group_stats.handle()
async def handle_month_group_stats(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_month_range()
    result = stats_data.get_group_stats(group_id, start, end)

    most_active = "暂无"
    if result["most_active_user"]:
        most_active = await _get_nickname(bot, group_id, int(result["most_active_user"]))
        most_active = f"{most_active}（{result['most_active_count']}条）"

    msg = (
        f"📊 本月群统计\n"
        f"━━━━━━━━━━━━━\n"
        f"💬 消息总数：{result['total_messages']}\n"
        f"👥 活跃人数：{result['active_users']}\n"
        f"🔥 最活跃：{most_active}\n"
        f"━━━━━━━━━━━━━"
    )
    await month_group_stats.finish(reply_msg(event, msg))


@my_stats.handle()
async def handle_my_stats(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    today_start, today_end = _get_today_range()
    week_start, week_end = _get_week_range()
    month_start, month_end = _get_month_range()

    today_count = stats_data.get_user_stats(group_id, user_id, today_start, today_end)
    week_count = stats_data.get_user_stats(group_id, user_id, week_start, week_end)
    month_count = stats_data.get_user_stats(group_id, user_id, month_start, month_end)

    nickname = await _get_nickname(bot, group_id, user_id)

    msg = (
        f"📊 发言统计 — {nickname}\n"
        f"━━━━━━━━━━━━━\n"
        f"📅 今日：{today_count}条\n"
        f"📅 本周：{week_count}条\n"
        f"📅 本月：{month_count}条\n"
        f"━━━━━━━━━━━━━"
    )
    await my_stats.finish(reply_msg(event, msg))


@user_stats.handle()
async def handle_user_stats(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    target_id = _extract_at_user(event)
    if not target_id:
        await user_stats.finish(reply_msg(event, "请@要查询的用户，例如：查发言统计@某人"))

    today_start, today_end = _get_today_range()
    week_start, week_end = _get_week_range()
    month_start, month_end = _get_month_range()

    today_count = stats_data.get_user_stats(group_id, target_id, today_start, today_end)
    week_count = stats_data.get_user_stats(group_id, target_id, week_start, week_end)
    month_count = stats_data.get_user_stats(group_id, target_id, month_start, month_end)

    nickname = await _get_nickname(bot, group_id, target_id)

    msg = (
        f"📊 发言统计 — {nickname}\n"
        f"━━━━━━━━━━━━━\n"
        f"📅 今日：{today_count}条\n"
        f"📅 本周：{week_count}条\n"
        f"📅 本月：{month_count}条\n"
        f"━━━━━━━━━━━━━"
    )
    await user_stats.finish(reply_msg(event, msg))


@today_ranking.handle()
async def handle_today_ranking(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_today_range()
    ranking = stats_data.get_ranking(group_id, start, end, limit=10)

    if not ranking:
        await today_ranking.finish(reply_msg(event, "今日暂无发言数据"))

    lines = ["🏆 今日发言排行", "━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, count) in enumerate(ranking, 1):
        nickname = await _get_nickname(bot, group_id, int(uid))
        medal = medals[i - 1] if i <= 3 else f"  {i}."
        lines.append(f"{medal} {nickname} — {count}条")
    lines.append("━━━━━━━━━━━━━")

    await today_ranking.finish(reply_msg(event, "\n".join(lines)))


@week_ranking.handle()
async def handle_week_ranking(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_week_range()
    ranking = stats_data.get_ranking(group_id, start, end, limit=10)

    if not ranking:
        await week_ranking.finish(reply_msg(event, "本周暂无发言数据"))

    lines = ["🏆 本周发言排行", "━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, count) in enumerate(ranking, 1):
        nickname = await _get_nickname(bot, group_id, int(uid))
        medal = medals[i - 1] if i <= 3 else f"  {i}."
        lines.append(f"{medal} {nickname} — {count}条")
    lines.append("━━━━━━━━━━━━━")

    await week_ranking.finish(reply_msg(event, "\n".join(lines)))


@month_ranking.handle()
async def handle_month_ranking(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "统计系统"):
        return

    start, end = _get_month_range()
    ranking = stats_data.get_ranking(group_id, start, end, limit=10)

    if not ranking:
        await month_ranking.finish(reply_msg(event, "本月暂无发言数据"))

    lines = ["🏆 本月发言排行", "━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, count) in enumerate(ranking, 1):
        nickname = await _get_nickname(bot, group_id, int(uid))
        medal = medals[i - 1] if i <= 3 else f"  {i}."
        lines.append(f"{medal} {nickname} — {count}条")
    lines.append("━━━━━━━━━━━━━")

    await month_ranking.finish(reply_msg(event, "\n".join(lines)))


@on_bot_disconnect
async def on_disconnect_save_stats(bot: Bot):
    if stats_data._dirty:
        stats_data.save()


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_GROUP_STATS_MENU_ITEMS = {
    "查今日群统计": "📊 查今日群统计",
    "查本周群统计": "📊 查本周群统计",
    "查本月群统计": "📊 查本月群统计",
    "我的发言统计": "📊 我的发言统计",
    "查发言统计": "📊 查发言统计",
    "今日发言排行": "📊 今日发言排行",
    "本周发言排行": "📊 本周发言排行",
    "本月发言排行": "📊 本月发言排行",
}

for _item_name, _text in _GROUP_STATS_MENU_ITEMS.items():
    menu_registry.register(
        category="群统计",
        item_name=_item_name,
        text=_text,
        category_title="📊◇━群统计━◇📊",
        category_trigger="群统计",
        category_description="发言统计·排行·数据查询",
    )
