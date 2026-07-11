import random
import json
import threading
import time
import os
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from core import on_command, CommandArg
from core.menu_registry import menu_registry
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from plugins.utils import reply_msg

# ==================== 数据管理器 ====================

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "data")


class BoardDataManager:
    def __init__(self, data_path: str = None):
        if data_path is None:
            data_path = os.path.join(_DATA_DIR, "board_games_data.json")
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

    def delete(self, key: str):
        self._ensure_loaded()
        with self._lock:
            self.data.pop(key, None)
            self._mark_dirty()


board_data = BoardDataManager()

# ==================== 常量 ====================

BOARD_TYPES = {
    "五子棋": {"size": 15, "min": 2, "max": 2},
    "围棋": {"size": 19, "min": 2, "max": 2},
    "飞行棋": {"size": 0, "min": 2, "max": 4},
}

LUDO_COLORS = ["🔴", "🔵", "🟢", "🟡"]
LUDO_COLORS_HEX = [(220, 50, 50), (50, 100, 220), (50, 180, 50), (220, 200, 30)]
LUDO_OFFSETS = [0, 13, 26, 39]
LUDO_TRACK_SIZE = 52
LUDO_HOME_SIZE = 6
LUDO_FINISH = 58

_FONT = None
_FONT_SMALL = None

def _get_font(size=20):
    global _FONT, _FONT_SMALL
    try:
        if size <= 16:
            if _FONT_SMALL is None:
                _FONT_SMALL = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
            return _FONT_SMALL
        if _FONT is None:
            _FONT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
        return _FONT
    except Exception:
        return ImageFont.load_default()

# ==================== 五子棋 ====================

def gomoku_init():
    return [[0] * 15 for _ in range(15)]

def gomoku_move(board: List[List[int]], row: int, col: int, player: int) -> Tuple[bool, str]:
    if not (0 <= row < 15 and 0 <= col < 15):
        return False, "坐标超出棋盘范围 (1-15)"
    if board[row][col] != 0:
        return False, "该位置已有棋子"
    board[row][col] = player
    win = gomoku_check_win(board, row, col, player)
    if win:
        return True, "win"
    return True, "ok"

def gomoku_check_win(board: List[List[int]], row: int, col: int, player: int) -> bool:
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        r, c = row + dr, col + dc
        while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
            count += 1
            r += dr
            c += dc
        r, c = row - dr, col - dc
        while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
            count += 1
            r -= dr
            c -= dc
        if count >= 5:
            return True
    return False

# ==================== 围棋 ====================

def go_init():
    return [[0] * 19 for _ in range(19)]

def go_get_group(board: List[List[int]], row: int, col: int) -> List[Tuple[int, int]]:
    player = board[row][col]
    if player == 0:
        return []
    visited = set()
    group = []
    stack = [(row, col)]
    while stack:
        r, c = stack.pop()
        if (r, c) in visited:
            continue
        visited.add((r, c))
        group.append((r, c))
        for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 19 and 0 <= nc < 19 and board[nr][nc] == player and (nr, nc) not in visited:
                stack.append((nr, nc))
    return group

def go_get_liberties(board: List[List[int]], group: List[Tuple[int, int]]) -> set:
    liberties = set()
    for r, c in group:
        for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 19 and 0 <= nc < 19 and board[nr][nc] == 0:
                liberties.add((nr, nc))
    return liberties

def go_capture_group(board: List[List[int]], group: List[Tuple[int, int]]) -> int:
    for r, c in group:
        board[r][c] = 0
    return len(group)

def go_move(board: List[List[int]], row: int, col: int, player: int, ko_point: Optional[Tuple[int, int]], last_board: Optional[List[List[int]]]) -> Tuple[bool, str, Optional[Tuple[int, int]], Optional[List[List[int]]], int]:
    if not (0 <= row < 19 and 0 <= col < 19):
        return False, "坐标超出棋盘范围 (1-19)", ko_point, last_board, 0
    if board[row][col] != 0:
        return False, "该位置已有棋子", ko_point, last_board, 0
    if ko_point == (row, col):
        return False, "此处为禁着点（劫）", ko_point, last_board, 0

    captured_count = 0
    board_clone = [list(r) for r in board]
    board_clone[row][col] = player

    for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        nr, nc = row + dr, col + dc
        if 0 <= nr < 19 and 0 <= nc < 19 and board_clone[nr][nc] == (3 - player):
            group = go_get_group(board_clone, nr, nc)
            if group and not go_get_liberties(board_clone, group):
                captured_count += go_capture_group(board_clone, group)

    own_group = go_get_group(board_clone, row, col)
    if own_group and not go_get_liberties(board_clone, own_group):
        return False, "该落子会导致自杀，禁止下在此处", ko_point, last_board, 0

    new_last_board = [list(r) for r in board]
    for r in range(19):
        for c in range(19):
            board[r][c] = board_clone[r][c]

    new_ko = None
    if captured_count == 1 and len(own_group) == 1:
        new_ko = (row, col)

    return True, "ok", new_ko, new_last_board, captured_count

def go_count_score(board: List[List[int]]) -> Tuple[int, int]:
    black_score = 0
    white_score = 0
    visited = [[False] * 19 for _ in range(19)]

    for r in range(19):
        for c in range(19):
            if board[r][c] == 1:
                black_score += 1
            elif board[r][c] == 2:
                white_score += 1
            elif board[r][c] == 0 and not visited[r][c]:
                region = []
                stack = [(r, c)]
                touches_black = False
                touches_white = False
                while stack:
                    cr, cc = stack.pop()
                    if (cr, cc) in visited:
                        continue
                    visited[cr][cc] = True
                    region.append((cr, cc))
                    for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < 19 and 0 <= nc < 19:
                            if board[nr][nc] == 1:
                                touches_black = True
                            elif board[nr][nc] == 2:
                                touches_white = True
                            elif board[nr][nc] == 0 and not visited[nr][nc]:
                                stack.append((nr, nc))
                if touches_black and not touches_white:
                    black_score += len(region)
                elif touches_white and not touches_black:
                    white_score += len(region)

    return black_score, white_score

# ==================== 飞行棋 ====================

def ludo_init(pawn_mode: int = 1):
    return {
        "pieces": [
            [{"pos": -1, "finished": False} for _ in range(pawn_mode)],
            [{"pos": -1, "finished": False} for _ in range(pawn_mode)],
            [{"pos": -1, "finished": False} for _ in range(pawn_mode)],
            [{"pos": -1, "finished": False} for _ in range(pawn_mode)],
        ],
        "pawn_mode": pawn_mode,
    }

def ludo_check_base_collision(board_data: dict, player_idx: int, player_offset: int):
    for pi in range(4):
        if pi == player_idx:
            continue
        for piece in board_data["pieces"][pi]:
            if not piece["finished"] and piece["pos"] == 0:
                g_pos = (LUDO_OFFSETS[pi] + 0) % LUDO_TRACK_SIZE
                if g_pos == player_offset:
                    piece["pos"] = -1
                    return True
    return False

def ludo_move_piece(board_data: dict, player_idx: int, piece_idx: int, dice: int) -> Tuple[bool, str]:
    pieces = board_data["pieces"]
    piece = pieces[player_idx][piece_idx]
    ppos = piece["pos"]
    offset = LUDO_OFFSETS[player_idx]

    if piece["finished"]:
        return False, "该棋子已完成"

    if ppos == -1:
        if dice == 6:
            piece["pos"] = 0
            ludo_check_base_collision(board_data, player_idx, offset)
            return True, "棋子出发"
        return False, f"掷出 {dice}，不是 6，无法出营"

    target = ppos + dice
    if target > LUDO_FINISH:
        return False, f"点数太大 ({dice})，无法越过终点"

    if target > LUDO_TRACK_SIZE - 1:
        piece["pos"] = target
        if target == LUDO_FINISH:
            piece["finished"] = True
            return True, "到达终点"
        return True, f"进入冲刺区 {target - LUDO_TRACK_SIZE}/{LUDO_HOME_SIZE}"
    else:
        global_target = (offset + target) % LUDO_TRACK_SIZE
        for pi in range(4):
            if pi == player_idx:
                continue
            for pj, opiece in enumerate(pieces[pi]):
                if opiece["finished"] or opiece["pos"] == -1:
                    continue
                if opiece["pos"] <= 50:
                    o_global = (LUDO_OFFSETS[pi] + opiece["pos"]) % LUDO_TRACK_SIZE
                    if o_global == global_target:
                        opiece["pos"] = -1
        piece["pos"] = target
        return True, f"前进 {dice} 步"

# ==================== 图片渲染 ====================

def _draw_grid(draw, size, margin, cell, num_lines):
    for i in range(num_lines):
        x = margin + i * cell
        draw.line((x, margin, x, margin + (num_lines - 1) * cell), fill=(0, 0, 0))
        y = margin + i * cell
        draw.line((margin, y, margin + (num_lines - 1) * cell, y), fill=(0, 0, 0))

def _draw_star_points(draw, size, margin, cell, points):
    for r, c in points:
        x = margin + c * cell
        y = margin + r * cell
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(0, 0, 0))

def render_gomoku(board: List[List[int]], last_move: Tuple[int, int] = None) -> bytes:
    sz = 15
    cell = 38
    margin = 30
    label_margin = 18
    left_margin = margin + label_margin
    top_margin = margin + label_margin
    img_size = left_margin + (sz - 1) * cell + margin

    img = Image.new("RGB", (img_size, img_size), (255, 206, 158))
    draw = ImageDraw.Draw(img)
    font = _get_font(14)

    for i in range(sz):
        x = left_margin + i * cell
        draw.line((x, top_margin, x, top_margin + (sz - 1) * cell), fill=(0, 0, 0))
        y = top_margin + i * cell
        draw.line((left_margin, y, left_margin + (sz - 1) * cell, y), fill=(0, 0, 0))

    star_points = [(3, 3), (3, 7), (3, 11), (7, 3), (7, 7), (7, 11), (11, 3), (11, 7), (11, 11)]
    for r, c in star_points:
        x = left_margin + c * cell
        y = top_margin + r * cell
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(0, 0, 0))

    for i in range(sz):
        draw.text((left_margin + i * cell - 5, 5), str(i + 1), fill=(0, 0, 0), font=font)
        draw.text((2, top_margin + i * cell - 7), str(i + 1), fill=(0, 0, 0), font=font)

    for r in range(sz):
        for c in range(sz):
            if board[r][c] == 0:
                continue
            x = left_margin + c * cell
            y = top_margin + r * cell
            color = (0, 0, 0) if board[r][c] == 1 else (255, 255, 255)
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=color)
            if board[r][c] == 2:
                draw.ellipse((x - 16, y - 16, x + 16, y + 16), outline=(0, 0, 0), width=2)

    if last_move:
        lr, lc = last_move
        x = left_margin + lc * cell
        y = top_margin + lr * cell
        mark = "●" if board[lr][lc] == 1 else "○"
        mark_color = (255, 0, 0)
        draw.text((x - 5, y - 7), mark, fill=mark_color, font=_get_font(16))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_go(board: List[List[int]], last_move: Tuple[int, int] = None) -> bytes:
    sz = 19
    cell = 30
    margin = 25
    label_margin = 16
    left_margin = margin + label_margin
    top_margin = margin + label_margin
    img_size = left_margin + (sz - 1) * cell + margin

    img = Image.new("RGB", (img_size, img_size), (255, 206, 158))
    draw = ImageDraw.Draw(img)
    font = _get_font(12)

    for i in range(sz):
        x = left_margin + i * cell
        draw.line((x, top_margin, x, top_margin + (sz - 1) * cell), fill=(0, 0, 0))
        y = top_margin + i * cell
        draw.line((left_margin, y, left_margin + (sz - 1) * cell, y), fill=(0, 0, 0))

    star_points = [
        (3, 3), (3, 9), (3, 15), (9, 3), (9, 9), (9, 15), (15, 3), (15, 9), (15, 15)]
    for r, c in star_points:
        x = left_margin + c * cell
        y = top_margin + r * cell
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(0, 0, 0))

    for i in range(sz):
        draw.text((left_margin + i * cell - 4, 3), str(i + 1), fill=(0, 0, 0), font=font)
        draw.text((2, top_margin + i * cell - 6), str(i + 1), fill=(0, 0, 0), font=font)

    for r in range(sz):
        for c in range(sz):
            if board[r][c] == 0:
                continue
            x = left_margin + c * cell
            y = top_margin + r * cell
            color = (0, 0, 0) if board[r][c] == 1 else (255, 255, 255)
            draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=color)
            if board[r][c] == 2:
                draw.ellipse((x - 12, y - 12, x + 12, y + 12), outline=(0, 0, 0), width=1)

    if last_move:
        lr, lc = last_move
        x = left_margin + lc * cell
        y = top_margin + lr * cell
        mark_color = (255, 0, 0)
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=mark_color)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_ludo(board_data: dict, player_count: int) -> bytes:
    sz = 400
    img = Image.new("RGB", (sz, sz), (245, 245, 235))
    draw = ImageDraw.Draw(img)
    font = _get_font(14)

    cx, cy = sz // 2, sz // 2
    track_r = 150
    home_r = 50

    for pi in range(4):
        angle = pi * 90 - 45
        import math
        rad = math.radians(angle)
        bx = int(cx + track_r * math.cos(rad))
        by = int(cy + track_r * math.sin(rad))
        draw.rectangle((bx - 40, by - 40, bx + 40, by + 40), fill=LUDO_COLORS_HEX[pi], outline=(0, 0, 0), width=2)
        in_base = sum(1 for p in board_data["pieces"][pi] if p["pos"] == -1)
        fin = sum(1 for p in board_data["pieces"][pi] if p["finished"])
        draw.text((bx - 15, by - 10), str(in_base), fill=(255, 255, 255), font=_get_font(20))

    pix_per_pos = 360 / LUDO_TRACK_SIZE
    for pi in range(4):
        for pj, piece in enumerate(board_data["pieces"][pi]):
            if piece["finished"] or piece["pos"] == -1:
                continue
            angle_base = LUDO_OFFSETS[pi] * 360 / LUDO_TRACK_SIZE
            angle = angle_base + piece["pos"] * 360 / LUDO_TRACK_SIZE
            if piece["pos"] > 50:
                home_progress = piece["pos"] - 51
                hp_x = int(cx + (track_r + 20) * math.cos(math.radians(LUDO_OFFSETS[pi] * 360 / LUDO_TRACK_SIZE - 90)))
                hp_y = int(cy + (track_r + 20) * math.sin(math.radians(LUDO_OFFSETS[pi] * 360 / LUDO_TRACK_SIZE - 90)))
                px = int(hp_x + home_progress * 15 * math.cos(math.radians(angle - 90 + 180)))
                py = int(hp_y + home_progress * 15 * math.sin(math.radians(angle - 90 + 180)))
            else:
                ang_rad = math.radians(angle - 90)
                px = int(cx + track_r * math.cos(ang_rad) + pj * 8)
                py = int(cy + track_r * math.sin(ang_rad) + pj * 8)
            draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=LUDO_COLORS_HEX[pi])

    draw.ellipse((cx - home_r, cy - home_r, cx + home_r, cy + home_r), outline=(0, 0, 0), width=2)
    finished = sum(sum(1 for p in pl if p["finished"]) for pl in board_data["pieces"])
    draw.text((cx - 20, cy - 10), str(finished), fill=(100, 100, 100), font=_get_font(24))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ==================== 命令处理器 ====================

create_room = on_command("创建棋局", priority=1, block=True)
join_room = on_command("加入棋局", priority=1, block=True)
room_list = on_command("棋局列表", priority=1, block=True)
make_move = on_command("下棋", priority=1, block=True)
room_info = on_command("棋局信息", priority=1, block=True)
surrender = on_command("认输", priority=1, block=True)
leave_room = on_command("退出棋局", priority=1, block=True)


def _room_key(gid: str, room_name: str) -> str:
    return f"{gid}_{room_name}"


def _parse_coord(text: str, max_val: int) -> Optional[Tuple[int, int]]:
    try:
        parts = text.split(",")
        if len(parts) < 2:
            return None
        row = int(parts[0].strip()) - 1
        col = int(parts[1].strip()) - 1
        if 0 <= row < max_val and 0 <= col < max_val:
            return (row, col)
    except (ValueError, IndexError):
        pass
    return None


def _board_image(room: dict) -> bytes:
    if room["type"] == "五子棋":
        return render_gomoku(room["board"], room.get("last_move"))
    elif room["type"] == "围棋":
        return render_go(room["board"], room.get("last_move"))
    elif room["type"] == "飞行棋":
        return render_ludo(room, len(room["players"]))
    return b""


def _current_player_name(event: GroupMessageEvent, player_id: int) -> str:
    return event.sender.card or event.sender.nickname or str(event.user_id)


# ---------- 创建棋局 ----------

@create_room.handle()
async def handle_create_room(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    text = args.extract_plain_text().strip()
    parts = text.split()

    if not parts:
        await create_room.finish(reply_msg(event, "用法：创建棋局 [类型] [房间号]\n类型：五子棋、围棋、飞行棋\n飞行棋可选：创建棋局 飞行棋 [房间号] 1棋/4棋"))

    game_type = parts[0]
    if game_type not in BOARD_TYPES:
        await create_room.finish(reply_msg(event, f"不支持的棋类类型，支持：{'、'.join(BOARD_TYPES.keys())}"))

    room_name = parts[1] if len(parts) > 1 else f"{game_type}房{random.randint(100, 999)}"
    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})

    if rkey in rooms and rooms[rkey]["status"] != "finished":
        await create_room.finish(reply_msg(event, f"房间「{room_name}」已存在"))

    pawn_mode = 1
    if game_type == "飞行棋":
        if len(parts) > 2:
            pm = parts[2]
            if pm in ("1棋", "单棋"):
                pawn_mode = 1
            elif pm in ("4棋", "满棋"):
                pawn_mode = 4
            else:
                pawn_mode = 1

    bt = BOARD_TYPES[game_type]
    room = {
        "type": game_type,
        "room_name": room_name,
        "players": [uid],
        "turn": 0,
        "status": "waiting",
        "winner": None,
        "created_at": time.time(),
        "min_players": bt["min"],
        "max_players": bt["max"],
    }

    if game_type == "五子棋":
        room["board"] = gomoku_init()
        room["players_color"] = {uid: 1}
    elif game_type == "围棋":
        room["board"] = go_init()
        room["ko_point"] = None
        room["last_board"] = None
        room["captured"] = [0, 0]
        room["pass_count"] = 0
        room["players_color"] = {uid: 1}
    elif game_type == "飞行棋":
        room.update(ludo_init(pawn_mode))
        room["dice"] = 0

    rooms[rkey] = room
    board_data.set("rooms", rooms)

    need_msg = f"「{room_name}」"
    if game_type == "飞行棋" and pawn_mode > 1:
        need_msg += f" ({pawn_mode}棋模式)"
    need_msg += f"\n等待玩家加入 (发送「加入棋局 {room_name}」)"

    await create_room.finish(reply_msg(event, f"🎮 {game_type}房间 {need_msg}"))


# ---------- 加入棋局 ----------

@join_room.handle()
async def handle_join_room(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    room_name = args.extract_plain_text().strip()
    if not room_name:
        await join_room.finish(reply_msg(event, "请指定房间号，如：加入棋局 1号房"))

    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})
    room = rooms.get(rkey)

    if not room or room["status"] == "finished":
        await join_room.finish(reply_msg(event, f"房间「{room_name}」不存在或已结束"))

    if uid in room["players"]:
        await join_room.finish(reply_msg(event, "你已经在房间中了"))

    if len(room["players"]) >= room["max_players"]:
        await join_room.finish(reply_msg(event, f"房间已满 ({room['max_players']}人)"))

    room["players"].append(uid)
    bt = BOARD_TYPES[room["type"]]

    if room["type"] in ("五子棋", "围棋"):
        room["players_color"][uid] = len(room["players"])

    if len(room["players"]) >= room["min_players"]:
        room["status"] = "playing"

    rooms[rkey] = room
    board_data.set("rooms", rooms)

    msg = f"✅ 已加入 {room['type']} 房间「{room_name}」"
    if room["status"] == "playing":
        names = []
        for p in room["players"]:
            try:
                mi = await bot.get_group_member_info(group_id=event.group_id, user_id=int(p))
                names.append(mi.get("card") or mi.get("nickname", p))
            except Exception:
                names.append(p)
        player_list = "\n".join(f"  {'⚫' if i == 0 else '⚪'} {n}" for i, n in enumerate(names))
        msg += f"\n🎮 游戏开始！\n玩家：\n{player_list}\n\n轮到 {'⚫' if room['turn'] == 0 else '⚪'} 下棋"
        img = _board_image(room)
        if img:
            await join_room.finish(reply_msg(event, msg) + MessageSegment.image(img))
    await join_room.finish(reply_msg(event, msg))


# ---------- 棋局列表 ----------

@room_list.handle()
async def handle_room_list(event: GroupMessageEvent):
    gid = str(event.group_id)
    rooms = board_data.get("rooms", {})
    active = [(k, v) for k, v in rooms.items() if k.startswith(gid + "_") and v["status"] != "finished"]

    if not active:
        await room_list.finish(reply_msg(event, "当前群没有活跃棋局"))

    lines = ["♟ 本群棋局列表\n━━━━━━━━"]
    for rkey, room in active:
        rname = room.get("room_name", rkey.split("_", 1)[-1])
        status = "⏳ 等待" if room["status"] == "waiting" else "♟ 进行中"
        lines.append(f"  {status} {room['type']}「{rname}」({len(room['players'])}/{room['max_players']}人)")
    await room_list.finish(reply_msg(event, "\n".join(lines)))


# ---------- 下棋 ----------

@make_move.handle()
async def handle_make_move(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    text = args.extract_plain_text().strip()

    if not text:
        await make_move.finish(reply_msg(event, "用法：下棋 [房间号] [行,列]\n示例：下棋 1号房 7,7"))

    parts = text.split(None, 1)
    room_name = parts[0]
    coord_str = parts[1].strip() if len(parts) > 1 else ""

    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})
    room = rooms.get(rkey)

    if not room or room["status"] == "finished":
        await make_move.finish(reply_msg(event, f"房间「{room_name}」不存在或已结束"))

    if uid not in room["players"]:
        await make_move.finish(reply_msg(event, "你不是该房间的玩家"))

    if room["status"] != "playing":
        await make_move.finish(reply_msg(event, "游戏尚未开始"))

    player_idx = room["players"].index(uid)
    if player_idx != room["turn"]:
        await make_move.finish(reply_msg(event, f"还没轮到你，请等待"))

    if room["type"] == "五子棋":
        coord = _parse_coord(coord_str, 15)
        if not coord:
            await make_move.finish(reply_msg(event, "坐标格式错误，请使用 行,列 (1-15)，如：下棋 1号房 7,7"))
        row, col = coord
        player = room["players_color"][uid]
        ok, result = gomoku_move(room["board"], row, col, player)
        if not ok:
            await make_move.finish(reply_msg(event, result))
        room["last_move"] = (row, col)
        if result == "win":
            room["winner"] = uid
            room["status"] = "finished"
            rooms[rkey] = room
            board_data.set("rooms", rooms)
            img = _board_image(room)
            msg = f"🎉 五子棋「{room_name}」结束！\n胜利者：{_current_player_name(event, uid)}"
            if img:
                await make_move.finish(reply_msg(event, msg) + MessageSegment.image(img))
            await make_move.finish(reply_msg(event, msg))
        room["turn"] = 1 - player_idx

    elif room["type"] == "围棋":
        coord = _parse_coord(coord_str, 19)
        if not coord:
            await make_move.finish(reply_msg(event, "坐标格式错误，请使用 行,列 (1-19)，如：下棋 1号房 10,10"))
        row, col = coord
        player = room["players_color"][uid]
        ok, result, new_ko, new_last, captured = go_move(
            room["board"], row, col, player, room["ko_point"], room["last_board"])
        if not ok:
            await make_move.finish(reply_msg(event, result))
        room["last_move"] = (row, col)
        room["ko_point"] = new_ko
        room["last_board"] = new_last
        room["captured"][player - 1] += captured
        room["pass_count"] = 0
        room["turn"] = 1 - player_idx

    elif room["type"] == "飞行棋":
        dice = random.randint(1, 6)
        room["dice"] = dice
        pawn_idx = -1
        pieces = room["pieces"]
        for pi, p in enumerate(pieces[player_idx]):
            if p["finished"]:
                continue
            if p["pos"] == -1:
                if pawn_idx == -1:
                    pawn_idx = pi
                continue
            if pawn_idx == -1 or p["pos"] < pieces[player_idx][pawn_idx]["pos"]:
                pawn_idx = pi
        if pawn_idx == -1:
            pawn_idx = 0
        ok, result = ludo_move_piece(room, player_idx, pawn_idx, dice)
        roll_msg = f"🎲 {_current_player_name(event, uid)} 掷出了 {dice}"
        if not ok:
            roll_msg += f"\n{result}"
            room["turn"] = (room["turn"] + 1) % len(room["players"])
        else:
            roll_msg += f"\n{result}"
            all_finished = all(p["finished"] for p in pieces[player_idx])
            if all_finished:
                room["winner"] = uid
                room["status"] = "finished"
                rooms[rkey] = room
                board_data.set("rooms", rooms)
                msg = f"🎉 飞行棋「{room_name}」结束！\n胜利者：{_current_player_name(event, uid)}"
                await make_move.finish(reply_msg(event, msg))
            if dice == 6:
                pass
            else:
                room["turn"] = (room["turn"] + 1) % len(room["players"])

    rooms[rkey] = room
    board_data.set("rooms", rooms)
    img = _board_image(room)
    next_name = room["type"]
    if room["status"] == "playing":
        next_p = room["turn"]
        next_uid = room["players"][next_p]
        try:
            mi = await bot.get_group_member_info(group_id=event.group_id, user_id=int(next_uid))
            next_name = mi.get("card") or mi.get("nickname", str(next_uid))
        except Exception:
            next_name = str(next_uid)
        if room["type"] in ("五子棋", "围棋"):
            mark = "⚫" if next_p == 0 else "⚪"
            next_name = f"{mark} {next_name}"

    msg = f"♟ {room['type']}「{room_name}」"
    if room["type"] == "围棋":
        msg += f"\n提子：⚫ {room['captured'][0]} | ⚪ {room['captured'][1]}"
    if room["type"] == "飞行棋":
        msg += f"\n{roll_msg}"
    if room["status"] == "playing":
        msg += f"\n轮到 {next_name} 下棋"
    if img:
        await make_move.finish(reply_msg(event, msg) + MessageSegment.image(img))
    await make_move.finish(reply_msg(event, msg))


# ---------- 棋局信息 ----------

@room_info.handle()
async def handle_room_info(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    room_name = args.extract_plain_text().strip()
    if not room_name:
        await room_info.finish(reply_msg(event, "请指定房间号，如：棋局信息 1号房"))

    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})
    room = rooms.get(rkey)

    if not room:
        await room_info.finish(reply_msg(event, f"房间「{room_name}」不存在"))

    img = _board_image(room)
    status = "等待中" if room["status"] == "waiting" else ("进行中" if room["status"] == "playing" else "已结束")
    msg = f"♟ {room['type']}「{room_name}」\n状态：{status}\n玩家：{len(room['players'])}/{room['max_players']}人"
    if room["winner"]:
        try:
            mi = await bot.get_group_member_info(group_id=event.group_id, user_id=int(room["winner"]))
            wn = mi.get("card") or mi.get("nickname", str(room["winner"]))
        except Exception:
            wn = str(room["winner"])
        msg += f"\n胜者：{wn}"
    if img:
        await room_info.finish(reply_msg(event, msg) + MessageSegment.image(img))
    await room_info.finish(reply_msg(event, msg))


# ---------- 认输 ----------

@surrender.handle()
async def handle_surrender(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    room_name = args.extract_plain_text().strip()
    if not room_name:
        await surrender.finish(reply_msg(event, "请指定房间号，如：认输 1号房"))

    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})
    room = rooms.get(rkey)

    if not room or room["status"] != "playing":
        await surrender.finish(reply_msg(event, f"房间「{room_name}」没有进行中的游戏"))

    if uid not in room["players"]:
        await surrender.finish(reply_msg(event, "你不是该房间的玩家"))

    winner_idx = 1 - room["players"].index(uid)
    room["winner"] = room["players"][winner_idx]
    room["status"] = "finished"
    rooms[rkey] = room
    board_data.set("rooms", rooms)

    try:
        mi = await bot.get_group_member_info(group_id=event.group_id, user_id=int(room["winner"]))
        wn = mi.get("card") or mi.get("nickname", str(room["winner"]))
    except Exception:
        wn = str(room["winner"])

    await surrender.finish(reply_msg(event, f"🏳️ {room['type']}「{room_name}」\n{_current_player_name(event, uid)} 认输！\n🎉 胜者：{wn}"))


# ---------- 退出棋局 ----------

@leave_room.handle()
async def handle_leave_room(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    uid = str(event.user_id)
    room_name = args.extract_plain_text().strip()
    if not room_name:
        await leave_room.finish(reply_msg(event, "请指定房间号，如：退出棋局 1号房"))

    rkey = _room_key(gid, room_name)
    rooms = board_data.get("rooms", {})
    room = rooms.get(rkey)

    if not room:
        await leave_room.finish(reply_msg(event, f"房间「{room_name}」不存在"))

    if uid not in room["players"]:
        await leave_room.finish(reply_msg(event, "你不在该房间中"))

    if room["status"] == "playing":
        await leave_room.finish(reply_msg(event, "游戏进行中，无法退出（可发送「认输」结束游戏）"))

    room["players"].remove(uid)
    if not room["players"]:
        del rooms[rkey]
        board_data.set("rooms", rooms)
        await leave_room.finish(reply_msg(event, f"已退出「{room_name}」，房间已删除"))
    else:
        rooms[rkey] = room
        board_data.set("rooms", rooms)
        await leave_room.finish(reply_msg(event, f"已退出「{room_name}」"))


# ---------- 帮助 ----------

board_help = on_command("下棋帮助", priority=1, block=True)

@board_help.handle()
async def handle_board_help(event: GroupMessageEvent):
    help_text = (
        "♟ 棋盘游戏玩法说明\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "📌 通用指令\n"
        "  创建棋局 [类型] [房间号]\n"
        "  加入棋局 [房间号]\n"
        "  下棋 [房间号] [行,列]\n"
        "  棋局列表 / 棋局信息 [房间号]\n"
        "  认输 [房间号] / 退出棋局 [房间号]\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🔲 五子棋 (15×15)\n"
        "  规则：黑白轮流落子，先连成五子的一方获胜。\n"
        "  坐标：1-15，如「下棋 1号房 8,8」表示第8行第8列。\n\n"
        "⚫ 围棋 (19×19)\n"
        "  规则：黑白轮流落子，提掉对方无气之子。\n"
        "  禁着：禁止自杀，禁止立即回提（劫）。\n"
        "  终局：双方连续弃着 → 数子法计分。\n"
        "  坐标：1-19，如「下棋 2号房 10,10」。\n\n"
        "🎲 飞行棋\n"
        "  规则：掷 6 出营，沿轨道前进，踩到对方棋子\n"
        "  则对方回到起点。支持 1 棋/4棋 模式。\n"
        "  操作：「下棋 [房间号]」无需坐标，自动掷骰。\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "发送「娱乐功能」查看所有子分类\n"
        "发送「棋盘游戏」查看本子分类全部指令"
    )
    await board_help.finish(reply_msg(event, help_text))


# ==================== 菜单注册 ====================
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 娱乐功能 -> 棋盘游戏
_BOARD_GAME_MENU_ITEMS = {
    "创建棋局": "♟ 创建棋局 类型 房间号",
    "加入棋局": "♟ 加入棋局 房间号",
    "棋局列表": "♟ 棋局列表",
    "下棋": "♟ 下棋 房间号 行,列",
    "棋局信息": "♟ 棋局信息 房间号",
    "认输": "♟ 认输 房间号",
    "退出棋局": "♟ 退出棋局 房间号",
    "下棋帮助": "♟ 下棋帮助",
}

for _item_name, _text in _BOARD_GAME_MENU_ITEMS.items():
    menu_registry.register(
        category="娱乐功能",
        item_name=_item_name,
        text=_text,
        subcategory="棋盘游戏",
        subcategory_title="♟◇━棋盘游戏━◇♟",
        subcategory_trigger="棋盘游戏",
        subcategory_description="五子棋·围棋·飞行棋",
    )
