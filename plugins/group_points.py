import json
import random
import threading
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import on_command, CommandArg, SUPERUSER, GROUP_ADMIN, GROUP_OWNER
from core.menu_registry import menu_registry
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.group_checkin import checkin_data
from plugins.utils import reply_msg

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class PointsDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "points_data.json")
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Dict[str, Any]]] = None
        self._lock = threading.Lock()
        self._dirty = False
        self._save_timer: Optional[threading.Timer] = None
        self._save_delay = 3.0
        self._save_threshold = 30
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

    def _mark_dirty(self):
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

    def add_exchange_log(self, group_id: int, user_id: int, gift: str, points: int) -> None:
        self._ensure_loaded()
        gid = str(group_id)
        if gid not in self.data:
            self.data[gid] = {}
        if "exchange_log" not in self.data[gid]:
            self.data[gid]["exchange_log"] = []
        self.data[gid]["exchange_log"].append({
            "user_id": str(user_id),
            "gift": gift,
            "points": points,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self._mark_dirty()


points_data = PointsDataManager()


def _check_enabled(group_id: int) -> tuple:
    """返回 (通过, 提示消息)。通过为True时提示消息为空"""
    if not config_manager.is_group_enabled(group_id):
        return False, ""
    if not config_manager.is_feature_authorized(group_id, "积分系统"):
        return False, ""
    points_config = config_manager.get_points_config(group_id)
    if not points_config.get("enabled", False):
        return False, "⚠️ 积分系统未开启，管理员请使用「开启积分系统」"
    return True, ""


def _check_base(group_id: int) -> bool:
    """仅检查群开关和授权，不检查积分系统开关（用于开启/关闭命令）"""
    if not config_manager.is_group_enabled(group_id):
        return False
    if not config_manager.is_feature_authorized(group_id, "积分系统"):
        return False
    return True


# ============ 积分查询 ============
query_points = on_command("积分查询", priority=1, block=True)


@query_points.handle()
async def handle_query_points(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await query_points.finish(reply_msg(event, msg))
        return

    user_data = checkin_data.get_user_data(group_id, user_id)
    points = user_data.get("points", 0)
    rank = checkin_data.get_user_rank(group_id, user_id)
    total_checkins = user_data.get("total_checkins", 0)
    consecutive = user_data.get("consecutive_days", 0)

    await query_points.finish(reply_msg(event,
        f"🌱 积分查询\n"
        f"━━━━━━━━━━━━━\n"
        f"💰 当前积分：{points}\n"
        f"🏅 积分排名：第{rank}名\n"
        f"📅 累计签到：{total_checkins}次\n"
        f"🔥 连续签到：{consecutive}天\n"
        f"━━━━━━━━━━━━━"
    ))


# ============ 积分排行 ============
rank_points = on_command("积分排行", priority=1, block=True)


@rank_points.handle()
async def handle_rank_points(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await rank_points.finish(reply_msg(event, msg))
        return

    ranking = checkin_data.get_group_ranking(group_id, limit=10)

    if not ranking:
        await rank_points.finish(reply_msg(event, "暂无积分数据"))

    lines = ["🌟 积分排行榜", "━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, data) in enumerate(ranking, 1):
        medal = medals[i - 1] if i <= 3 else f"  {i}."
        points = data.get("points", 0)

        nickname = uid
        try:
            member_info = await bot.get_group_member_info(group_id=group_id, user_id=int(uid))
            nickname = member_info.get("card") or member_info.get("nickname", uid)
        except Exception:
            pass

        lines.append(f"{medal} {nickname} — {points}积分")

    lines.append("━━━━━━━━━━━━━")
    await rank_points.finish(reply_msg(event, "\n".join(lines)))


# ============ 加积分 ============
add_points = on_command("加积分", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@add_points.handle()
async def handle_add_points(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await add_points.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    target_id = None
    amount = None

    for seg in args:
        if seg.type == "at":
            target_id = int(seg.data.get("qq", 0))

    parts = text.split()
    for part in parts:
        part = part.strip()
        if part.isdigit():
            amount = int(part)

    if not target_id:
        await add_points.finish(reply_msg(event, "请@目标用户，例如：加积分 @QQ 100"))
    if not amount or amount <= 0:
        await add_points.finish(reply_msg(event, "请输入有效积分数，例如：加积分 @QQ 100"))

    user_data = checkin_data.get_user_data(group_id, target_id)
    user_data["points"] = user_data.get("points", 0) + amount
    checkin_data.update_user_data(group_id, target_id, user_data)

    nickname = str(target_id)
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=target_id)
        nickname = member_info.get("card") or member_info.get("nickname", str(target_id))
    except Exception:
        pass

    log_manager.log_notice("points", f"Admin {event.user_id} added {amount} points to {target_id} in group {group_id}")
    await add_points.finish(reply_msg(event, f"✅ 已为 {nickname} 增加 {amount} 积分\n💰 当前积分：{user_data['points']}"))


# ============ 减积分 ============
sub_points = on_command("减积分", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@sub_points.handle()
async def handle_sub_points(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await sub_points.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    target_id = None
    amount = None

    for seg in args:
        if seg.type == "at":
            target_id = int(seg.data.get("qq", 0))

    parts = text.split()
    for part in parts:
        part = part.strip()
        if part.isdigit():
            amount = int(part)

    if not target_id:
        await sub_points.finish(reply_msg(event, "请@目标用户，例如：减积分 @QQ 100"))
    if not amount or amount <= 0:
        await sub_points.finish(reply_msg(event, "请输入有效积分数，例如：减积分 @QQ 100"))

    user_data = checkin_data.get_user_data(group_id, target_id)
    old_points = user_data.get("points", 0)
    user_data["points"] = max(0, old_points - amount)
    actual_deduction = old_points - user_data["points"]
    checkin_data.update_user_data(group_id, target_id, user_data)

    nickname = str(target_id)
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=target_id)
        nickname = member_info.get("card") or member_info.get("nickname", str(target_id))
    except Exception:
        pass

    log_manager.log_notice("points", f"Admin {event.user_id} subtracted {actual_deduction} points from {target_id} in group {group_id}")
    await sub_points.finish(reply_msg(event, f"✅ 已扣除 {nickname} {actual_deduction} 积分\n💰 当前积分：{user_data['points']}"))


# ============ 全员加积分 ============
add_points_all = on_command("全员加积分", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@add_points_all.handle()
async def handle_add_points_all(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await add_points_all.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    try:
        amount = int(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await add_points_all.finish(reply_msg(event, "请输入有效积分数，例如：全员加积分 100"))

    gid = str(group_id)
    if gid not in checkin_data.data:
        await add_points_all.finish(reply_msg(event, "本群暂无积分数据"))

    count = 0
    for uid in checkin_data.data[gid]:
        checkin_data.data[gid][uid]["points"] = checkin_data.data[gid][uid].get("points", 0) + amount
        count += 1
    checkin_data.save()

    log_manager.log_notice("points", f"Admin {event.user_id} added {amount} points to all {count} users in group {group_id}")
    await add_points_all.finish(reply_msg(event, f"✅ 已为 {count} 名用户各增加 {amount} 积分"))


# ============ 全员减积分 ============
sub_points_all = on_command("全员减积分", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@sub_points_all.handle()
async def handle_sub_points_all(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await sub_points_all.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    try:
        amount = int(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await sub_points_all.finish(reply_msg(event, "请输入有效积分数，例如：全员减积分 100"))

    gid = str(group_id)
    if gid not in checkin_data.data:
        await sub_points_all.finish(reply_msg(event, "本群暂无积分数据"))

    count = 0
    for uid in checkin_data.data[gid]:
        old = checkin_data.data[gid][uid].get("points", 0)
        checkin_data.data[gid][uid]["points"] = max(0, old - amount)
        count += 1
    checkin_data.save()

    log_manager.log_notice("points", f"Admin {event.user_id} subtracted {amount} points from all {count} users in group {group_id}")
    await sub_points_all.finish(reply_msg(event, f"✅ 已扣除 {count} 名用户各 {amount} 积分（不足者归零）"))


# ============ 查积分（查他人） ============
check_points = on_command("查积分", priority=1, block=True)


@check_points.handle()
async def handle_check_points(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await check_points.finish(reply_msg(event, msg))
        return

    target_id = None
    for seg in args:
        if seg.type == "at":
            target_id = int(seg.data.get("qq", 0))

    if not target_id:
        await check_points.finish(reply_msg(event, "请@目标用户，例如：查积分 @QQ"))

    user_data = checkin_data.get_user_data(group_id, target_id)
    points = user_data.get("points", 0)
    rank = checkin_data.get_user_rank(group_id, target_id)

    nickname = str(target_id)
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=target_id)
        nickname = member_info.get("card") or member_info.get("nickname", str(target_id))
    except Exception:
        pass

    await check_points.finish(reply_msg(event,
        f"🌱 查询积分\n"
        f"━━━━━━━━━━━━━\n"
        f"👤 用户：{nickname}\n"
        f"💰 积分：{points}\n"
        f"🏅 排名：第{rank}名\n"
        f"━━━━━━━━━━━━━"
    ))


# ============ 积分重置 ============
reset_points = on_command("积分重置", priority=1, block=True, permission=SUPERUSER)


@reset_points.handle()
async def handle_reset_points(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await reset_points.finish(reply_msg(event, msg))
        return

    gid = str(group_id)
    if gid not in checkin_data.data:
        await reset_points.finish(reply_msg(event, "本群暂无积分数据"))

    count = 0
    for uid in checkin_data.data[gid]:
        checkin_data.data[gid][uid]["points"] = 0
        count += 1
    checkin_data.save()

    log_manager.log_notice("points", f"Superuser {event.user_id} reset all points in group {group_id}, affected {count} users")
    await reset_points.finish(reply_msg(event, f"✅ 已重置本群 {count} 名用户的积分"))


# ============ 设置兑换礼物 ============
set_gift = on_command("设置兑换礼物", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_gift.handle()
async def handle_set_gift(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_gift.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await set_gift.finish(reply_msg(event, "格式：设置兑换礼物 礼物名 积分 [库存]\n例如：设置兑换礼物 专属头衔 100 10\n库存不填则为无限"))

    parts = text.split()
    if len(parts) < 2:
        await set_gift.finish(reply_msg(event, "格式：设置兑换礼物 礼物名 积分 [库存]"))

    gift_name = parts[0]
    try:
        points_cost = int(parts[1])
        if points_cost <= 0:
            raise ValueError
    except ValueError:
        await set_gift.finish(reply_msg(event, "积分必须为正整数"))

    stock = -1
    if len(parts) >= 3:
        try:
            stock = int(parts[2])
            if stock < -1 or stock == 0:
                raise ValueError
        except ValueError:
            await set_gift.finish(reply_msg(event, "库存必须为正整数或-1（无限）"))

    config_manager.add_gift(group_id, gift_name, points_cost, stock=stock)

    stock_text = "无限" if stock == -1 else str(stock)
    await set_gift.finish(reply_msg(event, f"✅ 礼物已上架\n🎁 名称：{gift_name}\n💰 所需积分：{points_cost}\n📦 库存：{stock_text}"))


# ============ 删除礼物 ============
del_gift = on_command("删除礼物", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@del_gift.handle()
async def handle_del_gift(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await del_gift.finish(reply_msg(event, msg))
        return

    gift_name = args.extract_plain_text().strip()
    if not gift_name:
        await del_gift.finish(reply_msg(event, "请输入礼物名称，例如：删除礼物 专属头衔"))

    if config_manager.remove_gift(group_id, gift_name):
        await del_gift.finish(reply_msg(event, f"✅ 礼物「{gift_name}」已下架"))
    else:
        await del_gift.finish(reply_msg(event, f"❌ 礼物「{gift_name}」不存在"))


# ============ 积分商城 ============
points_shop = on_command("积分商城", priority=1, block=True)


@points_shop.handle()
async def handle_points_shop(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await points_shop.finish(reply_msg(event, msg))
        return

    gifts = config_manager.get_gifts(group_id)

    if not gifts:
        await points_shop.finish(reply_msg(event, "🏪 积分商城暂无商品上架\n管理员可使用「设置兑换礼物」上架商品"))

    lines = ["🏪 积分商城", "━━━━━━━━━━━━━"]

    for i, (name, data) in enumerate(gifts.items(), 1):
        points_cost = data.get("points", 0)
        stock = data.get("stock", -1)
        description = data.get("description", "")

        stock_text = "无限" if stock == -1 else str(stock)
        desc_text = f"\n   📝 {description}" if description else ""

        lines.append(f"{i}. 🎁 {name}")
        lines.append(f"   💰 {points_cost}积分 | 📦 库存：{stock_text}{desc_text}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用「兑换礼物 礼物名」进行兑换")
    await points_shop.finish(reply_msg(event, "\n".join(lines)))


# ============ 兑换礼物 ============
exchange_gift = on_command("兑换礼物", priority=1, block=True)


@exchange_gift.handle()
async def handle_exchange_gift(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await exchange_gift.finish(reply_msg(event, msg))
        return

    gift_name = args.extract_plain_text().strip()
    if not gift_name:
        await exchange_gift.finish(reply_msg(event, "请输入礼物名称，例如：兑换礼物 专属头衔\n使用「积分商城」查看可兑换礼物"))

    gifts = config_manager.get_gifts(group_id)
    if gift_name not in gifts:
        await exchange_gift.finish(reply_msg(event, f"❌ 礼物「{gift_name}」不存在\n使用「积分商城」查看可兑换礼物"))

    gift_info = gifts[gift_name]
    points_cost = gift_info.get("points", 0)
    stock = gift_info.get("stock", -1)

    if stock == 0:
        await exchange_gift.finish(reply_msg(event, f"❌ 礼物「{gift_name}」已售罄"))

    user_data = checkin_data.get_user_data(group_id, user_id)
    current_points = user_data.get("points", 0)

    if current_points < points_cost:
        await exchange_gift.finish(reply_msg(event, f"❌ 积分不足\n💰 当前积分：{current_points}\n🎁 所需积分：{points_cost}"))

    user_data["points"] = current_points - points_cost
    checkin_data.update_user_data(group_id, user_id, user_data)

    if stock > 0:
        config_manager.add_gift(group_id, gift_name, points_cost,
                                description=gift_info.get("description", ""),
                                stock=stock - 1)

    points_data.add_exchange_log(group_id, user_id, gift_name, points_cost)

    log_manager.log_notice("points", f"User {user_id} exchanged gift '{gift_name}' for {points_cost} points in group {group_id}")
    await exchange_gift.finish(reply_msg(event,
        f"✅ 兑换成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"🎁 礼物：{gift_name}\n"
        f"💰 消耗积分：{points_cost}\n"
        f"💵 剩余积分：{user_data['points']}\n"
        f"━━━━━━━━━━━━━"
    ))


# ============ 积分抽奖 ============
lottery = on_command("积分抽奖", priority=1, block=True)


@lottery.handle()
async def handle_lottery(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await lottery.finish(reply_msg(event, msg))
        return

    lottery_config = config_manager.get_lottery_config(group_id)
    cost = lottery_config.get("cost", 10)
    prizes = lottery_config.get("prizes", [])

    if not prizes:
        await lottery.finish(reply_msg(event, "❌ 抽奖尚未配置，请联系管理员设置"))

    user_data = checkin_data.get_user_data(group_id, user_id)
    current_points = user_data.get("points", 0)

    if current_points < cost:
        await lottery.finish(reply_msg(event, f"❌ 积分不足\n💰 当前积分：{current_points}\n🎰 抽奖费用：{cost}积分"))

    user_data["points"] = current_points - cost

    roll = random.randint(1, 100)
    cumulative = 0
    won_prize = prizes[-1]
    for prize in prizes:
        cumulative += prize.get("probability", 0)
        if roll <= cumulative:
            won_prize = prize
            break

    reward = won_prize.get("reward_points", 0)
    user_data["points"] += reward
    checkin_data.update_user_data(group_id, user_id, user_data)

    reward_text = f"+{reward}积分" if reward > 0 else "无积分奖励"
    net_change = reward - cost

    log_manager.log_notice("points", f"User {user_id} lottery in group {group_id}: cost={cost}, prize={won_prize.get('name')}, reward={reward}")
    await lottery.finish(reply_msg(event,
        f"🎰 积分抽奖\n"
        f"━━━━━━━━━━━━━\n"
        f"🎲 抽奖结果：{won_prize.get('name', '未知')}\n"
        f"💸 消耗积分：{cost}\n"
        f"🎁 奖励：{reward_text}\n"
        f"📊 净变动：{net_change:+d}积分\n"
        f"💰 当前积分：{user_data['points']}\n"
        f"━━━━━━━━━━━━━"
    ))


# ============ 设置抽奖 ============
set_lottery = on_command("设置抽奖", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_lottery.handle()
async def handle_set_lottery(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_lottery.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await set_lottery.finish(reply_msg(event,
            "格式：设置抽奖 费用 奖品1:概率:积分,奖品2:概率:积分,...\n"
            "例如：设置抽奖 10 一等奖:5:100,二等奖:15:50,三等奖:30:20,谢谢参与:50:0\n"
            "概率之和应为100"
        ))

    parts = text.split()
    if len(parts) < 2:
        await set_lottery.finish(reply_msg(event, "格式：设置抽奖 费用 奖品列表"))

    try:
        cost = int(parts[0])
        if cost <= 0:
            raise ValueError
    except ValueError:
        await set_lottery.finish(reply_msg(event, "抽奖费用必须为正整数"))

    prizes = []
    prize_parts = parts[1].split(",")
    total_prob = 0

    for pp in prize_parts:
        fields = pp.strip().split(":")
        if len(fields) != 3:
            await set_lottery.finish(reply_msg(event, f"奖品格式错误：{pp}\n正确格式：奖品名:概率:积分"))
        name = fields[0].strip()
        try:
            prob = int(fields[1].strip())
            reward = int(fields[2].strip())
            if prob <= 0:
                raise ValueError
        except ValueError:
            await set_lottery.finish(reply_msg(event, f"概率和积分必须为非负整数：{pp}"))

        total_prob += prob
        prizes.append({"name": name, "probability": prob, "reward_points": reward})

    if total_prob != 100:
        await set_lottery.finish(reply_msg(event, f"❌ 概率之和为{total_prob}，必须等于100"))

    config_manager.set_lottery_cost(group_id, cost)
    config_manager.set_lottery_prizes(group_id, prizes)

    prize_list = "\n".join([f"  {p['name']} - 概率{p['probability']}% - 奖励{p['reward_points']}积分" for p in prizes])
    await set_lottery.finish(reply_msg(event,
        f"✅ 抽奖已设置\n"
        f"🎰 抽奖费用：{cost}积分\n"
        f"📋 奖品列表：\n{prize_list}"
    ))


# ============ 设置积分赠送手续费 ============
set_transfer_fee = on_command("设置积分赠送手续费", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@set_transfer_fee.handle()
async def handle_set_transfer_fee(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await set_transfer_fee.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    try:
        rate = int(text)
        if rate < 0 or rate > 100:
            raise ValueError
    except ValueError:
        await set_transfer_fee.finish(reply_msg(event, "手续费百分比必须为0-100的整数"))

    config_manager.set_transfer_fee_rate(group_id, rate)
    await set_transfer_fee.finish(reply_msg(event, f"✅ 积分赠送手续费已设置为 {rate}%"))


# ============ 积分赠送 ============
transfer_points = on_command("积分赠送", priority=1, block=True)


@transfer_points.handle()
async def handle_transfer_points(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await transfer_points.finish(reply_msg(event, msg))
        return

    transfer_config = config_manager.get_transfer_config(group_id)
    if not transfer_config.get("enabled", True):
        await transfer_points.finish(reply_msg(event, "❌ 积分赠送功能未开启"))

    text = args.extract_plain_text().strip()
    target_id = None
    amount = None

    for seg in args:
        if seg.type == "at":
            target_id = int(seg.data.get("qq", 0))

    parts = text.split()
    for part in parts:
        part = part.strip()
        if part.isdigit():
            amount = int(part)

    if not target_id:
        await transfer_points.finish(reply_msg(event, "请@目标用户，例如：积分赠送 @QQ 100"))
    if target_id == user_id:
        await transfer_points.finish(reply_msg(event, "❌ 不能给自己赠送积分"))
    if not amount or amount <= 0:
        await transfer_points.finish(reply_msg(event, "请输入有效积分数，例如：积分赠送 @QQ 100"))

    fee_rate = transfer_config.get("fee_rate", 10)
    fee = max(1, amount * fee_rate // 100) if fee_rate > 0 else 0
    total_cost = amount + fee

    sender_data = checkin_data.get_user_data(group_id, user_id)
    if sender_data.get("points", 0) < total_cost:
        await transfer_points.finish(reply_msg(event,
            f"❌ 积分不足\n"
            f"💰 当前积分：{sender_data.get('points', 0)}\n"
            f"💸 赠送：{amount}积分 + 手续费{fee}积分 = 共需{total_cost}积分"
        ))

    sender_data["points"] = sender_data.get("points", 0) - total_cost
    checkin_data.update_user_data(group_id, user_id, sender_data)

    receiver_data = checkin_data.get_user_data(group_id, target_id)
    receiver_data["points"] = receiver_data.get("points", 0) + amount
    checkin_data.update_user_data(group_id, target_id, receiver_data)

    receiver_name = str(target_id)
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=target_id)
        receiver_name = member_info.get("card") or member_info.get("nickname", str(target_id))
    except Exception:
        pass

    fee_text = f"\n💸 手续费：{fee}积分（{fee_rate}%）" if fee > 0 else ""
    log_manager.log_notice("points", f"User {user_id} transferred {amount} points to {target_id} in group {group_id}, fee={fee}")
    await transfer_points.finish(reply_msg(event,
        f"✅ 积分赠送成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"👤 接收人：{receiver_name}\n"
        f"💰 赠送积分：{amount}{fee_text}\n"
        f"💵 你的剩余积分：{sender_data['points']}\n"
        f"━━━━━━━━━━━━━"
    ))


# ============ 开启/关闭积分系统 ============
enable_points = on_command("开启积分系统", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_points = on_command("关闭积分系统", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@enable_points.handle()
async def handle_enable_points(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_points_enabled(group_id, True)
    await enable_points.finish(reply_msg(event, "✅ 积分系统已开启"))


@disable_points.handle()
async def handle_disable_points(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_points_enabled(group_id, False)
    await disable_points.finish(reply_msg(event, "❌ 积分系统已关闭"))


# ============ 注册菜单 ============
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 积分系统(无子分类)
_POINTS_MENU_ITEMS = {
    "积分查询": "🌟积分查询",
    "积分排行": "🌟积分排行",
    "加积分": "🌟加积分@QQ *",
    "减积分": "🌟减积分@QQ *",
    "全员加积分": "🌟全员加积分*",
    "全员减积分": "🌟全员减积分*",
    "查积分": "🌟查积分*",
    "积分重置": "🌟积分重置",
    "设置兑换礼物": "🌟设置兑换礼物积分",
    "积分商城": "🌟积分商城",
    "兑换礼物": "🌟兑换礼物",
    "积分抽奖": "🌟积分抽奖",
    "设置积分赠送手续费": "🌟设置积分赠送手续费",
    "积分赠送": "🌟积分赠送",
    "删除礼物": "🌟删除礼物",
    "设置抽奖": "🌟设置抽奖",
    "开启积分系统": "🌟开启积分系统",
    "关闭积分系统": "🌟关闭积分系统",
}

for _item_name, _text in _POINTS_MENU_ITEMS.items():
    menu_registry.register(
        category="积分系统",
        item_name=_item_name,
        text=_text,
        category_title="🌱◇━积分系统━◇🌱",
        category_trigger="积分系统",
        category_description="积分查询·排行·商城·抽奖·赠送",
    )
