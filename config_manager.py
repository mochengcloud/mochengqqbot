import json
import os
import random
import secrets
import string
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


AVAILABLE_FEATURES = ["群管系统", "统计系统", "签到系统", "积分系统", "定时功能", "站长工具", "新人系统", "验证系统", "提示系统", "自定义API", "AI聊天", "AI违规检测"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_config_path() -> str:
    return os.path.join(BASE_DIR, "config", "config.json")


class ConfigManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = _default_config_path()
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.group_names: Dict[str, str] = {}
        self._dirty = False
        self._save_timer: Optional[threading.Timer] = None
        self._save_delay = 3.0
        self._save_lock = threading.Lock()
        self._auth_init_done = False
        self.load()
    
    def _mark_dirty(self):
        self._dirty = True
        if self._save_timer and self._save_timer.is_alive():
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self._save_delay, self._flush)
        self._save_timer.daemon = True
        self._save_timer.start()
    
    def _flush(self):
        if self._dirty:
            self.save()

    def save_immediate(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def flush(self):
        if self._save_timer and self._save_timer.is_alive():
            self._save_timer.cancel()
            self._save_timer = None
        self._flush()
    
    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = self._get_default_config()
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_immediate()
        return self.config
    
    def save(self) -> None:
        with self._save_lock:
            self._dirty = False
            if self._save_timer and self._save_timer.is_alive():
                self._save_timer.cancel()
                self._save_timer = None
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "bot": {
                "superusers": [],
                "nickname": "陌城网络-qqbot",
                "command_start": [""]
            },
            "onebot": {
                "mode": "ws_client",
                "ws_client": {
                    "enabled": True,
                    "url": "ws://127.0.0.1:3001",
                    "access_token": "",
                    "reconnect_interval": 5,
                    "heartbeat_interval": 30
                },
                "ws_server": {
                    "enabled": False,
                    "host": "0.0.0.0",
                    "port": 3000,
                    "access_token": ""
                },
                "http": {
                    "enabled": False,
                    "url": "http://127.0.0.1:3000",
                    "access_token": "",
                    "timeout": 30
                }
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
                "webui_port": 8081
            },
            "menu": {
                "enabled": True,
                "title": "📋 菜单",
                "trigger": "菜单",
                "description": "发送对应名称查看详细功能"
            },
            "group_settings": {},
            "dispatch": {
                "max_concurrent": 16
            },
            "webui": {
                "access_token": "".join(random.choices(string.ascii_letters + string.digits, k=16)),
                "jwt_secret": secrets.token_hex(32)
            }
        }
    
    def is_group_enabled(self, group_id: int) -> bool:
        group_settings = self.config.get("group_settings", {}).get(str(group_id), {})
        return group_settings.get("enabled", True)
    
    def is_menu_enabled(self, group_id: int) -> bool:
        group_settings = self.config.get("group_settings", {}).get(str(group_id), {})
        return group_settings.get("menu_enabled", True)
    
    def set_group_enabled(self, group_id: int, enabled: bool) -> None:
        if str(group_id) not in self.config["group_settings"]:
            self.config["group_settings"][str(group_id)] = {}
        self.config["group_settings"][str(group_id)]["enabled"] = enabled
        self._mark_dirty()
    
    def set_menu_enabled(self, group_id: int, enabled: bool) -> None:
        if str(group_id) not in self.config["group_settings"]:
            self.config["group_settings"][str(group_id)] = {}
        self.config["group_settings"][str(group_id)]["menu_enabled"] = enabled
        self._mark_dirty()
    
    def set_menu_global_enabled(self, enabled: bool) -> None:
        """设置菜单全局开关。"""
        if "menu" not in self.config:
            self.config["menu"] = {}
        self.config["menu"]["enabled"] = enabled
        self._mark_dirty()

    def get_menu_config(self) -> Dict[str, Any]:
        """返回精简后的 menu 配置(仅开关与主菜单文案)。"""
        return self.config.get("menu", {
            "enabled": True,
            "title": "📋 菜单",
            "trigger": "菜单",
            "description": "发送对应名称查看详细功能"
        })

    def get_onebot_config(self) -> Dict[str, Any]:
        return self.config.get("onebot", {})
    
    def update_onebot_config(self, onebot_config: Dict[str, Any]) -> None:
        self.config["onebot"] = onebot_config
        self._mark_dirty()
    
    def update_onebot_mode(self, mode: str) -> None:
        if "onebot" not in self.config:
            self.config["onebot"] = self._get_default_config()["onebot"]
        self.config["onebot"]["mode"] = mode
        self._mark_dirty()
    
    def update_ws_client_config(self, ws_client_config: Dict[str, Any]) -> None:
        if "onebot" not in self.config:
            self.config["onebot"] = self._get_default_config()["onebot"]
        self.config["onebot"]["ws_client"] = ws_client_config
        self._mark_dirty()
    
    def update_ws_server_config(self, ws_server_config: Dict[str, Any]) -> None:
        if "onebot" not in self.config:
            self.config["onebot"] = self._get_default_config()["onebot"]
        self.config["onebot"]["ws_server"] = ws_server_config
        self._mark_dirty()
    
    def update_http_config(self, http_config: Dict[str, Any]) -> None:
        if "onebot" not in self.config:
            self.config["onebot"] = self._get_default_config()["onebot"]
        self.config["onebot"]["http"] = http_config
        self._mark_dirty()
    
    def get_server_config(self) -> Dict[str, Any]:
        return self.config.get("server", {"host": "0.0.0.0", "port": 8080, "webui_port": 8081})
    
    def update_server_config(self, server_config: Dict[str, Any]) -> None:
        self.config["server"] = server_config
        self._mark_dirty()

    def get_dispatch_config(self) -> Dict[str, Any]:
        """获取分发并发配置。"""
        if "dispatch" not in self.config:
            self.config["dispatch"] = {"max_concurrent": 16}
            self._mark_dirty()
        return self.config["dispatch"]

    def update_dispatch_config(self, data: Dict[str, Any]) -> None:
        """更新分发并发配置。"""
        if "dispatch" not in self.config:
            self.config["dispatch"] = {"max_concurrent": 16}
        if "max_concurrent" in data:
            mc = data["max_concurrent"]
            if isinstance(mc, (int, float)) and mc >= 1:
                self.config["dispatch"]["max_concurrent"] = int(mc)
        self._mark_dirty()
    
    def get_bot_config(self) -> Dict[str, Any]:
        return self.config.get("bot", {})
    
    def update_bot_config(self, bot_config: Dict[str, Any]) -> None:
        self.config["bot"] = bot_config
        self._mark_dirty()
    
    def _get_default_verify_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "mode": "number",
            "timeout_kick": False,
            "timeout_minutes": 5,
            "welcome_prompt": "欢迎加入本群！请完成验证以继续",
            "success_prompt": "✅ 验证通过，欢迎加入！",
            "timeout_prompt": "⏰ 验证超时，你已被移出群聊"
        }

    def _ensure_verify_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "verify" not in gs:
            gs["verify"] = self._get_default_verify_config()
            self._mark_dirty()
        return gs["verify"]

    def get_verify_config(self, group_id: int) -> Dict[str, Any]:
        verify = self._ensure_verify_config(group_id)
        return verify

    def set_verify_enabled(self, group_id: int, enabled: bool) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["enabled"] = enabled
        self._mark_dirty()

    def set_verify_mode(self, group_id: int, mode: str) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["mode"] = mode
        self._mark_dirty()

    def set_verify_timeout_kick(self, group_id: int, enabled: bool) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["timeout_kick"] = enabled
        self._mark_dirty()

    def set_verify_timeout_minutes(self, group_id: int, minutes: int) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["timeout_minutes"] = minutes
        self._mark_dirty()

    def set_verify_welcome_prompt(self, group_id: int, prompt: str) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["welcome_prompt"] = prompt
        self._mark_dirty()

    def set_verify_success_prompt(self, group_id: int, prompt: str) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["success_prompt"] = prompt
        self._mark_dirty()

    def set_verify_timeout_prompt(self, group_id: int, prompt: str) -> None:
        verify = self._ensure_verify_config(group_id)
        verify["timeout_prompt"] = prompt
        self._mark_dirty()

    def _get_default_newcomer_config(self) -> Dict[str, Any]:
        return {
            "join_mode": "none",
            "reject_level_below": 0,
            "reject_nickname_contains": [],
            "reject_sign_contains": [],
            "mute_minutes": 0
        }

    def _ensure_newcomer_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "newcomer" not in gs:
            gs["newcomer"] = self._get_default_newcomer_config()
            self._mark_dirty()
        return gs["newcomer"]

    def get_newcomer_config(self, group_id: int) -> Dict[str, Any]:
        newcomer = self._ensure_newcomer_config(group_id)
        return newcomer

    def set_newcomer_join_mode(self, group_id: int, mode: str) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        newcomer["join_mode"] = mode
        self._mark_dirty()

    def set_newcomer_reject_level(self, group_id: int, level: int) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        newcomer["reject_level_below"] = level
        self._mark_dirty()

    def add_newcomer_reject_nickname(self, group_id: int, keyword: str) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        if "reject_nickname_contains" not in newcomer:
            newcomer["reject_nickname_contains"] = []
        if keyword not in newcomer["reject_nickname_contains"]:
            newcomer["reject_nickname_contains"].append(keyword)
            self._mark_dirty()

    def remove_newcomer_reject_nickname(self, group_id: int, keyword: str) -> bool:
        newcomer = self._ensure_newcomer_config(group_id)
        if "reject_nickname_contains" in newcomer and keyword in newcomer["reject_nickname_contains"]:
            newcomer["reject_nickname_contains"].remove(keyword)
            self._mark_dirty()
            return True
        return False

    def add_newcomer_reject_sign(self, group_id: int, keyword: str) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        if "reject_sign_contains" not in newcomer:
            newcomer["reject_sign_contains"] = []
        if keyword not in newcomer["reject_sign_contains"]:
            newcomer["reject_sign_contains"].append(keyword)
            self._mark_dirty()

    def remove_newcomer_reject_sign(self, group_id: int, keyword: str) -> bool:
        newcomer = self._ensure_newcomer_config(group_id)
        if "reject_sign_contains" in newcomer and keyword in newcomer["reject_sign_contains"]:
            newcomer["reject_sign_contains"].remove(keyword)
            self._mark_dirty()
            return True
        return False

    def set_newcomer_mute_minutes(self, group_id: int, minutes: int) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        newcomer["mute_minutes"] = minutes
        self._mark_dirty()

    def _get_default_checkin_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "send_like": False,
            "reward_min": 1,
            "reward_max": 10,
            "penalty_enabled": False,
            "penalty_deduction": 5,
            "low_points_block_enabled": False,
            "low_points_threshold": 0
        }

    def _ensure_checkin_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "checkin" not in gs:
            gs["checkin"] = self._get_default_checkin_config()
            self._mark_dirty()
        return gs["checkin"]

    def get_checkin_config(self, group_id: int) -> Dict[str, Any]:
        checkin = self._ensure_checkin_config(group_id)
        return checkin

    def set_checkin_enabled(self, group_id: int, enabled: bool) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["enabled"] = enabled
        self._mark_dirty()

    def set_checkin_send_like(self, group_id: int, enabled: bool) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["send_like"] = enabled
        self._mark_dirty()

    def set_checkin_reward(self, group_id: int, min_val: int, max_val: int) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["reward_min"] = min_val
        checkin["reward_max"] = max_val
        self._mark_dirty()

    def set_checkin_penalty_enabled(self, group_id: int, enabled: bool) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["penalty_enabled"] = enabled
        self._mark_dirty()

    def set_checkin_penalty_deduction(self, group_id: int, deduction: int) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["penalty_deduction"] = deduction
        self._mark_dirty()

    def set_checkin_low_points_block(self, group_id: int, enabled: bool) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["low_points_block_enabled"] = enabled
        self._mark_dirty()

    def set_checkin_low_points_threshold(self, group_id: int, threshold: int) -> None:
        checkin = self._ensure_checkin_config(group_id)
        checkin["low_points_threshold"] = threshold
        self._mark_dirty()
    
    def _get_default_essence_config(self) -> Dict[str, Any]:
        return {"enabled": False}
    
    def _ensure_essence_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "essence" not in gs:
            gs["essence"] = self._get_default_essence_config()
            self._mark_dirty()
        return gs["essence"]
    
    def get_essence_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_essence_config(group_id)
    
    def set_essence_enabled(self, group_id: int, enabled: bool) -> None:
        cfg = self._ensure_essence_config(group_id)
        cfg["enabled"] = enabled
        self._mark_dirty()
    
    def _get_default_notify_config(self) -> Dict[str, Any]:
        return {
            "welcome_enabled": False,
            "welcome_text": "欢迎加入本群！",
            "join_private_enabled": False,
            "join_private_text": "欢迎加入本群，请遵守群规！",
            "kick_enabled": False,
            "kick_text": "已被踢出本群",
            "admin_set_enabled": False,
            "admin_set_text": "恭喜成为本群管理员！",
            "admin_unset_enabled": False,
            "admin_unset_text": "已被取消管理员身份",
            "leave_enabled": False,
            "leave_text": "已离开本群"
        }

    def _ensure_notify_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "notify" not in gs:
            gs["notify"] = self._get_default_notify_config()
            self._mark_dirty()
        return gs["notify"]

    def get_notify_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_notify_config(group_id)

    def set_notify_welcome_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["welcome_enabled"] = enabled
        self._mark_dirty()

    def set_notify_welcome_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["welcome_text"] = text
        self._mark_dirty()

    def set_notify_join_private_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["join_private_enabled"] = enabled
        self._mark_dirty()

    def set_notify_join_private_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["join_private_text"] = text
        self._mark_dirty()

    def set_notify_kick_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["kick_enabled"] = enabled
        self._mark_dirty()

    def set_notify_kick_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["kick_text"] = text
        self._mark_dirty()

    def set_notify_admin_set_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["admin_set_enabled"] = enabled
        self._mark_dirty()

    def set_notify_admin_set_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["admin_set_text"] = text
        self._mark_dirty()

    def set_notify_admin_unset_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["admin_unset_enabled"] = enabled
        self._mark_dirty()

    def set_notify_admin_unset_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["admin_unset_text"] = text
        self._mark_dirty()

    def set_notify_leave_enabled(self, group_id: int, enabled: bool) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["leave_enabled"] = enabled
        self._mark_dirty()

    def set_notify_leave_text(self, group_id: int, text: str) -> None:
        notify = self._ensure_notify_config(group_id)
        notify["leave_text"] = text
        self._mark_dirty()

    def update_notify_config(self, group_id: int, config: Dict[str, Any]) -> None:
        notify = self._ensure_notify_config(group_id)
        for key, value in config.items():
            if value is not None:
                notify[key] = value
        self._mark_dirty()

    def update_checkin_config(self, group_id: int, config: Dict[str, Any]) -> None:
        checkin = self._ensure_checkin_config(group_id)
        for key, value in config.items():
            if value is not None:
                checkin[key] = value
        self._mark_dirty()

    def update_verify_config(self, group_id: int, config: Dict[str, Any]) -> None:
        verify = self._ensure_verify_config(group_id)
        for key, value in config.items():
            if value is not None:
                verify[key] = value
        self._mark_dirty()

    def update_newcomer_config(self, group_id: int, config: Dict[str, Any]) -> None:
        newcomer = self._ensure_newcomer_config(group_id)
        for key, value in config.items():
            if value is not None:
                newcomer[key] = value
        self._mark_dirty()

    def update_superusers(self, superusers: List[str]) -> None:
        if "bot" not in self.config:
            self.config["bot"] = {}
        self.config["bot"]["superusers"] = superusers
        self._mark_dirty()

    def get_webui_config(self) -> Dict[str, Any]:
        if "webui" not in self.config:
            self.config["webui"] = {
                "access_token": "".join(random.choices(string.ascii_letters + string.digits, k=16)),
                "jwt_secret": secrets.token_hex(32)
            }
            self._mark_dirty()
        return self.config["webui"]

    def update_webui_access_token(self, token: str) -> None:
        self.get_webui_config()
        self.config["webui"]["access_token"] = token
        self._mark_dirty()

    def _get_default_authorization_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "groups": {},
            "codes": {},
            "authorizations": {}
        }

    def _ensure_authorization_config(self) -> Dict[str, Any]:
        if "authorization" not in self.config:
            self.config["authorization"] = self._get_default_authorization_config()
            self._auth_init_done = False
        auth = self.config["authorization"]
        if getattr(self, '_auth_init_done', False):
            return auth
        if "enabled" not in auth:
            auth["enabled"] = False
        if "groups" not in auth:
            auth["groups"] = {}
        if "codes" not in auth:
            auth["codes"] = {}
        if "authorizations" not in auth:
            auth["authorizations"] = {}
        need_save = False
        for group_data in auth.get("groups", {}).values():
            perms = group_data.get("permissions", [])
            for feature in AVAILABLE_FEATURES:
                if feature not in perms:
                    perms.append(feature)
                    need_save = True
            group_data["permissions"] = perms
        if need_save:
            self._mark_dirty()
        self._auth_init_done = True
        return auth

    def is_authorization_enabled(self) -> bool:
        auth = self.config.get("authorization", {})
        return auth.get("enabled", False)

    def set_authorization_enabled(self, enabled: bool) -> None:
        self._ensure_authorization_config()
        self.config["authorization"]["enabled"] = enabled
        self._mark_dirty()

    def get_auth_groups(self) -> Dict[str, Any]:
        auth = self._ensure_authorization_config()
        return auth.get("groups", {})

    def add_auth_group(self, name: str, permissions: List[str]) -> None:
        auth = self._ensure_authorization_config()
        auth["groups"][name] = {"permissions": permissions}
        self._mark_dirty()

    def update_auth_group(self, name: str, permissions: List[str]) -> None:
        auth = self._ensure_authorization_config()
        if name not in auth["groups"]:
            auth["groups"][name] = {"permissions": permissions}
        else:
            auth["groups"][name]["permissions"] = permissions
        self._mark_dirty()

    def delete_auth_group(self, name: str) -> bool:
        auth = self._ensure_authorization_config()
        if name in auth.get("groups", {}):
            del auth["groups"][name]
            self._mark_dirty()
            return True
        return False

    def generate_auth_code(self) -> str:
        auth = self._ensure_authorization_config()
        while True:
            parts = []
            for _ in range(3):
                part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
                parts.append(part)
            code = "-".join(parts)
            if code not in auth.get("codes", {}):
                return code

    def create_auth_code(self, expire_time: Optional[str], auth_group: str, max_uses: int = 1) -> str:
        auth = self._ensure_authorization_config()
        code = self.generate_auth_code()
        auth["codes"][code] = {
            "expire_time": expire_time,
            "auth_group": auth_group,
            "max_uses": max_uses,
            "use_count": 0,
            "used_by": []
        }
        self._mark_dirty()
        return code

    def get_auth_codes(self) -> Dict[str, Any]:
        auth = self._ensure_authorization_config()
        return auth.get("codes", {})

    def delete_auth_code(self, code: str) -> bool:
        auth = self._ensure_authorization_config()
        if code not in auth.get("codes", {}):
            return False
        code_data = auth["codes"][code]
        for gid in code_data.get("used_by", []):
            if gid in auth.get("authorizations", {}):
                del auth["authorizations"][gid]
        del auth["codes"][code]
        self._mark_dirty()
        return True

    def use_auth_code(self, code: str, group_id: int) -> bool:
        auth = self._ensure_authorization_config()
        gid = str(group_id)
        if code not in auth.get("codes", {}):
            return False
        code_data = auth["codes"][code]
        if code_data["max_uses"] > 0 and code_data["use_count"] >= code_data["max_uses"]:
            return False
        if code_data.get("expire_time"):
            try:
                expire_dt = datetime.fromisoformat(code_data["expire_time"])
                if expire_dt < datetime.now():
                    return False
            except (ValueError, TypeError):
                pass
        if gid in code_data.get("used_by", []):
            return False
        code_data["use_count"] += 1
        if "used_by" not in code_data:
            code_data["used_by"] = []
        code_data["used_by"].append(gid)
        auth["authorizations"][gid] = {
            "expire_time": code_data["expire_time"],
            "auth_group": code_data["auth_group"],
            "activate_time": datetime.now().isoformat(),
            "code": code
        }
        self._mark_dirty()
        return True

    def release_auth_code(self, code: str, group_id: int) -> bool:
        auth = self._ensure_authorization_config()
        gid = str(group_id)
        if code not in auth.get("codes", {}):
            return False
        code_data = auth["codes"][code]
        if gid in code_data.get("used_by", []):
            code_data["used_by"].remove(gid)
            code_data["use_count"] = max(0, code_data["use_count"] - 1)
            self._mark_dirty()
            return True
        return False

    def get_authorizations(self) -> Dict[str, Any]:
        auth = self._ensure_authorization_config()
        return auth.get("authorizations", {})

    def get_group_authorization(self, group_id: int) -> Optional[Dict[str, Any]]:
        auth = self._ensure_authorization_config()
        return auth.get("authorizations", {}).get(str(group_id))

    def remove_group_authorization(self, group_id: int) -> bool:
        auth = self._ensure_authorization_config()
        gid = str(group_id)
        if gid not in auth.get("authorizations", {}):
            return False
        auth_info = auth["authorizations"][gid]
        old_code = auth_info.get("code")
        if old_code and old_code in auth.get("codes", {}):
            self.release_auth_code(old_code, group_id)
        del auth["authorizations"][gid]
        self._mark_dirty()
        return True

    def rebind_group_authorization(self, group_id: int, new_code: str) -> bool:
        auth = self._ensure_authorization_config()
        gid = str(group_id)
        if new_code not in auth.get("codes", {}):
            return False
        new_code_data = auth["codes"][new_code]
        if new_code_data["max_uses"] > 0 and new_code_data["use_count"] >= new_code_data["max_uses"]:
            return False
        if new_code_data.get("expire_time"):
            try:
                expire_dt = datetime.fromisoformat(new_code_data["expire_time"])
                if expire_dt < datetime.now():
                    return False
            except (ValueError, TypeError):
                pass
        if gid in auth.get("authorizations", {}):
            old_auth = auth["authorizations"][gid]
            old_code = old_auth.get("code")
            if old_code and old_code in auth.get("codes", {}):
                self.release_auth_code(old_code, group_id)
        new_code_data["use_count"] += 1
        if "used_by" not in new_code_data:
            new_code_data["used_by"] = []
        new_code_data["used_by"].append(gid)
        auth["authorizations"][gid] = {
            "expire_time": new_code_data["expire_time"],
            "auth_group": new_code_data["auth_group"],
            "activate_time": datetime.now().isoformat(),
            "code": new_code
        }
        self._mark_dirty()
        return True

    def is_group_authorized(self, group_id: int) -> bool:
        auth = self.config.get("authorization")
        if not auth or not auth.get("enabled", False):
            return True
        gid = str(group_id)
        auth_info = auth.get("authorizations", {}).get(gid)
        if not auth_info:
            return False
        expire_time = auth_info.get("expire_time")
        if expire_time:
            try:
                expire_dt = datetime.fromisoformat(expire_time)
                if expire_dt < datetime.now():
                    return False
            except (ValueError, TypeError):
                pass
        return True

    def is_feature_authorized(self, group_id: int, feature_name: str) -> bool:
        auth = self._ensure_authorization_config()
        if not auth.get("enabled", False):
            return True
        if not self.is_group_authorized(group_id):
            return False
        gid = str(group_id)
        auth_info = auth.get("authorizations", {}).get(gid)
        if not auth_info:
            return False
        auth_group_name = auth_info.get("auth_group")
        if not auth_group_name:
            return False
        auth_group = auth.get("groups", {}).get(auth_group_name)
        if not auth_group:
            return False
        permissions = auth_group.get("permissions", [])
        return feature_name in permissions

    def get_group_permissions(self, group_id: int) -> List[str]:
        auth = self._ensure_authorization_config()
        if not auth.get("enabled", False):
            return list(AVAILABLE_FEATURES)
        if not self.is_group_authorized(group_id):
            return []
        gid = str(group_id)
        auth_info = auth.get("authorizations", {}).get(gid)
        if not auth_info:
            return []
        auth_group_name = auth_info.get("auth_group")
        if not auth_group_name:
            return []
        auth_group = auth.get("groups", {}).get(auth_group_name)
        if not auth_group:
            return []
        return auth_group.get("permissions", [])


    def _get_default_webmaster_config(self) -> Dict[str, Any]:
        return {
            "enabled": False
        }

    def _ensure_webmaster_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "webmaster" not in gs:
            gs["webmaster"] = self._get_default_webmaster_config()
            self._mark_dirty()
        return gs["webmaster"]

    def get_webmaster_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_webmaster_config(group_id)

    def set_webmaster_enabled(self, group_id: int, enabled: bool) -> None:
        webmaster = self._ensure_webmaster_config(group_id)
        webmaster["enabled"] = enabled
        self._mark_dirty()

    def update_webmaster_config(self, group_id: int, config: Dict[str, Any]) -> None:
        webmaster = self._ensure_webmaster_config(group_id)
        for key, value in config.items():
            if value is not None:
                webmaster[key] = value
        self._mark_dirty()

    def update_schedule_config(self, group_id: int, config: Dict[str, Any]) -> None:
        schedule = self._ensure_schedule_config(group_id)
        for key, value in config.items():
            if value is not None:
                schedule[key] = value
        self._mark_dirty()

    def _get_default_schedule_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "mute": {
                "enabled": False,
                "hour": 22,
                "minute": 0,
                "prompt": "晚安时间到，请保持安静~"
            },
            "unmute": {
                "enabled": False,
                "hour": 7,
                "minute": 0,
                "prompt": "早上好，解除禁言啦~"
            },
            "broadcasts": [],
            "hourly_chime": {
                "enabled": False,
                "template": "现在是{hour}点整"
            },
            "next_broadcast_id": 1
        }

    def _ensure_schedule_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "schedule" not in gs:
            gs["schedule"] = self._get_default_schedule_config()
            self._mark_dirty()
        return gs["schedule"]

    def get_schedule_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_schedule_config(group_id)

    def set_schedule_enabled(self, group_id: int, enabled: bool) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["enabled"] = enabled
        self._mark_dirty()

    def set_mute_time(self, group_id: int, hour: int, minute: int) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["mute"]["enabled"] = True
        schedule["mute"]["hour"] = hour
        schedule["mute"]["minute"] = minute
        self._mark_dirty()

    def set_mute_prompt(self, group_id: int, prompt: str) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["mute"]["prompt"] = prompt
        self._mark_dirty()

    def set_unmute_time(self, group_id: int, hour: int, minute: int) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["unmute"]["enabled"] = True
        schedule["unmute"]["hour"] = hour
        schedule["unmute"]["minute"] = minute
        self._mark_dirty()

    def set_unmute_prompt(self, group_id: int, prompt: str) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["unmute"]["prompt"] = prompt
        self._mark_dirty()

    def add_broadcast(self, group_id: int, hour: int, minute: int, content: str) -> int:
        schedule = self._ensure_schedule_config(group_id)
        broadcast_id = schedule.get("next_broadcast_id", 1)
        schedule["broadcasts"].append({
            "id": broadcast_id,
            "hour": hour,
            "minute": minute,
            "content": content,
            "enabled": True
        })
        schedule["next_broadcast_id"] = broadcast_id + 1
        self._mark_dirty()
        return broadcast_id

    def remove_broadcast(self, group_id: int, broadcast_id: int) -> bool:
        schedule = self._ensure_schedule_config(group_id)
        broadcasts = schedule.get("broadcasts", [])
        for i, b in enumerate(broadcasts):
            if b["id"] == broadcast_id:
                broadcasts.pop(i)
                self._mark_dirty()
                return True
        return False

    def set_hourly_chime(self, group_id: int, enabled: bool) -> None:
        schedule = self._ensure_schedule_config(group_id)
        schedule["hourly_chime"]["enabled"] = enabled
        self._mark_dirty()

    def clear_schedule(self, group_id: int) -> None:
        schedule = self._ensure_schedule_config(group_id)
        default = self._get_default_schedule_config()
        schedule["mute"] = default["mute"]
        schedule["unmute"] = default["unmute"]
        schedule["broadcasts"] = default["broadcasts"]
        schedule["hourly_chime"] = default["hourly_chime"]
        schedule["next_broadcast_id"] = default["next_broadcast_id"]
        self._mark_dirty()

    def _get_default_points_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "gifts": {},
            "lottery": {
                "cost": 10,
                "prizes": [
                    {"name": "一等奖", "probability": 5, "reward_points": 100},
                    {"name": "二等奖", "probability": 15, "reward_points": 50},
                    {"name": "三等奖", "probability": 30, "reward_points": 20},
                    {"name": "谢谢参与", "probability": 50, "reward_points": 0}
                ]
            },
            "transfer": {
                "enabled": True,
                "fee_rate": 10
            }
        }

    def _ensure_points_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "points" not in gs:
            gs["points"] = self._get_default_points_config()
            self._mark_dirty()
        return gs["points"]

    def get_points_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_points_config(group_id)

    def set_points_enabled(self, group_id: int, enabled: bool) -> None:
        points = self._ensure_points_config(group_id)
        points["enabled"] = enabled
        self._mark_dirty()

    def add_gift(self, group_id: int, name: str, points_cost: int, description: str = "", stock: int = -1) -> None:
        points = self._ensure_points_config(group_id)
        if "gifts" not in points:
            points["gifts"] = {}
        points["gifts"][name] = {
            "points": points_cost,
            "description": description,
            "stock": stock
        }
        self._mark_dirty()

    def remove_gift(self, group_id: int, name: str) -> bool:
        points = self._ensure_points_config(group_id)
        if "gifts" in points and name in points["gifts"]:
            del points["gifts"][name]
            self._mark_dirty()
            return True
        return False

    def get_gifts(self, group_id: int) -> Dict[str, Any]:
        points = self._ensure_points_config(group_id)
        return points.get("gifts", {})

    def set_lottery_cost(self, group_id: int, cost: int) -> None:
        points = self._ensure_points_config(group_id)
        if "lottery" not in points:
            points["lottery"] = {"cost": cost, "prizes": []}
        points["lottery"]["cost"] = cost
        self._mark_dirty()

    def set_lottery_prizes(self, group_id: int, prizes: List[Dict[str, Any]]) -> None:
        points = self._ensure_points_config(group_id)
        if "lottery" not in points:
            points["lottery"] = {"cost": 10, "prizes": prizes}
        points["lottery"]["prizes"] = prizes
        self._mark_dirty()

    def get_lottery_config(self, group_id: int) -> Dict[str, Any]:
        points = self._ensure_points_config(group_id)
        return points.get("lottery", {"cost": 10, "prizes": []})

    def set_transfer_fee_rate(self, group_id: int, rate: int) -> None:
        points = self._ensure_points_config(group_id)
        if "transfer" not in points:
            points["transfer"] = {"enabled": True, "fee_rate": rate}
        points["transfer"]["fee_rate"] = rate
        self._mark_dirty()

    def set_transfer_enabled(self, group_id: int, enabled: bool) -> None:
        points = self._ensure_points_config(group_id)
        if "transfer" not in points:
            points["transfer"] = {"enabled": enabled, "fee_rate": 10}
        points["transfer"]["enabled"] = enabled
        self._mark_dirty()

    def get_transfer_config(self, group_id: int) -> Dict[str, Any]:
        points = self._ensure_points_config(group_id)
        return points.get("transfer", {"enabled": True, "fee_rate": 10})

    def update_points_config(self, group_id: int, config: Dict[str, Any]) -> None:
        points = self._ensure_points_config(group_id)
        for key, value in config.items():
            if value is not None:
                points[key] = value
        self._mark_dirty()


    def _get_default_custom_api_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "apis": {}
        }

    def _ensure_custom_api_config(self) -> Dict[str, Any]:
        if "custom_api" not in self.config:
            self.config["custom_api"] = self._get_default_custom_api_config()
            self._mark_dirty()
        custom_api = self.config["custom_api"]
        if "enabled" not in custom_api:
            custom_api["enabled"] = True
        if "apis" not in custom_api:
            custom_api["apis"] = {}
        return custom_api

    def get_custom_api_config(self) -> Dict[str, Any]:
        return self._ensure_custom_api_config()

    def set_custom_api_enabled(self, enabled: bool) -> None:
        custom_api = self._ensure_custom_api_config()
        custom_api["enabled"] = enabled
        self._mark_dirty()

    def get_custom_apis(self) -> Dict[str, Any]:
        custom_api = self._ensure_custom_api_config()
        return custom_api.get("apis", {})

    def add_custom_api(self, name: str, trigger: str, url: str, method: str = "GET",
                       response_type: str = "text", json_path: str = "",
                       timeout: int = 10, headers: Optional[Dict[str, str]] = None,
                       enabled: bool = True) -> None:
        custom_api = self._ensure_custom_api_config()
        custom_api["apis"][name] = {
            "enabled": enabled,
            "trigger": trigger,
            "url": url,
            "method": method,
            "response_type": response_type,
            "json_path": json_path,
            "timeout": timeout,
            "headers": headers or {}
        }
        self._mark_dirty()

    def update_custom_api(self, name: str, **kwargs) -> bool:
        custom_api = self._ensure_custom_api_config()
        if name not in custom_api["apis"]:
            return False
        api = custom_api["apis"][name]
        for key, value in kwargs.items():
            if value is not None:
                api[key] = value
        self._mark_dirty()
        return True

    def delete_custom_api(self, name: str) -> bool:
        custom_api = self._ensure_custom_api_config()
        if name not in custom_api.get("apis", {}):
            return False
        del custom_api["apis"][name]
        self._mark_dirty()
        return True

    def get_custom_api_by_trigger(self, trigger: str) -> Optional[Dict[str, Any]]:
        custom_api = self._ensure_custom_api_config()
        for name, api_config in custom_api.get("apis", {}).items():
            if api_config.get("enabled", True) and api_config.get("trigger") == trigger:
                return {"name": name, **api_config}
        return None

    def get_all_custom_api_triggers(self) -> List[str]:
        custom_api = self._ensure_custom_api_config()
        triggers = []
        for name, api_config in custom_api.get("apis", {}).items():
            if api_config.get("enabled", True):
                trigger = api_config.get("trigger", "")
                if trigger:
                    triggers.append(trigger)
        return triggers

    def sync_group_list(self, groups_data: list) -> int:
        if "group_settings" not in self.config:
            self.config["group_settings"] = {}
        added = 0
        current_gids = set()
        for group in groups_data:
            gid = str(group.get("group_id", ""))
            if not gid:
                continue
            current_gids.add(gid)
            if gid not in self.config["group_settings"]:
                self.config["group_settings"][gid] = {}
                added += 1
            group_name = group.get("group_name", "")
            if group_name:
                self.group_names[gid] = group_name
                # 持久化群名到 group_settings,重启后不丢失
                if gid in self.config["group_settings"]:
                    self.config["group_settings"][gid]["group_name"] = group_name
        # 删除已退出的群
        removed = 0
        for gid in list(self.config["group_settings"].keys()):
            if gid not in current_gids:
                del self.config["group_settings"][gid]
                self.group_names.pop(gid, None)
                removed += 1
        self._mark_dirty()
        return added, removed

    def get_group_name(self, group_id: str) -> str:
        return self.group_names.get(str(group_id), "")

    # ============ 群 WebUI 独立面板 Token ============

    def get_group_webui_token(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        gs = self.config.get("group_settings", {}).get(gid, {})
        return {
            "token": gs.get("webui_token", ""),
            "enabled": gs.get("webui_enabled", False),
        }

    def set_group_webui_token(self, group_id: int, token: str) -> None:
        gid = str(group_id)
        if "group_settings" not in self.config:
            self.config["group_settings"] = {}
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        self.config["group_settings"][gid]["webui_token"] = token
        self._mark_dirty()

    def generate_group_webui_token(self, group_id: int) -> str:
        token = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        self.set_group_webui_token(group_id, token)
        return token

    def set_group_webui_enabled(self, group_id: int, enabled: bool) -> None:
        gid = str(group_id)
        if "group_settings" not in self.config:
            self.config["group_settings"] = {}
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        self.config["group_settings"][gid]["webui_enabled"] = enabled
        self._mark_dirty()

    def delete_group_webui_token(self, group_id: int) -> None:
        gid = str(group_id)
        gs = self.config.get("group_settings", {}).get(gid)
        if gs:
            gs.pop("webui_token", None)
            gs.pop("webui_enabled", None)
            self._mark_dirty()

    def _get_default_ai_chat_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "providers": {}
        }

    def _ensure_ai_chat_config(self) -> Dict[str, Any]:
        if "ai_chat" not in self.config:
            self.config["ai_chat"] = self._get_default_ai_chat_config()
            self._mark_dirty()
        ai_chat = self.config["ai_chat"]
        if "enabled" not in ai_chat:
            ai_chat["enabled"] = True
        if "providers" not in ai_chat:
            ai_chat["providers"] = {}
        return ai_chat

    def get_ai_chat_config(self) -> Dict[str, Any]:
        return self._ensure_ai_chat_config()

    def set_ai_chat_enabled(self, enabled: bool) -> None:
        ai_chat = self._ensure_ai_chat_config()
        ai_chat["enabled"] = enabled
        self._mark_dirty()

    def get_ai_providers(self) -> Dict[str, Any]:
        ai_chat = self._ensure_ai_chat_config()
        return ai_chat.get("providers", {})

    def add_ai_provider(self, name: str, api_base: str, api_key: str,
                        default_model: str = "", enabled: bool = True,
                        api_format: str = "openai") -> None:
        ai_chat = self._ensure_ai_chat_config()
        ai_chat["providers"][name] = {
            "api_base": api_base,
            "api_key": api_key,
            "default_model": default_model,
            "enabled": enabled,
            "api_format": api_format
        }
        self._mark_dirty()

    def update_ai_provider(self, name: str, **kwargs) -> bool:
        ai_chat = self._ensure_ai_chat_config()
        if name not in ai_chat["providers"]:
            return False
        provider = ai_chat["providers"][name]
        for key, value in kwargs.items():
            if value is not None:
                provider[key] = value
        self._mark_dirty()
        return True

    def delete_ai_provider(self, name: str) -> bool:
        ai_chat = self._ensure_ai_chat_config()
        if name not in ai_chat.get("providers", {}):
            return False
        del ai_chat["providers"][name]
        self._mark_dirty()
        return True

    def _get_default_ai_chat_group_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "provider": "",
            "model": "",
            "system_prompt": "你是一个友好的AI助手",
            "max_context": 10,
            "max_tokens": 2048,
            "temperature": 0.7,
            "proactive_reply": False,
            "proactive_reply_probability": 0.1
        }

    def _ensure_ai_chat_group_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "ai_chat" not in gs:
            gs["ai_chat"] = self._get_default_ai_chat_group_config()
            self._mark_dirty()
        if gid not in getattr(self, '_ai_chat_group_init', set()):
            if not hasattr(self, '_ai_chat_group_init'):
                self._ai_chat_group_init = set()
            changed = False
            for old_key in ("trigger", "trigger_modes", "at_trigger"):
                if old_key in gs["ai_chat"]:
                    gs["ai_chat"].pop(old_key)
                    changed = True
            if changed:
                self._mark_dirty()
            self._ai_chat_group_init.add(gid)
        return gs["ai_chat"]

    def get_ai_chat_group_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_ai_chat_group_config(group_id)

    def update_ai_chat_group_config(self, group_id: int, config: Dict[str, Any]) -> None:
        ai_chat = self._ensure_ai_chat_group_config(group_id)
        for key, value in config.items():
            if value is not None:
                ai_chat[key] = value
        self._mark_dirty()


    def update_group_name(self, group_id: str, name: str) -> None:
        if name:
            self.group_names[str(group_id)] = name


    # === AI违规检测配置 ===

    def _get_default_content_check_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "provider": "",
            "model": "",
            "violation_types": {
                "广告": {"enabled": True, "description": "推销产品、带联系方式（QQ/微信/链接/网盘/资源号/二维码），包括标准链接、变体链接写法（如'点'代替'.'、'dot'代替'.'、空格或符号隔开、谐音替换）、明显指向某个站点的域名/子域名、任何形式的引流信息（加好友、进群、私聊领福利、刷单等）"},
                "脏话": {"enabled": True, "description": "含侮辱性脏词（如SB、TMD、草泥马、傻逼）或明显的粗俗用语"},
                "骂人": {"enabled": True, "description": "人身攻击、诅咒、羞辱对方或其家人（如'你去死''你智商有问题''全家'）"},
                "色情": {"enabled": True, "description": "描述性行为、露骨色情用语、求资源/视频/网站/网盘、约炮、发'你懂的'等隐晦色情暗示"}
            },
            "custom_prompt": "",
            "warning_template": "@用户 ⚠️ 你的发言因【{type}】已被撤回",
            "temperature": 0.1,
            "max_tokens": 128,
            "max_concurrent": 10
        }

    def _ensure_content_check_config(self, group_id: int) -> Dict[str, Any]:
        gid = str(group_id)
        if gid not in self.config["group_settings"]:
            self.config["group_settings"][gid] = {}
        gs = self.config["group_settings"][gid]
        if "content_check" not in gs:
            gs["content_check"] = self._get_default_content_check_config()
            self._mark_dirty()
        if gid in getattr(self, '_content_check_init', set()):
            return gs["content_check"]
        if not hasattr(self, '_content_check_init'):
            self._content_check_init = set()
        cc = gs["content_check"]
        changed = False
        default = self._get_default_content_check_config()
        for key, val in default.items():
            if key not in cc:
                cc[key] = val
                changed = True
        default_types = default["violation_types"]
        if "violation_types" not in cc:
            cc["violation_types"] = {}
            changed = True
        vt = cc["violation_types"]
        for vtype, default_val in default_types.items():
            if vtype not in vt:
                vt[vtype] = default_val
                changed = True
            elif isinstance(vt[vtype], bool):
                vt[vtype] = {"enabled": vt[vtype], "description": default_val["description"]}
                changed = True
            elif isinstance(vt[vtype], dict):
                if "enabled" not in vt[vtype]:
                    vt[vtype]["enabled"] = True
                    changed = True
                if "description" not in vt[vtype]:
                    vt[vtype]["description"] = default_val["description"]
                    changed = True
        if changed:
            self._mark_dirty()
        self._content_check_init.add(gid)
        return cc

    def get_content_check_config(self, group_id: int) -> Dict[str, Any]:
        return self._ensure_content_check_config(group_id)

    def update_content_check_config(self, group_id: int, config: Dict[str, Any]) -> None:
        cc = self._ensure_content_check_config(group_id)
        for key, value in config.items():
            if value is not None:
                cc[key] = value
        self._mark_dirty()

    def batch_update_content_check_config(self, group_ids: List[int], config: Dict[str, Any]) -> None:
        for group_id in group_ids:
            self.update_content_check_config(group_id, config)

    def batch_update_ai_chat_group_config(self, group_ids: List[int], config: Dict[str, Any]) -> None:
        for group_id in group_ids:
            self.update_ai_chat_group_config(group_id, config)


config_manager = ConfigManager()
