import asyncio
import threading
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from collections import deque
import json
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_stats_file() -> str:
    return os.path.join(BASE_DIR, "config", "data", "message_stats.json")


class LogManager:
    def __init__(self, max_logs: int = 1000, stats_file: str = None):
        if stats_file is None:
            stats_file = _default_stats_file()
        self._logs: deque = deque(maxlen=max_logs)
        self._lock = threading.Lock()
        self._subscribers: List[Callable] = []
        self._stats_file = stats_file
        self._stats = self._load_stats()
        self._stats_dirty = False
        self._stats_save_timer: Optional[threading.Timer] = None
        self._stats_save_delay = 3.0

    def _load_stats(self) -> Dict[str, int]:
        try:
            with open(self._stats_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"total": 0, "messages": 0, "sent": 0, "received": 0, "commands": 0, "errors": 0, "connections": 0}

    def _mark_stats_dirty(self):
        self._stats_dirty = True
        if self._stats_save_timer and self._stats_save_timer.is_alive():
            self._stats_save_timer.cancel()
        self._stats_save_timer = threading.Timer(self._stats_save_delay, self._flush_stats)
        self._stats_save_timer.daemon = True
        self._stats_save_timer.start()

    def _flush_stats(self):
        if self._stats_dirty:
            self._save_stats()

    def _save_stats(self):
        try:
            Path(self._stats_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self._stats_file, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
            self._stats_dirty = False
        except Exception:
            pass

    def add_log(
        self,
        log_type: str,
        direction: str,
        content: str,
        extra: Optional[Dict[str, Any]] = None
    ):
        log_entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().timestamp(),
            "type": log_type,
            "direction": direction,
            "content": content,
            "extra": extra or {}
        }
        
        with self._lock:
            self._logs.append(log_entry)
            self._stats["total"] += 1
            if log_type == "message":
                self._stats["messages"] += 1
                if direction == "send":
                    self._stats["sent"] += 1
                elif direction == "receive":
                    self._stats["received"] += 1
            elif log_type == "command":
                self._stats["commands"] += 1
            elif log_type == "error":
                self._stats["errors"] += 1
            elif log_type == "connection":
                self._stats["connections"] += 1
            self._mark_stats_dirty()
        
        for subscriber in self._subscribers:
            try:
                subscriber(log_entry)
            except Exception:
                pass
    
    def log_message(
        self,
        direction: str,
        user_id: int,
        group_id: Optional[int],
        message: str,
        user_name: str = ""
    ):
        self.add_log(
            log_type="message",
            direction=direction,
            content=message[:200] if len(message) > 200 else message,
            extra={
                "user_id": user_id,
                "group_id": group_id,
                "user_name": user_name
            }
        )
    
    def log_connection(self, status: str, detail: str = ""):
        self.add_log(
            log_type="connection",
            direction="system",
            content=f"{status}" + (f" - {detail}" if detail else ""),
            extra={"status": status}
        )
    
    def log_command(
        self,
        user_id: int,
        group_id: int,
        command: str,
        result: str = ""
    ):
        self.add_log(
            log_type="command",
            direction="receive",
            content=command,
            extra={
                "user_id": user_id,
                "group_id": group_id,
                "result": result
            }
        )
    
    def log_notice(self, notice_type: str, detail: str = ""):
        self.add_log(
            log_type="notice",
            direction="system",
            content=f"{notice_type}" + (f" - {detail}" if detail else ""),
            extra={"notice_type": notice_type}
        )
    
    def log_error(self, error_msg: str, detail: str = ""):
        self.add_log(
            log_type="error",
            direction="system",
            content=f"{error_msg}" + (f" - {detail}" if detail else ""),
            extra={}
        )
    
    def get_logs(
        self,
        log_type: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._lock:
            logs = list(self._logs)
        
        if log_type:
            logs = [l for l in logs if l["type"] == log_type]
        if direction:
            logs = [l for l in logs if l["direction"] == direction]
        
        logs = logs[::-1]
        
        return logs[offset:offset + limit]
    
    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stats)
    
    def clear_logs(self):
        self.flush_stats()
        with self._lock:
            self._logs.clear()
            self._stats = self._load_stats()
            self._save_stats()

    def flush_stats(self):
        if self._stats_save_timer and self._stats_save_timer.is_alive():
            self._stats_save_timer.cancel()
            self._stats_save_timer = None
        self._flush_stats()
    
    def subscribe(self, callback: Callable):
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable):
        if callback in self._subscribers:
            self._subscribers.remove(callback)


log_manager = LogManager()
