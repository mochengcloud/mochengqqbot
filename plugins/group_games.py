import random
import json
import threading
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from core import on_command, CommandArg, FinishedException
from core.menu_registry import menu_registry
from core.onebot import Bot, GroupMessageEvent, Message

from log_manager import log_manager
from plugins.utils import reply_msg

# ==================== 数据管理器 ====================

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class GamesDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "games_data.json")
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

    def update(self, key: str, sub: Dict):
        self._ensure_loaded()
        with self._lock:
            if key not in self.data:
                self.data[key] = {}
            self.data[key].update(sub)
            self._mark_dirty()

    def delete(self, key: str):
        self._ensure_loaded()
        with self._lock:
            self.data.pop(key, None)
            self._mark_dirty()


games_data = GamesDataManager()

# ==================== 老虎机 ====================

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🔔", "⭐", "💎", "7️⃣"]
SLOT_PAYOUTS = {
    3: {"7️⃣": 100, "💎": 50, "⭐": 30, "🔔": 20, "🍊": 15, "🍋": 10, "🍒": 5},
    2: {"7️⃣": 10, "💎": 8, "⭐": 5, "🔔": 3, "🍊": 2, "🍋": 1, "🍒": 1},
}

slot_machine = on_command("老虎机", priority=1, block=True)

@slot_machine.handle()
async def handle_slot_machine(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)

    try:
        bet = int(args.extract_plain_text().strip())
    except ValueError:
        bet = 10

    if bet <= 0:
        await slot_machine.finish(reply_msg(event, "下注必须大于0"))

    from plugins.group_checkin import checkin_data
    user_data = checkin_data.get_user_data(event.group_id, event.user_id)
    user_points = user_data.get("points", 0)
    if user_points <= 0:
        await slot_machine.finish(reply_msg(event, "你没有积分，先去签到获取积分吧！"))

    if bet > user_points:
        await slot_machine.finish(reply_msg(event, f"你只有 {user_points} 积分，不能下注 {bet}"))

    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    line = " │ ".join(reels)

    first = reels[0]
    count = sum(1 for s in reels if s == first)

    winnings = 0
    if count == 3:
        winnings = bet * SLOT_PAYOUTS[3].get(first, 1)
    elif count == 2:
        winnings = bet * SLOT_PAYOUTS[2].get(first, 0)

    new_points = user_points - bet + winnings
    user_data["points"] = new_points
    checkin_data.update_user_data(event.group_id, event.user_id, user_data)

    status = "🎉 中奖！" if winnings > 0 else "💔 没中"
    wl = f"+{winnings}" if winnings > 0 else f"-{bet}"
    msg = f"🎰 老虎机\n━━━━━━━━\n  {line}\n━━━━━━━━\n{status}\n下注：{bet}  盈亏：{wl}\n当前积分：{new_points}"
    await slot_machine.finish(reply_msg(event, msg))

# ---------- 积分查询 ----------

slot_points = on_command("游戏积分", priority=1, block=True)

@slot_points.handle()
async def handle_slot_points(event: GroupMessageEvent):
    from plugins.group_checkin import checkin_data
    user_data = checkin_data.get_user_data(event.group_id, event.user_id)
    await slot_points.finish(reply_msg(event, f"💰 我的积分\n━━━━━━━━\n当前积分：{user_data.get('points', 0)}"))

# ==================== 俄罗斯轮盘 ====================

roulette = on_command("俄罗斯轮盘", priority=1, block=True)

@roulette.handle()
async def handle_roulette(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    rdata = games_data.get("roulette", {})

    if gid not in rdata:
        rdata[gid] = {"chamber": [False]*6, "bullet": 1, "players": [], "current": 0, "active": False}

    game = rdata[gid]
    if not game["active"]:
        game["chamber"] = [False]*6
        game["bullet"] = random.randint(1, 3)
        positions = random.sample(range(6), game["bullet"])
        for p in positions:
            game["chamber"][p] = True
        game["players"] = [uid]
        game["current"] = 0
        game["active"] = True
        games_data.set("roulette", rdata)
        await roulette.finish(reply_msg(event, f"🔫 俄罗斯轮盘开始！\n装填 {game['bullet']} 颗子弹，6 个弹仓\n已加入：你\n\n发送「开枪」扣动扳机\n发送「加入轮盘」加入游戏"))
    else:
        if uid in game["players"]:
            await roulette.finish(reply_msg(event, "你已经在游戏中了"))
        game["players"].append(uid)
        games_data.set("roulette", rdata)
        await roulette.finish(reply_msg(event, f"✅ 已加入轮盘！当前 {len(game['players'])} 人\n轮到 @{game['players'][game['current']]} 开枪"))

roulette_shoot = on_command("开枪", priority=1, block=True)

@roulette_shoot.handle()
async def handle_roulette_shoot(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    rdata = games_data.get("roulette", {})

    if gid not in rdata or not rdata[gid]["active"]:
        await roulette_shoot.finish(reply_msg(event, "当前没有进行中的轮盘游戏"))

    game = rdata[gid]
    if game["players"][game["current"]] != uid:
        await roulette_shoot.finish(reply_msg(event, f"还没轮到你，请等待 @{game['players'][game['current']]} 开枪"))

    pos = game["current"] % 6
    fired = game["chamber"][pos]
    name = event.sender.card or event.sender.nickname or str(event.user_id)

    if fired:
        game["players"].pop(game["current"])
        if len(game["players"]) <= 1:
            winner = game["players"][0] if game["players"] else None
            game["active"] = False
            games_data.set("roulette", rdata)
            if winner:
                await roulette_shoot.finish(reply_msg(event, f"💥 {name} 被击中了！\n\n🎉 胜者：{winner}"))
            else:
                await roulette_shoot.finish(reply_msg(event, f"💥 {name} 被击中了！\n全员阵亡！"))
        else:
            game["current"] = game["current"] % len(game["players"])
            games_data.set("roulette", rdata)
            await roulette_shoot.finish(reply_msg(event, f"💥 {name} 被击中了！已淘汰\n剩余 {len(game['players'])} 人\n轮到 @{game['players'][game['current']]} 开枪"))
    else:
        game["current"] = (game["current"] + 1) % len(game["players"])
        games_data.set("roulette", rdata)
        await roulette_shoot.finish(reply_msg(event, f"🔫 空枪！{name} 活了下来\n轮到 @{game['players'][game['current']]} 开枪"))

roulette_join = on_command("加入轮盘", priority=1, block=True)

@roulette_join.handle()
async def handle_roulette_join(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    rdata = games_data.get("roulette", {})
    if gid not in rdata or not rdata[gid]["active"]:
        await roulette_join.finish(reply_msg(event, "当前没有进行中的轮盘游戏"))
    game = rdata[gid]
    if uid in game["players"]:
        await roulette_join.finish(reply_msg(event, "你已经在游戏中了"))
    game["players"].append(uid)
    games_data.set("roulette", rdata)
    await roulette_join.finish(reply_msg(event, f"✅ 已加入！当前 {len(game['players'])} 人"))

# ==================== 21点 ====================

BLACKJACK = on_command("21点", priority=1, block=True)
blackjack_hit = on_command("要牌", priority=1, block=True)
blackjack_stand = on_command("停牌", priority=1, block=True)

CARD_VALUES = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10
}
CARD_SUITS = ["♠", "♥", "♣", "♦"]


def _draw_card():
    face = random.choice(list(CARD_VALUES.keys()))
    suit = random.choice(CARD_SUITS)
    return {"face": face, "suit": suit, "value": CARD_VALUES[face]}


def _hand_value(hand):
    val = sum(c["value"] for c in hand)
    aces = sum(1 for c in hand if c["face"] == "A")
    while val > 21 and aces > 0:
        val -= 10
        aces -= 1
    return val


def _hand_str(hand):
    return " ".join(f"{c['suit']}{c['face']}" for c in hand)


@BLACKJACK.handle()
async def handle_blackjack(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    bj_data = games_data.get("blackjack", {})

    if gid not in bj_data:
        bj_data[gid] = {}
    if uid in bj_data[gid]:
        await BLACKJACK.finish(reply_msg(event, "你已经在游戏中了！发送「要牌」或「停牌」"))

    try:
        bet = int(args.extract_plain_text().strip())
    except ValueError:
        bet = 10

    if bet <= 0:
        await BLACKJACK.finish(reply_msg(event, "下注必须大于0"))

    from plugins.group_checkin import checkin_data
    user_data = checkin_data.get_user_data(event.group_id, event.user_id)
    if user_data["points"] < bet:
        await BLACKJACK.finish(reply_msg(event, f"积分不足！你只有 {user_data['points']} 积分"))
    user_data["points"] -= bet
    checkin_data.update_user_data(event.group_id, event.user_id, user_data)

    player = [_draw_card(), _draw_card()]
    dealer = [_draw_card(), _draw_card()]

    bj_data[gid][uid] = {"player": player, "dealer": dealer, "bet": bet}
    games_data.set("blackjack", bj_data)

    pv = _hand_value(player)
    msg = f"🃏 21点 (下注 {bet})\n━━━━━━━━\n你的牌：{_hand_str(player)}  ({pv}点)\n庄家：{_hand_str([dealer[0]])}  ?\n━━━━━━━━\n发送「要牌」或「停牌」"

    if pv == 21:
        await BLACKJACK.finish(reply_msg(event, msg + "\n\n🎉 Blackjack！"))

    await BLACKJACK.finish(reply_msg(event, msg))


@blackjack_hit.handle()
async def handle_blackjack_hit(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    bj_data = games_data.get("blackjack", {})
    if gid not in bj_data or uid not in bj_data[gid]:
        await blackjack_hit.finish(reply_msg(event, "你没有进行中的21点游戏，发送「21点 下注」开始"))

    game = bj_data[gid][uid]
    game["player"].append(_draw_card())
    pv = _hand_value(game["player"])

    if pv > 21:
        del bj_data[gid][uid]
        games_data.set("blackjack", bj_data)
        await blackjack_hit.finish(reply_msg(event, f"你的牌：{_hand_str(game['player'])}  ({pv}点)\n💥 爆了！你输了 {game['bet']} 积分"))
    elif pv == 21:
        dv = _hand_value(game["dealer"])
        while dv < 17:
            game["dealer"].append(_draw_card())
            dv = _hand_value(game["dealer"])
        del bj_data[gid][uid]
        games_data.set("blackjack", bj_data)
        from plugins.group_checkin import checkin_data as _cd
        _ud = _cd.get_user_data(event.group_id, event.user_id)
        if dv > 21 or pv > dv:
            _ud["points"] += game["bet"] * 2
            result = "🎉 你赢了！"
        elif pv == dv:
            _ud["points"] += game["bet"]
            result = "🤝 平局"
        else:
            result = f"💔 庄家 {dv} 点，你输了"
        _cd.update_user_data(event.group_id, event.user_id, _ud)
        await blackjack_hit.finish(reply_msg(event, f"你的牌：{_hand_str(game['player'])}  ({pv}点)\n庄家：{_hand_str(game['dealer'])}  ({dv}点)\n\n{result}"))
    else:
        games_data.set("blackjack", bj_data)
        await blackjack_hit.finish(reply_msg(event, f"你的牌：{_hand_str(game['player'])}  ({pv}点)\n继续？发送「要牌」或「停牌」"))


@blackjack_stand.handle()
async def handle_blackjack_stand(event: GroupMessageEvent):
    gid = str(event.group_id)
    uid = str(event.user_id)
    bj_data = games_data.get("blackjack", {})
    if gid not in bj_data or uid not in bj_data[gid]:
        await blackjack_stand.finish(reply_msg(event, "你没有进行中的21点游戏"))

    game = bj_data[gid][uid]
    pv = _hand_value(game["player"])
    dv = _hand_value(game["dealer"])
    while dv < 17:
        game["dealer"].append(_draw_card())
        dv = _hand_value(game["dealer"])

    del bj_data[gid][uid]
    games_data.set("blackjack", bj_data)

    from plugins.group_checkin import checkin_data as _cd
    _ud = _cd.get_user_data(event.group_id, event.user_id)
    if dv > 21 or pv > dv:
        _ud["points"] += game["bet"] * 2
        result = "🎉 你赢了！"
    elif pv == dv:
        _ud["points"] += game["bet"]
        result = "🤝 平局"
    else:
        result = f"💔 庄家 {dv} 点，你输了"
    _cd.update_user_data(event.group_id, event.user_id, _ud)

    await blackjack_stand.finish(reply_msg(event, f"你的牌：{_hand_str(game['player'])}  ({pv}点)\n庄家：{_hand_str(game['dealer'])}  ({dv}点)\n\n{result}"))

# ==================== 成语接龙 ====================

idiom_start = on_command("成语接龙", priority=1, block=True)

@idiom_start.handle()
async def handle_idiom_start(event: GroupMessageEvent):
    gid = str(event.group_id)
    idiom_data = games_data.get("idiom", {})

    word = random.choice(IDIOM_DB)
    last_char = word[-1]
    idiom_data[gid] = {"last_char": last_char, "word": word, "last_user": str(event.user_id), "time": time.time()}
    games_data.set("idiom", idiom_data)
    await idiom_start.finish(reply_msg(event, f"📖 成语接龙开始！\n━━━━━━━━\n{word}\n\n请接「{last_char}」字开头的成语\n发送「接龙 成语」来接龙"))

idiom_next = on_command("接龙", priority=1, block=True)

@idiom_next.handle()
async def handle_idiom_next(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    idiom_data = games_data.get("idiom", {})
    if gid not in idiom_data:
        await idiom_next.finish(reply_msg(event, "当前没有进行中的接龙，发送「成语接龙」开始"))

    game = idiom_data[gid]
    if time.time() - game["time"] > 60:
        del idiom_data[gid]
        games_data.set("idiom", idiom_data)
        await idiom_next.finish(reply_msg(event, f"⏰ 超时了！上一个成语：{game.get('word', '')}"))

    uid = str(event.user_id)
    # if uid == game.get("last_user"):
    #     await idiom_next.finish(reply_msg(event, "不能自己接自己"))

    word = args.extract_plain_text().strip()
    if len(word) != 4 or not word.isalpha():
        await idiom_next.finish(reply_msg(event, "请输入4字成语"))

    # 简单检查是否在成语库中
    if word not in IDIOM_DB:
        # 放宽检查：只检查格式
        pass

    if word[0] != game["last_char"]:
        await idiom_next.finish(reply_msg(event, f"请以「{game['last_char']}」字开头"))

    last_char = word[-1]
    game["last_char"] = last_char
    game["word"] = word
    game["last_user"] = uid
    game["time"] = time.time()
    games_data.set("idiom", idiom_data)
    await idiom_next.finish(reply_msg(event, f"✅ 接龙成功！\n{word}\n\n请接「{last_char}」字开头的成语"))


# ==================== 内置数据 ====================

IDIOM_DB = [
    "一心一意", "一石二鸟", "三心二意", "四面八方", "五光十色",
    "六神无主", "七嘴八舌", "八仙过海", "九牛一毛", "十全十美",
    "百发百中", "千军万马", "万紫千红", "画蛇添足", "守株待兔",
    "掩耳盗铃", "亡羊补牢", "刻舟求剑", "叶公好龙", "狐假虎威",
    "井底之蛙", "对牛弹琴", "杯弓蛇影", "鹤立鸡群", "虎头蛇尾",
    "龙马精神", "鸡飞蛋打", "狗急跳墙", "鸟语花香", "风和日丽",
    "山清水秀", "春暖花开", "秋高气爽", "冰天雪地", "雷厉风行",
    "电闪雷鸣", "风雨同舟", "雪中送炭", "锦上添花", "花好月圆",
    "国色天香", "出水芙蓉", "闭月羞花", "沉鱼落雁", "才高八斗",
    "学富五车", "满腹经纶", "博古通今", "出口成章", "妙笔生花",
    "画龙点睛", "入木三分", "铁画银钩", "字里行间", "言简意赅",
    "语重心长", "苦口婆心", "推心置腹", "开诚布公", "肝胆相照",
    "情同手足", "同甘共苦", "患难与共", "亲密无间", "形影不离",
    "如胶似漆", "相敬如宾", "举案齐眉", "相濡以沫", "天长地久",
    "海枯石烂", "山盟海誓", "情投意合", "两情相悦", "一见钟情",
    "青梅竹马", "两小无猜", "心心相印", "心有灵犀", "不约而同",
    "不谋而合", "殊途同归", "异曲同工", "相辅相成", "相得益彰",
    "珠联璧合", "天作之合", "金玉良缘", "安居乐业", "国泰民安",
    "繁荣昌盛", "蒸蒸日上", "欣欣向荣", "朝气蓬勃", "意气风发",
    "斗志昂扬", "生龙活虎", "精神抖擞", "神采奕奕", "容光焕发",
    "眉飞色舞", "喜笑颜开", "眉开眼笑", "心花怒放", "欢天喜地",
    "兴高采烈", "喜出望外", "乐不可支", "捧腹大笑", "哭笑不得",
    "啼笑皆非", "破涕为笑", "忍俊不禁", "哑然失笑", "嫣然一笑",
    "回眸一笑", "笑逐颜开", "喜上眉梢", "欣喜若狂", "欢欣鼓舞",
    "载歌载舞", "弹冠相庆", "额手称庆", "普天同庆", "举国欢腾",
    "热闹非凡", "人山人海", "车水马龙", "络绎不绝", "川流不息",
    "门庭若市", "座无虚席", "接踵而至", "纷至沓来", "源源不断",
    "日新月异", "突飞猛进", "一日千里", "与时俱进", "翻天覆地",
    "改天换地", "沧海桑田", "星移斗转", "光阴似箭", "日月如梭",
    "白驹过隙", "稍纵即逝", "转瞬即逝", "弹指之间", "瞬息万变",
    "惊天动地", "震天动地", "翻江倒海", "排山倒海", "气势磅礴",
    "波澜壮阔", "汹涌澎湃", "惊涛骇浪", "风起云涌", "风驰电掣",
    "大步流星", "健步如飞", "疾步如飞", "飞奔如箭", "龙腾虎跃",
]

# ==================== 菜单注册 ====================
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 娱乐功能 -> 小游戏
_GAME_MENU_ITEMS = {
    "老虎机": "🎰 老虎机 下注",
    "21点": "🃏 21点 下注",
    "要牌": "🃏 要牌",
    "停牌": "🃏 停牌",
    "俄罗斯轮盘": "🔫 俄罗斯轮盘",
    "开枪": "🔫 开枪",
    "加入轮盘": "🔫 加入轮盘",
    "成语接龙": "📖 成语接龙",
    "接龙": "📖 接龙 成语",
    "游戏积分": "💰 游戏积分",
}

for _item_name, _text in _GAME_MENU_ITEMS.items():
    menu_registry.register(
        category="娱乐功能",
        item_name=_item_name,
        text=_text,
        subcategory="小游戏",
        subcategory_title="🎲◇━小游戏━◇🎲",
        subcategory_trigger="小游戏",
        subcategory_description="老虎机·21点·俄罗斯轮盘·成语接龙",
    )
