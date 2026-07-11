import json
import threading
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from core import on_command, GROUP_ADMIN, GROUP_OWNER, SUPERUSER
from core.menu_registry import menu_registry
from core.onebot import Bot, GroupMessageEvent, Message

from config_manager import config_manager
from plugins.utils import reply_msg

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class EssenceDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "essence_stats_data.json")
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Dict[str, Any]]] = None
        self._lock = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None

    def _ensure_loaded(self):
        if self.data is None:
            self.load()

    def load(self):
        if self.data_path.exists():
            try:
                with open(self.data_path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self):
        with self._lock:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _mark_dirty(self):
        if self._save_timer and self._save_timer.is_alive():
            self._save_timer.cancel()
        self._save_timer = threading.Timer(3.0, self.save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _ensure_group(self, group_id: int) -> dict:
        self._ensure_loaded()
        gid = str(group_id)
        if gid not in self.data:
            self.data[gid] = {"essence_counts": {}, "operator_counts": {}}
        return self.data[gid]

    def record_essence_add(self, group_id: int, sender_id: int, operator_id: int):
        with self._lock:
            gd = self._ensure_group(group_id)
            sc = gd["essence_counts"]
            sc[str(sender_id)] = sc.get(str(sender_id), 0) + 1
            oc = gd["operator_counts"]
            oc[str(operator_id)] = oc.get(str(operator_id), 0) + 1
            self._mark_dirty()

    def record_essence_delete(self, group_id: int, sender_id: int, operator_id: int):
        with self._lock:
            gd = self._ensure_group(group_id)
            sc = gd["essence_counts"]
            sid = str(sender_id)
            if sid in sc:
                sc[sid] -= 1
                if sc[sid] <= 0:
                    del sc[sid]
            self._mark_dirty()

    def clear_group(self, group_id: int):
        self._ensure_loaded()
        with self._lock:
            gid = str(group_id)
            self.data[gid] = {"essence_counts": {}, "operator_counts": {}, "last_clear": time.time()}
            self._mark_dirty()

    def get_essence_ranking(self, group_id: int, limit: int = 10) -> List[Tuple[str, int]]:
        self._ensure_loaded()
        gid = str(group_id)
        if gid not in self.data:
            return []
        gd = self.data[gid]
        sorted_items = sorted(gd.get("essence_counts", {}).items(), key=lambda x: -x[1])
        return sorted_items[:limit]

    def get_operator_ranking(self, group_id: int, limit: int = 10) -> List[Tuple[str, int]]:
        self._ensure_loaded()
        gid = str(group_id)
        if gid not in self.data:
            return []
        gd = self.data[gid]
        sorted_items = sorted(gd.get("operator_counts", {}).items(), key=lambda x: -x[1])
        return sorted_items[:limit]


essence_data = EssenceDataManager()


def _extract_target(event: GroupMessageEvent) -> Optional[int]:
    for seg in event.message:
        if seg.type == "at" and seg.data.get("qq") not in ("all",):
            return int(seg.data["qq"])
    return None


# ==================== 开关命令 ====================

enable_essence = on_command("开启精华统计", priority=1, block=True,
                            permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_essence = on_command("关闭精华统计", priority=1, block=True,
                             permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

@enable_essence.handle()
async def handle_enable_essence(event: GroupMessageEvent):
    config_manager.set_essence_enabled(event.group_id, True)
    await enable_essence.finish(reply_msg(event, "✅ 精华统计已开启"))

@disable_essence.handle()
async def handle_disable_essence(event: GroupMessageEvent):
    config_manager.set_essence_enabled(event.group_id, False)
    await disable_essence.finish(reply_msg(event, "✅ 精华统计已关闭"))


# ==================== 手动管理命令 ====================

add_essence = on_command("添加精华", priority=1, block=True,
                         permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
del_essence = on_command("删除精华", priority=1, block=True,
                         permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

@add_essence.handle()
async def handle_add_essence(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    if not config_manager.is_group_enabled(gid):
        return
    cfg = config_manager.get_essence_config(gid)
    if not cfg.get("enabled", False):
        await add_essence.finish(reply_msg(event, "本群未开启精华统计"))
    target = _extract_target(event)
    if not target:
        await add_essence.finish(reply_msg(event, "请 @ 要添加的用户"))
    essence_data.record_essence_add(gid, target, event.user_id)
    await add_essence.finish(reply_msg(event, f"✅ 已为 {target} 增加精华计数"))

@del_essence.handle()
async def handle_del_essence(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    if not config_manager.is_group_enabled(gid):
        return
    cfg = config_manager.get_essence_config(gid)
    if not cfg.get("enabled", False):
        await del_essence.finish(reply_msg(event, "本群未开启精华统计"))
    target = _extract_target(event)
    if not target:
        await del_essence.finish(reply_msg(event, "请 @ 要删除的用户"))
    essence_data.record_essence_delete(gid, target, event.user_id)
    await del_essence.finish(reply_msg(event, f"✅ 已减少 {target} 的精华计数"))


# ==================== 清空数据 ====================

rebuild_essence = on_command("刷新精华数据", priority=1, block=True)

@rebuild_essence.handle()
async def handle_rebuild_essence(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    if not config_manager.is_group_enabled(gid):
        return
    cfg = config_manager.get_essence_config(gid)
    if not cfg.get("enabled", False):
        await rebuild_essence.finish(reply_msg(event, "本群未开启精华统计"))
    essence_data.clear_group(gid)
    await rebuild_essence.finish(reply_msg(event, "✅ 已清空数据，请使用「添加精华」手动添加"))


# ==================== 查询命令 ====================

query_essence = on_command("查询精华", priority=1, block=True)
query_aliases = [
    on_command("设精大王", priority=1, block=True),
    on_command("精华次数", priority=1, block=True),
    on_command("精华排行", priority=1, block=True),
    on_command("精帖排行", priority=1, block=True),
    on_command("谁是水王", priority=1, block=True),
]


async def _do_query_essence(bot: Bot, event: GroupMessageEvent, matcher):
    gid = event.group_id
    if not config_manager.is_group_enabled(gid):
        return
    cfg = config_manager.get_essence_config(gid)
    if not cfg.get("enabled", False):
        await matcher.finish(reply_msg(event, "本群未开启精华统计功能，请管理员发送「开启精华统计」"))

    erank = essence_data.get_essence_ranking(gid, 10)
    orank = essence_data.get_operator_ranking(gid, 10)

    if not erank and not orank:
        await matcher.finish(reply_msg(event, "本群暂无精华消息记录"))

    medals = ["🥇", "🥈", "🥉"]

    async def _fmt(lines, rank_list):
        for i, (uid, cnt) in enumerate(rank_list, 1):
            medal = medals[i - 1] if i <= 3 else f"{' ' if i < 10 else ''}{i}."
            try:
                mi = await bot.get_group_member_info(group_id=gid, user_id=int(uid))
                name = mi.get("card") or mi.get("nickname", uid)
            except Exception:
                name = uid
            lines.append(f"{medal} {name} — {cnt}次")

    left = ["📌 被设精榜 TOP10", "─────"]
    if erank:
        await _fmt(left, erank)
    else:
        left.append("暂无数据")

    right = ["📌 设精榜 TOP10", "─────"]
    if orank:
        await _fmt(right, orank)
    else:
        right.append("暂无数据")
    msg = f"🏆 群精华统计\n━━━━━━━━\n\n{chr(10).join(left)}\n\n{chr(10).join(right)}"
    await matcher.finish(reply_msg(event, msg))


@query_essence.handle()
async def handle_query_essence(bot: Bot, event: GroupMessageEvent):
    await _do_query_essence(bot, event, query_essence)


for _qa in list(query_aliases):
    _m = _qa
    @_qa.handle()
    async def handle_alias(bot: Bot, event: GroupMessageEvent, __m=_m):
        await _do_query_essence(bot, event, __m)


# ==================== 菜单注册 ====================
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 娱乐功能 -> 精华统计
_ESSENCE_MENU_ITEMS = {
    "开启精华统计": "🌟 开启精华统计",
    "关闭精华统计": "🌟 关闭精华统计",
    "添加精华": "🌟 添加精华",
    "删除精华": "🌟 删除精华",
    "刷新精华数据": "🌟 刷新精华数据",
    "查询精华": "🌟 查询精华",
    "设精大王": "🌟 设精大王",
    "精华次数": "🌟 精华次数",
    "精华排行": "🌟 精华排行",
    "精帖排行": "🌟 精帖排行",
    "谁是水王": "🌟 谁是水王",
}

for _item_name, _text in _ESSENCE_MENU_ITEMS.items():
    menu_registry.register(
        category="娱乐功能",
        item_name=_item_name,
        text=_text,
        subcategory="精华统计",
        subcategory_title="🌟◇━精华统计━◇🌟",
        subcategory_trigger="精华统计",
        subcategory_description="查询精华·设精排行·精华次数",
    )
