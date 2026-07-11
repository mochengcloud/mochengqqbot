import random
import json
import threading
import time
import os
from datetime import datetime, date
from typing import Dict, Any, Optional
from pathlib import Path

from core import on_command, CommandArg, FinishedException
from core.menu_registry import menu_registry
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from log_manager import log_manager
from plugins.utils import reply_msg

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class SimDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "entertainment_data.json")
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._dirty = False
        self._timer: Optional[threading.Timer] = None

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

    def _save(self):
        with self._lock:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self._dirty = False

    def _mark_dirty(self):
        self._dirty = True
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
        self._timer = threading.Timer(5.0, self._save)
        self._timer.daemon = True
        self._timer.start()

    def get(self, key: str, default=None):
        self._ensure_loaded()
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value):
        self._ensure_loaded()
        with self._lock:
            self.data[key] = value
            self._mark_dirty()


sim_data = SimDataManager()


def _get_nickname(event: GroupMessageEvent) -> str:
    return event.sender.card or event.sender.nickname or str(event.user_id)


def _get_target_uid(event: GroupMessageEvent) -> Optional[str]:
    for seg in event.message:
        if seg.type == "at":
            return str(seg.data.get("qq", ""))
    return None


# ==================== 结婚系统 ====================

marry_propose = on_command("求婚", priority=1, block=True)

@marry_propose.handle()
async def handle_marry_propose(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    target = _get_target_uid(event)
    if not target:
        await marry_propose.finish(reply_msg(event, "请 @ 要结婚的对象"))

    if target == uid:
        await marry_propose.finish(reply_msg(event, "不能和自己结婚"))

    data = sim_data.get("marriage", {})
    if gid not in data:
        data[gid] = {"pairs": [], "proposals": {}}

    # 检查是否已婚
    for p in data[gid]["pairs"]:
        if uid in [p["user1"], p["user2"]]:
            await marry_propose.finish(reply_msg(event, "你已经结婚了！发送「离婚」解除婚姻"))
        if target in [p["user1"], p["user2"]]:
            await marry_propose.finish(reply_msg(event, "对方已经结婚了！"))

    data[gid]["proposals"][uid] = {"target": target, "time": time.time()}
    sim_data.set("marriage", data)

    nick = _get_nickname(event)
    await marry_propose.finish(reply_msg(event, f"💍 {nick}\n向 @{target} 求婚了！\n\n如果对方同意，请发送「同意结婚」"))


marry_accept = on_command("同意结婚", priority=1, block=True)

@marry_accept.handle()
async def handle_marry_accept(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("marriage", {})

    if gid not in data:
        await marry_accept.finish(reply_msg(event, "当前没有求婚信息"))

    # 查找谁向当前用户求婚
    proposer = None
    for puid, p in list(data[gid]["proposals"].items()):
        if p["target"] == uid:
            if time.time() - p["time"] > 300:
                del data[gid]["proposals"][puid]
                continue
            proposer = puid
            break

    if not proposer:
        await marry_accept.finish(reply_msg(event, "没有人向你求婚"))

    now = date.today().isoformat()
    data[gid]["pairs"].append({"user1": proposer, "user2": uid, "married_date": now, "intimacy": 0})
    del data[gid]["proposals"][proposer]
    sim_data.set("marriage", data)

    await marry_accept.finish(reply_msg(event, "🎉 恭喜二位！新婚快乐！\n\n可以发送「查看婚姻」查看状态"))


marry_divorce = on_command("离婚", priority=1, block=True)

@marry_divorce.handle()
async def handle_marry_divorce(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("marriage", {})

    if gid not in data:
        await marry_divorce.finish(reply_msg(event, "你还没有结婚"))

    for i, p in enumerate(data[gid]["pairs"]):
        if uid in [p["user1"], p["user2"]]:
            data[gid]["pairs"].pop(i)
            sim_data.set("marriage", data)
            await marry_divorce.finish(reply_msg(event, "💔 婚姻已解除…"))

    await marry_divorce.finish(reply_msg(event, "你还没有结婚"))


marry_info = on_command("查看婚姻", priority=1, block=True)
marry_info2 = on_command("婚姻状态", priority=1, block=True)

@marry_info.handle()
async def handle_marry_info(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("marriage", {})

    if gid not in data:
        await marry_info.finish(reply_msg(event, "本群还没有人结婚"))

    for p in data[gid]["pairs"]:
        if uid in [p["user1"], p["user2"]]:
            partner = p["user2"] if uid == p["user1"] else p["user1"]
            days = (date.today() - date.fromisoformat(p["married_date"])).days
            hearts = "❤️" * min(p.get("intimacy", 0) // 10, 5) or "💔"
            await marry_info.finish(reply_msg(event, f"💑 婚姻状态\n━━━━━━━━\n结婚对象：{partner}\n结婚天数：{days} 天\n亲密度：{p.get('intimacy', 0)} {hearts}"))

    await marry_info.finish(reply_msg(event, "你还没有结婚"))

@marry_info2.handle()
async def handle_marry_info2(event: GroupMessageEvent):
    await handle_marry_info(event)


# ==================== 宠物养成 ====================

PET_TYPES = ["🐱 猫", "🐶 狗", "🐰 兔子", "🐉 龙", "🐧 企鹅", "🦊 狐狸", "🐱 布偶猫", "🦄 独角兽"]

pet_adopt = on_command("领养宠物", priority=1, block=True)

@pet_adopt.handle()
async def handle_pet_adopt(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("pets", {})

    if uid in data.get(gid, {}):
        await pet_adopt.finish(reply_msg(event, "你已经有一只宠物了！发送「查看宠物」查看状态"))

    name = args.extract_plain_text().strip()
    if not name:
        name = "小可爱"

    pet_type = random.choice(PET_TYPES)

    if gid not in data:
        data[gid] = {}
    data[gid][uid] = {
        "name": name, "type": pet_type, "level": 1, "exp": 0,
        "hunger": 100, "cleanliness": 100, "mood": 100,
        "last_update": time.time()
    }
    sim_data.set("pets", data)
    await pet_adopt.finish(reply_msg(event, f"🎉 领养成功！\n{pet_type}「{name}」成为了你的伙伴！\n\n发送「查看宠物」查看状态，发送「喂食」「清洁」「玩耍」照顾它"))


pet_info = on_command("查看宠物", priority=1, block=True)

@pet_info.handle()
async def handle_pet_info(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("pets", {})

    if gid not in data or uid not in data[gid]:
        await pet_info.finish(reply_msg(event, "你还没有宠物，发送「领养宠物 名字」领养一个"))

    pet = data[gid][uid]
    # 计算衰减
    now = time.time()
    elapsed = now - pet["last_update"]
    hours = elapsed / 3600
    pet["hunger"] = max(0, int(pet["hunger"] - hours * 5))
    pet["cleanliness"] = max(0, int(pet["cleanliness"] - hours * 3))
    pet["mood"] = max(0, int(pet["mood"] - hours * 4))
    pet["last_update"] = now
    sim_data.set("pets", data)

    bar = lambda v: "█" * (v // 10) + "░" * (10 - v // 10)
    await pet_info.finish(reply_msg(event, f"🐾 {pet['type']}「{pet['name']}」\n━━━━━━━━\n等级：Lv.{pet['level']}  经验：{pet['exp']}/100\n饥饿：{pet['hunger']:>3} {bar(pet['hunger'])}\n清洁：{pet['cleanliness']:>3} {bar(pet['cleanliness'])}\n心情：{pet['mood']:>3} {bar(pet['mood'])}"))


pet_feed = on_command("喂食", priority=1, block=True)
pet_clean = on_command("清洁", priority=1, block=True)
pet_play = on_command("玩耍", priority=1, block=True)
pet_work = on_command("宠物打工", priority=1, block=True)


async def _pet_act(event: GroupMessageEvent, attr: str, gain: int, msg: str):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("pets", {})
    if gid not in data or uid not in data[gid]:
        await event.matcher.finish(reply_msg(event, "你还没有宠物"))

    pet = data[gid][uid]
    old = pet.get(attr, 0)
    pet[attr] = min(100, old + gain)
    
    # 加经验
    pet["exp"] += random.randint(5, 15)
    leveled = False
    if pet["exp"] >= 100:
        pet["level"] += 1
        pet["exp"] = pet["exp"] - 100
        leveled = True

    sim_data.set("pets", data)

    reply = f"✅ {msg}「{pet['name']}」\n{attr} +{gain}\n当前：{pet[attr]}"
    if leveled:
        reply += f"\n\n🎉 升级啦！Lv.{pet['level']}"
    await event.matcher.finish(reply_msg(event, reply))


@pet_feed.handle()
async def handle_pet_feed(event: GroupMessageEvent):
    await _pet_act(event, "hunger", 30, "你喂食了")

@pet_clean.handle()
async def handle_pet_clean(event: GroupMessageEvent):
    await _pet_act(event, "cleanliness", 30, "你帮")

@pet_play.handle()
async def handle_pet_play(event: GroupMessageEvent):
    await _pet_act(event, "mood", 30, "你和")

@pet_work.handle()
async def handle_pet_work(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("pets", {})

    if gid not in data or uid not in data[gid]:
        await pet_work.finish(reply_msg(event, "你还没有宠物"))

    pet = data[gid][uid]
    if pet["mood"] < 30:
        await pet_work.finish(reply_msg(event, f"{pet['name']} 心情不好，不想打工…先陪它玩一会儿吧"))
    if pet["hunger"] < 30:
        await pet_work.finish(reply_msg(event, f"{pet['name']} 饿得走不动了…先喂食吧"))

    earnings = random.randint(5, 20) * pet["level"]
    pet["mood"] = max(0, pet["mood"] - 15)
    pet["hunger"] = max(0, pet["hunger"] - 15)
    pet["exp"] += random.randint(10, 25)
    leveled = False
    if pet["exp"] >= 100:
        pet["level"] += 1
        pet["exp"] = pet["exp"] - 100
        leveled = True

    sim_data.set("pets", data)

    reply = f"💼 {pet['name']} 打工归来！\n赚了 {earnings} 积分\n消耗了体力…"
    if leveled:
        reply += f"\n\n🎉 升级啦！Lv.{pet['level']}"
    await pet_work.finish(reply_msg(event, reply))


# ==================== 钓鱼模拟 ====================

FISH_SPECIES = [
    ("草鱼", 1, "🌿"), ("鲤鱼", 1, "🐟"), ("鲫鱼", 2, "🐠"), ("鲢鱼", 2, "🐟"),
    ("鲈鱼", 3, "🐠"), ("鳜鱼", 3, "🐟"), ("金鱼", 2, "🐠"), ("锦鲤", 4, "🎏"),
    ("龙鱼", 8, "🐉"), ("金龙鱼", 10, "🌟"), ("蓝鳍金枪鱼", 15, "🔵"),
    ("彩虹鳟鱼", 6, "🌈"), ("小丑鱼", 3, "🤡"), ("神仙鱼", 5, "👼"),
    ("河豚", 4, "🎈"), ("电鳗", 3, "⚡"), ("魔鬼鱼", 8, "👿"),
    ("海马", 5, "🐴"), ("水母", 3, "🪼"), ("龙虾", 6, "🦞"),
    ("螃蟹", 3, "🦀"), ("乌龟", 7, "🐢"), ("章鱼", 9, "🐙"),
    ("鱿鱼", 4, "🦑"), ("海豚", 20, "🐬"), ("鲸鱼", 50, "🐋"),
]

ROD_LEVELS = [
    ("竹竿", 1, 0), ("鱼竿", 2, 100), ("海竿", 3, 300),
    ("碳素竿", 4, 600), ("钛金竿", 5, 1000), ("传说钓竿", 6, 2000),
]

fishing = on_command("钓鱼", priority=1, block=True)

@fishing.handle()
async def handle_fishing(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("fishing", {})

    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {"rod": 0, "bait": 20, "exp": 0, "cooldown": 0, "catch_count": 0}

    player = data[gid][uid]
    now = time.time()

    if now < player["cooldown"]:
        wait = int(player["cooldown"] - now)
        await fishing.finish(reply_msg(event, f"🎣 你还不能抛竿，冷却中…剩余 {wait} 秒"))

    if player["bait"] <= 0:
        await fishing.finish(reply_msg(event, "没有鱼饵了！发送「买鱼饵」购买"))

    rod_level = player["rod"]
    rod_name = ROD_LEVELS[rod_level][0] if rod_level < len(ROD_LEVELS) else "传说钓竿"
    rod_mult = ROD_LEVELS[rod_level][1] if rod_level < len(ROD_LEVELS) else 6

    player["bait"] -= 1
    wait_time = random.randint(3, 8)
    player["cooldown"] = now + wait_time

    # 决定是否钓到鱼
    rarity = random.random()
    catch_pool = [f for f in FISH_SPECIES if f[1] <= rod_mult + 2]
    caught = random.choice(catch_pool)
    fish_name, rarity_score, icon = caught

    # 概率修正
    if random.random() < 0.3:
        sim_data.set("fishing", data)
        await fishing.finish(reply_msg(event, f"🎣 抛竿了…\n等了 {wait_time} 秒\n\n😅 鱼跑掉了！下次运气会更好的"))

    player["catch_count"] += 1
    player["exp"] += rarity_score + random.randint(1, 5)

    # 升级鱼竿
    old_rod = player["rod"]
    for i, (_, _, cost) in enumerate(ROD_LEVELS):
        if player["exp"] >= cost and i > player["rod"]:
            player["rod"] = i

    # 图鉴
    fish_dex = sim_data.get("fish_dex", {})
    if gid not in fish_dex:
        fish_dex[gid] = {}
    if uid not in fish_dex[gid]:
        fish_dex[gid][uid] = []
    if fish_name not in fish_dex[gid][uid]:
        fish_dex[gid][uid].append(fish_name)

    sim_data.set("fishing", data)
    sim_data.set("fish_dex", fish_dex)

    rod_up = ""
    if player["rod"] > old_rod:
        rod_up = f"\n\n🎣 鱼竿升级了！当前：{ROD_LEVELS[player['rod']][0]}"

    msg = f"🎣 钓鱼结果\n━━━━━━━━\n鱼竿：{rod_name}\n鱼饵：{player['bait']}\n\n{icon} 钓到了 {fish_name}！"
    if rod_up:
        msg += rod_up

    await fishing.finish(reply_msg(event, msg))


fishing_bait = on_command("买鱼饵", priority=1, block=True)

@fishing_bait.handle()
async def handle_fishing_bait(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("fishing", {})
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {"rod": 0, "bait": 0, "exp": 0, "cooldown": 0, "catch_count": 0}
    data[gid][uid]["bait"] += 20
    sim_data.set("fishing", data)
    await fishing_bait.finish(reply_msg(event, "✅ 购买了 20 个鱼饵！"))


fishing_info = on_command("钓鱼信息", priority=1, block=True)

@fishing_info.handle()
async def handle_fishing_info(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    data = sim_data.get("fishing", {})

    if gid not in data or uid not in data[gid]:
        await fishing_info.finish(reply_msg(event, "你还没有钓过鱼，发送「钓鱼」开始"))

    p = data[gid][uid]
    rod_name = ROD_LEVELS[p["rod"]][0] if p["rod"] < len(ROD_LEVELS) else "传说钓竿"
    fish_dex = sim_data.get("fish_dex", {}).get(gid, {}).get(uid, [])
    await fishing_info.finish(reply_msg(event, f"🎣 钓鱼信息\n━━━━━━━━\n鱼竿：{rod_name}\n鱼饵：{p['bait']} 个\n经验：{p['exp']}\n总收获：{p['catch_count']} 条\n图鉴：{len(fish_dex)}/{len(FISH_SPECIES)} 种"))


fishing_dex = on_command("鱼图鉴", priority=1, block=True)

@fishing_dex.handle()
async def handle_fishing_dex(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    fish_dex = sim_data.get("fish_dex", {}).get(gid, {}).get(uid, [])

    if not fish_dex:
        await fishing_dex.finish(reply_msg(event, "图鉴为空，快去钓鱼吧！"))

    chunks = [fish_dex[i:i+5] for i in range(0, len(fish_dex), 5)]
    lines = [" | ".join(chunk) for chunk in chunks]
    await fishing_dex.finish(reply_msg(event, f"🐟 鱼图鉴 ({len(fish_dex)}/{len(FISH_SPECIES)})\n━━━━━━━━\n" + "\n".join(lines)))


# ==================== 菜单注册 ====================
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 娱乐功能 -> 群内模拟
_SIMULATION_MENU_ITEMS = {
    "求婚": "💍 求婚@某人",
    "同意结婚": "💒 同意结婚",
    "离婚": "💔 离婚",
    "查看婚姻": "💑 查看婚姻",
    "婚姻状态": "💑 婚姻状态",
    "领养宠物": "🐾 领养宠物",
    "查看宠物": "🐾 查看宠物",
    "喂食": "🍖 喂食",
    "清洁": "🧹 清洁",
    "玩耍": "🎾 玩耍",
    "宠物打工": "💼 宠物打工",
    "钓鱼": "🎣 钓鱼",
    "买鱼饵": "🪱 买鱼饵",
    "钓鱼信息": "🎣 钓鱼信息",
    "鱼图鉴": "🐟 鱼图鉴",
}

for _item_name, _text in _SIMULATION_MENU_ITEMS.items():
    menu_registry.register(
        category="娱乐功能",
        item_name=_item_name,
        text=_text,
        subcategory="群内模拟",
        subcategory_title="🏠◇━群内模拟━◇🏠",
        subcategory_trigger="群内模拟",
        subcategory_description="结婚·宠物·钓鱼",
    )
