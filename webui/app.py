import sys
import os
import time
import aiohttp
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn
import json
import jwt
import subprocess
import sys
import threading
from datetime import datetime, timedelta

from config_manager import config_manager, AVAILABLE_FEATURES
from log_manager import log_manager
from core.menu_registry import menu_registry

_START_TIME = time.time()

app = FastAPI(title="陌城网络-qqbot WebUI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRONTEND_DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
_FRONTEND_INDEX_HTML = os.path.join(_FRONTEND_DIST_DIR, "index.html")


class MenuTitleUpdate(BaseModel):
    title: str


class MenuDescriptionUpdate(BaseModel):
    description: str


class MenuTriggerUpdate(BaseModel):
    trigger: str


class GroupSettingUpdate(BaseModel):
    enabled: Optional[bool] = None
    menu_enabled: Optional[bool] = None


class OneBotConfigUpdate(BaseModel):
    mode: Optional[str] = None
    ws_client: Optional[Dict[str, Any]] = None
    ws_server: Optional[Dict[str, Any]] = None
    http: Optional[Dict[str, Any]] = None


class ServerConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    webui_port: Optional[int] = None


class BotConfigUpdate(BaseModel):
    superusers: Optional[List[str]] = None
    nickname: Optional[str] = None


class AuthGroupCreate(BaseModel):
    name: str
    permissions: List[str]


class AuthGroupUpdate(BaseModel):
    permissions: List[str]


class AuthCodeCreate(BaseModel):
    expire_time: Optional[str] = None
    auth_group: str
    max_uses: int = 1


class AuthorizationEnabledUpdate(BaseModel):
    enabled: bool


class NotifyConfigUpdate(BaseModel):
    welcome_enabled: Optional[bool] = None
    welcome_text: Optional[str] = None
    join_private_enabled: Optional[bool] = None
    join_private_text: Optional[str] = None
    kick_enabled: Optional[bool] = None
    kick_text: Optional[str] = None
    admin_set_enabled: Optional[bool] = None
    admin_set_text: Optional[str] = None
    admin_unset_enabled: Optional[bool] = None
    admin_unset_text: Optional[str] = None
    leave_enabled: Optional[bool] = None
    leave_text: Optional[str] = None


class CheckinConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    send_like: Optional[bool] = None
    reward_min: Optional[int] = None
    reward_max: Optional[int] = None
    penalty_enabled: Optional[bool] = None
    penalty_deduction: Optional[int] = None
    low_points_block_enabled: Optional[bool] = None
    low_points_threshold: Optional[int] = None


class VerifyConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    timeout_kick: Optional[bool] = None
    timeout_minutes: Optional[int] = None
    welcome_prompt: Optional[str] = None
    success_prompt: Optional[str] = None
    timeout_prompt: Optional[str] = None


class NewcomerConfigUpdate(BaseModel):
    join_mode: Optional[str] = None
    reject_level_below: Optional[int] = None
    reject_nickname_contains: Optional[List[str]] = None
    reject_sign_contains: Optional[List[str]] = None
    mute_minutes: Optional[int] = None


class LoginRequest(BaseModel):
    token: str


class CustomApiCreate(BaseModel):
    name: str
    trigger: str
    url: str
    method: Optional[str] = "GET"
    response_type: Optional[str] = "text"
    json_path: Optional[str] = ""
    timeout: Optional[int] = 10
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = True


class CustomApiUpdate(BaseModel):
    trigger: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    response_type: Optional[str] = None
    json_path: Optional[str] = None
    timeout: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


class CustomApiEnabledUpdate(BaseModel):
    enabled: bool


class AccessTokenUpdate(BaseModel):
    access_token: str


class BroadcastRequest(BaseModel):
    message: str
    group_ids: List[str]


class AiProviderCreate(BaseModel):
    name: str
    api_base: str
    api_key: Optional[str] = ""
    default_model: Optional[str] = ""
    enabled: Optional[bool] = True
    api_format: Optional[str] = "openai"


class AiProviderUpdate(BaseModel):
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    enabled: Optional[bool] = None
    api_format: Optional[str] = None


class AiChatEnabledUpdate(BaseModel):
    enabled: bool


class AiChatGroupConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_context: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    proactive_reply: Optional[bool] = None
    proactive_reply_probability: Optional[float] = None


class ScheduleConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    mute: Optional[Dict[str, Any]] = None
    unmute: Optional[Dict[str, Any]] = None
    broadcasts: Optional[List[Dict[str, Any]]] = None
    hourly_chime: Optional[Dict[str, Any]] = None


class WebmasterConfigUpdate(BaseModel):
    enabled: Optional[bool] = None


class PointsConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    gifts: Optional[Dict[str, Any]] = None
    lottery: Optional[Dict[str, Any]] = None
    transfer: Optional[Dict[str, Any]] = None


class ContentCheckConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    violation_types: Optional[Dict[str, Any]] = None
    custom_prompt: Optional[str] = None
    warning_template: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_concurrent: Optional[int] = None


class ContentCheckBatchUpdate(BaseModel):
    group_ids: List[str]
    config: ContentCheckConfigUpdate


class AiChatBatchUpdate(BaseModel):
    group_ids: List[str]
    config: AiChatGroupConfigUpdate


class GroupLoginRequest(BaseModel):
    group_id: str
    token: str


class GroupWebuiTokenUpdate(BaseModel):
    token: Optional[str] = None
    auto_generate: Optional[bool] = False


class GroupPanelConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    menu_enabled: Optional[bool] = None
    notify: Optional[NotifyConfigUpdate] = None
    checkin: Optional[CheckinConfigUpdate] = None
    verify: Optional[VerifyConfigUpdate] = None
    newcomer: Optional[NewcomerConfigUpdate] = None
    ai_chat: Optional[AiChatGroupConfigUpdate] = None
    schedule: Optional[ScheduleConfigUpdate] = None
    webmaster: Optional[WebmasterConfigUpdate] = None
    points: Optional[PointsConfigUpdate] = None
    content_check: Optional[ContentCheckConfigUpdate] = None


class UserPointsUpdate(BaseModel):
    points: int
    operation: str = "set"


def _get_jwt_secret() -> str:
    return config_manager.get_webui_config().get("jwt_secret", "default-secret")


def _create_jwt_token() -> str:
    payload = {
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


async def get_current_token(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = auth_header[7:]
    try:
        jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="认证令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="认证令牌无效")


def _create_group_jwt(group_id: str) -> str:
    payload = {
        "exp": datetime.utcnow() + timedelta(hours=24),
        "group_id": group_id,
        "scope": "group"
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


async def get_group_admin(group_id: str, request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="认证令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="认证令牌无效")
    if payload.get("scope") != "group":
        raise HTTPException(status_code=403, detail="需要群管理员权限")
    if payload.get("group_id") != group_id:
        raise HTTPException(status_code=403, detail="无权访问该群的管理面板")
    return payload


@app.get("/", response_class=HTMLResponse)
async def index():
    if os.path.exists(_FRONTEND_INDEX_HTML):
        with open(_FRONTEND_INDEX_HTML, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebUI not built. Run <code>npm run build</code> in webui/frontend/</h1>", status_code=404)


@app.post("/api/auth/login")
async def login(data: LoginRequest):
    webui_config = config_manager.get_webui_config()
    if data.token != webui_config.get("access_token", ""):
        raise HTTPException(status_code=401, detail="访问令牌错误")
    token = _create_jwt_token()
    return {"success": True, "token": token}


@app.get("/api/auth/check")
async def check_auth(token: str = Depends(get_current_token)):
    return {"success": True, "message": "认证有效"}


@app.post("/api/auth/access-token")
async def update_access_token(data: AccessTokenUpdate, _=Depends(get_current_token)):
    config_manager.update_webui_access_token(data.access_token)
    return {"success": True, "message": "访问令牌已更新"}


@app.post("/api/group-login")
async def group_login(data: GroupLoginRequest):
    gid = str(data.group_id)
    gs = config_manager.config.get("group_settings", {}).get(gid, {})
    stored_token = gs.get("webui_token", "")
    if not stored_token:
        raise HTTPException(status_code=401, detail="该群未设置 WebUI 访问令牌")
    if not gs.get("webui_enabled", False):
        raise HTTPException(status_code=401, detail="该群的管理面板未启用")
    if data.token != stored_token:
        raise HTTPException(status_code=401, detail="群访问令牌错误")
    token = _create_group_jwt(gid)
    return {
        "success": True,
        "token": token,
        "group_id": gid,
        "group_name": config_manager.get_group_name(gid)
    }


@app.get("/api/config")
async def get_config(_=Depends(get_current_token)):
    return config_manager.config


@app.get("/api/menu")
async def get_menu(_=Depends(get_current_token)):
    # 返回菜单全局配置(开关与文案)与注册中心聚合的菜单树
    return {
        "config": config_manager.get_menu_config(),
        "tree": menu_registry.get_menu_tree(),
    }


@app.get("/api/menu/text")
async def get_menu_text(_=Depends(get_current_token)):
    cfg = config_manager.get_menu_config()
    return {"text": menu_registry.get_main_menu_text(global_title=cfg.get("title"), global_desc=cfg.get("description"))}


@app.get("/api/menu/category/{category}/text")
async def get_category_menu_text(category: str, _=Depends(get_current_token)):
    text = menu_registry.get_category_menu_text(category)
    if text is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    return {"text": text}


@app.post("/api/menu/title")
async def update_menu_title(data: MenuTitleUpdate, _=Depends(get_current_token)):
    # 菜单标题为全局文案覆盖,直接写 config 并标记脏数据
    config_manager.config.setdefault("menu", {})["title"] = data.title
    config_manager._mark_dirty()
    return {"success": True, "message": "菜单标题已更新"}


@app.post("/api/menu/description")
async def update_menu_description(data: MenuDescriptionUpdate, _=Depends(get_current_token)):
    # 菜单描述为全局文案覆盖,直接写 config 并标记脏数据
    config_manager.config.setdefault("menu", {})["description"] = data.description
    config_manager._mark_dirty()
    return {"success": True, "message": "菜单描述已更新"}


@app.post("/api/menu/trigger")
async def update_menu_trigger(data: MenuTriggerUpdate, _=Depends(get_current_token)):
    # 菜单触发词为全局文案覆盖,直接写 config 并标记脏数据
    config_manager.config.setdefault("menu", {})["trigger"] = data.trigger
    config_manager._mark_dirty()
    return {"success": True, "message": "菜单触发词已更新"}


@app.post("/api/menu/enabled")
async def set_menu_enabled(enabled: bool, _=Depends(get_current_token)):
    config_manager.set_menu_global_enabled(enabled)
    return {"success": True, "message": f"菜单功能已{'开启' if enabled else '关闭'}"}


@app.get("/api/categories")
async def get_categories(_=Depends(get_current_token)):
    # 从 menu_registry 读取分类列表(只读)
    tree = menu_registry.get_menu_tree()
    result = []
    for name, data in tree.items():
        item_count = len(data.get("items", {}))
        # 含子分类时累加子分类下的菜单项数
        for sub_data in data.get("subcategories", {}).values():
            item_count += len(sub_data.get("items", {}))
        result.append({
            "name": name,
            "title": data.get("title", name),
            "trigger": data.get("trigger", name),
            "description": data.get("description", ""),
            "enabled": data.get("enabled", True),
            "item_count": item_count
        })
    return result


@app.get("/api/categories/{category}")
async def get_category(category: str, _=Depends(get_current_token)):
    # 从 menu_registry 读取分类详情(只读)
    tree = menu_registry.get_menu_tree()
    category_data = tree.get(category)
    if not category_data:
        raise HTTPException(status_code=404, detail="分类不存在")
    return {
        "name": category,
        "title": category_data.get("title", category),
        "trigger": category_data.get("trigger", category),
        "description": category_data.get("description", ""),
        "enabled": category_data.get("enabled", True),
        "subcategories": category_data.get("subcategories", {}),
        "items": category_data.get("items", {})
    }


@app.get("/api/categories/{category}/items")
async def get_category_items(category: str, _=Depends(get_current_token)):
    # 从 menu_registry 读取分类下所有菜单项(只读,含子分类)
    tree = menu_registry.get_menu_tree()
    category_data = tree.get(category)
    if not category_data:
        raise HTTPException(status_code=404, detail="分类不存在")

    result = []
    # 一级分类直属菜单项
    for name, data in category_data.get("items", {}).items():
        result.append({
            "name": name,
            "text": data.get("text", name),
            "description": data.get("description", ""),
            "enabled": data.get("enabled", True),
            "subcategory": None
        })
    # 子分类下的菜单项
    for sub_name, sub_data in category_data.get("subcategories", {}).items():
        for name, data in sub_data.get("items", {}).items():
            result.append({
                "name": name,
                "text": data.get("text", name),
                "description": data.get("description", ""),
                "enabled": data.get("enabled", True),
                "subcategory": sub_name
            })
    return result


async def _auto_sync_groups():
    """静默自动同步群列表:调 OneBot get_group_list,失败不抛。
    用于在返回群列表前确保数据最新,失败则降级用本地数据。
    """
    try:
        from core import get_bots
        bots = get_bots()
        if not bots:
            return
        bot = list(bots.values())[0]
        groups = await bot.get_group_list()
        config_manager.sync_group_list(groups)
    except Exception:
        # 静默失败,降级返回本地数据
        pass


@app.get("/api/groups")
async def get_groups(_=Depends(get_current_token)):
    await _auto_sync_groups()
    group_settings = config_manager.config.get("group_settings", {})
    result = {}
    for gid, settings in group_settings.items():
        entry = dict(settings) if isinstance(settings, dict) else settings
        name = config_manager.get_group_name(gid)
        if name:
            result[gid] = {**entry, "group_name": name}
        else:
            result[gid] = entry
    return result


@app.post("/api/groups/sync")
async def sync_groups(_=Depends(get_current_token)):
    try:
        from core import get_bots
        bots = get_bots()
        if not bots:
            raise HTTPException(status_code=503, detail="Bot 未连接，无法同步群列表")
        bot = list(bots.values())[0]
        groups = await bot.get_group_list()
        added, removed = config_manager.sync_group_list(groups)
        group_settings = config_manager.config.get("group_settings", {})
        result = {}
        for gid, settings in group_settings.items():
            entry = dict(settings) if isinstance(settings, dict) else settings
            name = config_manager.get_group_name(gid)
            if name:
                result[gid] = {**entry, "group_name": name}
            else:
                result[gid] = entry
        return {"success": True, "added": added, "removed": removed, "total": len(result), "groups": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步群列表失败: {str(e)}")


@app.get("/api/groups/{group_id}")
async def get_group(group_id: str, _=Depends(get_current_token)):
    return config_manager.config.get("group_settings", {}).get(group_id, {})


@app.post("/api/groups/{group_id}")
async def update_group(group_id: str, data: GroupSettingUpdate, _=Depends(get_current_token)):
    if data.enabled is not None:
        config_manager.set_group_enabled(int(group_id), data.enabled)
    if data.menu_enabled is not None:
        config_manager.set_menu_enabled(int(group_id), data.menu_enabled)
    return {"success": True, "message": "群设置已更新"}


@app.get("/api/groups/{group_id}/notify")
async def get_notify_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_notify_config(int(group_id))


@app.post("/api/groups/{group_id}/notify")
async def update_notify_config(group_id: str, data: NotifyConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_notify_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "提示系统配置已更新"}


@app.get("/api/groups/{group_id}/checkin")
async def get_checkin_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_checkin_config(int(group_id))


@app.post("/api/groups/{group_id}/checkin")
async def update_checkin_config(group_id: str, data: CheckinConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_checkin_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "签到系统配置已更新"}


@app.get("/api/groups/{group_id}/verify")
async def get_verify_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_verify_config(int(group_id))


@app.post("/api/groups/{group_id}/verify")
async def update_verify_config(group_id: str, data: VerifyConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_verify_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "验证系统配置已更新"}


@app.get("/api/groups/{group_id}/newcomer")
async def get_newcomer_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_newcomer_config(int(group_id))


@app.post("/api/groups/{group_id}/newcomer")
async def update_newcomer_config(group_id: str, data: NewcomerConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_newcomer_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "新人系统配置已更新"}


# === 群 WebUI Token 管理（全局管理员） ===

@app.get("/api/groups/{group_id}/webui-token")
async def get_group_webui_token(group_id: str, _=Depends(get_current_token)):
    info = config_manager.get_group_webui_token(int(group_id))
    return {
        "has_token": bool(info["token"]),
        "enabled": info["enabled"],
        "group_name": config_manager.get_group_name(group_id),
    }


@app.post("/api/groups/{group_id}/webui-token")
async def set_group_webui_token(group_id: str, data: GroupWebuiTokenUpdate, _=Depends(get_current_token)):
    if data.auto_generate:
        token = config_manager.generate_group_webui_token(int(group_id))
    elif data.token:
        config_manager.set_group_webui_token(int(group_id), data.token)
        token = data.token
    else:
        raise HTTPException(status_code=400, detail="请提供 token 或设置 auto_generate=true")
    config_manager.set_group_webui_enabled(int(group_id), True)
    return {"success": True, "token": token, "message": "群 WebUI 访问令牌已设置"}


@app.delete("/api/groups/{group_id}/webui-token")
async def delete_group_webui_token(group_id: str, _=Depends(get_current_token)):
    config_manager.delete_group_webui_token(int(group_id))
    return {"success": True, "message": "群 WebUI 访问令牌已清除"}


@app.get("/api/onebot")
async def get_onebot_config(_=Depends(get_current_token)):
    return config_manager.get_onebot_config()


@app.post("/api/onebot")
async def update_onebot_config(data: OneBotConfigUpdate, _=Depends(get_current_token)):
    current = config_manager.get_onebot_config()
    if data.mode is not None:
        current["mode"] = data.mode
    if data.ws_client is not None:
        current["ws_client"] = data.ws_client
    if data.ws_server is not None:
        current["ws_server"] = data.ws_server
    if data.http is not None:
        current["http"] = data.http
    config_manager.update_onebot_config(current)
    return {"success": True, "message": "OneBot配置已更新"}


@app.post("/api/onebot/mode")
async def update_onebot_mode(mode: str, _=Depends(get_current_token)):
    config_manager.update_onebot_mode(mode)
    return {"success": True, "message": f"连接模式已切换为 {mode}"}


@app.get("/api/server")
async def get_server_config(_=Depends(get_current_token)):
    return config_manager.get_server_config()


@app.post("/api/server")
async def update_server_config(data: ServerConfigUpdate, _=Depends(get_current_token)):
    current = config_manager.get_server_config()
    if data.host is not None:
        current["host"] = data.host
    if data.port is not None:
        current["port"] = data.port
    if data.webui_port is not None:
        current["webui_port"] = data.webui_port
    config_manager.update_server_config(current)
    return {"success": True, "message": "服务器配置已更新"}


@app.get("/api/dispatch")
async def get_dispatch_config(_=Depends(get_current_token)):
    return config_manager.get_dispatch_config()


class DispatchConfigUpdate(BaseModel):
    max_concurrent: Optional[int] = None


@app.post("/api/dispatch")
async def update_dispatch_config(data: DispatchConfigUpdate, _=Depends(get_current_token)):
    if data.max_concurrent is not None and (data.max_concurrent < 1 or data.max_concurrent > 512):
        raise HTTPException(status_code=400, detail="max_concurrent 范围: 1~512")
    config_manager.update_dispatch_config({"max_concurrent": data.max_concurrent})
    return {"ok": True, "dispatch": config_manager.get_dispatch_config()}


@app.get("/api/bot")
async def get_bot_config(_=Depends(get_current_token)):
    return config_manager.get_bot_config()


@app.post("/api/bot")
async def update_bot_config(data: BotConfigUpdate, _=Depends(get_current_token)):
    current = config_manager.get_bot_config()
    if data.superusers is not None:
        current["superusers"] = data.superusers
    if data.nickname is not None:
        current["nickname"] = data.nickname
    config_manager.update_bot_config(current)
    return {"success": True, "message": "机器人配置已更新"}


@app.post("/api/config/save")
async def save_config(_=Depends(get_current_token)):
    config_manager.save()
    return {"success": True, "message": "配置已保存"}


@app.post("/api/config/reload")
async def reload_config(_=Depends(get_current_token)):
    config_manager.load()
    return {"success": True, "message": "配置已重新加载"}


@app.get("/api/version/check")
async def check_version(_=Depends(get_current_token)):
    """检测是否有新版本"""
    from core.updater import check_update
    result = await check_update()
    return result


@app.get("/api/version/info")
async def get_version_info(_=Depends(get_current_token)):
    """获取当前版本号和最新版本详情"""
    from core.version import __version__
    from core.updater import check_update
    result = await check_update()
    return {
        "current": __version__,
        "has_update": result.get("has_update", False),
        "latest": result.get("latest"),
        "error": result.get("error")
    }


@app.post("/api/version/update")
async def trigger_update(_=Depends(get_current_token)):
    """触发后台更新任务"""
    from core.updater import get_update_status, _set_status, check_update_sync, download_update, perform_update, trigger_restart, BASE_DIR
    import threading, tempfile, os

    status = get_update_status()
    if status["status"] not in ("idle", "error", "done"):
        raise HTTPException(status_code=409, detail="已有更新任务正在进行中")

    def _do_update():
        try:
            _set_status("checking", 5, "正在检测新版本...")
            result = check_update_sync()
            if not result.get("has_update"):
                _set_status("done", 100, "当前已是最新版本")
                return
            latest = result.get("latest") or {}
            download_url = latest.get("download_url")
            if not download_url:
                _set_status("error", 0, "未获取到下载链接")
                return

            _set_status("downloading", 10, f"正在下载 {latest.get('version_name', '')}...")
            temp_zip = os.path.join(tempfile.gettempdir(), f"qqbot_update_{int(time.time())}.zip")

            def progress_cb(downloaded, total):
                if total > 0:
                    pct = 10 + int(downloaded / total * 50)
                    _set_status("downloading", pct, f"下载中: {downloaded//1024}KB / {total//1024}KB")

            download_update(download_url, temp_zip, progress_cb)

            _set_status("extracting", 65, "正在解压...")
            _set_status("backup", 75, "正在备份当前版本...")
            _set_status("overwriting", 85, "正在覆盖文件...")

            success = perform_update(temp_zip, BASE_DIR)

            if success:
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
                _set_status("restarting", 95, "更新完成,正在重启框架...")
                import time as _time
                _time.sleep(2)
                trigger_restart()
            else:
                _set_status("error", 0, "更新失败,已回滚到旧版本")
        except Exception as e:
            _set_status("error", 0, f"更新失败: {type(e).__name__}: {e}")

    thread = threading.Thread(target=_do_update, daemon=True)
    thread.start()
    return {"started": True, "message": "更新任务已启动"}


@app.get("/api/version/update-status")
async def get_update_progress(_=Depends(get_current_token)):
    """查询更新进度"""
    from core.updater import get_update_status
    return get_update_status()


@app.get("/api/status")
async def get_status(_=Depends(get_current_token)):
    from core import get_bots

    bots = get_bots()
    online = len(bots) > 0
    bot_info: Dict[str, Any] = {}

    if online:
        bot = list(bots.values())[0]
        bot_info["self_id"] = str(bot.self_id)
        bot_info["nickname"] = ""
        bot_info["avatar"] = f"https://q1.qlogo.cn/g?b=qq&nk={bot.self_id}&s=640"

        # Try to get login info for nickname
        try:
            login_info = await bot.get_login_info()
            bot_info["nickname"] = login_info.get("nickname", "")
        except Exception:
            pass

        # 静默自动同步群列表,失败降级用本地数据
        await _auto_sync_groups()
        bot_info["group_count"] = len(config_manager.config.get("group_settings", {}))
    else:
        bot_config = config_manager.get_bot_config()
        bot_info["self_id"] = ""
        bot_info["nickname"] = bot_config.get("nickname", "")
        bot_info["avatar"] = ""
        bot_info["group_count"] = len(config_manager.config.get("group_settings", {}))

    # Uptime
    uptime_seconds = int(time.time() - _START_TIME)

    # Message stats from log_manager
    stats = log_manager.get_stats()

    return {
        "online": online,
        "self_id": bot_info.get("self_id", ""),
        "nickname": bot_info.get("nickname", ""),
        "avatar": bot_info.get("avatar", ""),
        "group_count": bot_info.get("group_count", 0),
        "uptime": uptime_seconds,
        "messages_sent": stats.get("sent", 0),
        "messages_received": stats.get("received", 0),
    }


@app.get("/api/logs")
async def get_logs(
    log_type: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _=Depends(get_current_token)
):
    logs = log_manager.get_logs(
        log_type=log_type,
        direction=direction,
        limit=min(limit, 500),
        offset=offset
    )
    return {"logs": logs, "total": len(logs)}


@app.get("/api/logs/stats")
async def get_log_stats(_=Depends(get_current_token)):
    return log_manager.get_stats()


@app.post("/api/logs/clear")
async def clear_logs(_=Depends(get_current_token)):
    log_manager.clear_logs()
    return {"success": True, "message": "日志已清空"}


@app.get("/api/authorization")
async def get_authorization(_=Depends(get_current_token)):
    return config_manager.config.get("authorization", {
        "enabled": False, "groups": {}, "codes": {}, "authorizations": {}
    })


@app.post("/api/authorization/enabled")
async def set_authorization_enabled(data: AuthorizationEnabledUpdate, _=Depends(get_current_token)):
    config_manager.set_authorization_enabled(data.enabled)
    return {"success": True, "message": f"授权系统已{'开启' if data.enabled else '关闭'}"}


@app.get("/api/authorization/features")
async def get_authorization_features(_=Depends(get_current_token)):
    return {"features": AVAILABLE_FEATURES}


@app.get("/api/authorization/groups")
async def get_auth_groups(_=Depends(get_current_token)):
    groups = config_manager.get_auth_groups()
    result = []
    for name, data in groups.items():
        result.append({
            "name": name,
            "permissions": data.get("permissions", [])
        })
    return result


@app.post("/api/authorization/groups")
async def create_auth_group(data: AuthGroupCreate, _=Depends(get_current_token)):
    config_manager.add_auth_group(data.name, data.permissions)
    return {"success": True, "message": "授权分组已创建"}


@app.post("/api/authorization/groups/{name}")
async def update_auth_group(name: str, data: AuthGroupUpdate, _=Depends(get_current_token)):
    config_manager.update_auth_group(name, data.permissions)
    return {"success": True, "message": "授权分组已更新"}


@app.delete("/api/authorization/groups/{name}")
async def delete_auth_group(name: str, _=Depends(get_current_token)):
    if config_manager.delete_auth_group(name):
        return {"success": True, "message": "授权分组已删除"}
    raise HTTPException(status_code=404, detail="授权分组不存在")


@app.get("/api/authorization/codes")
async def get_auth_codes(_=Depends(get_current_token)):
    codes = config_manager.get_auth_codes()
    result = []
    for code, data in codes.items():
        result.append({
            "code": code,
            "expire_time": data.get("expire_time"),
            "auth_group": data.get("auth_group", ""),
            "max_uses": data.get("max_uses", 1),
            "use_count": data.get("use_count", 0),
            "used_by": data.get("used_by", [])
        })
    return result


@app.post("/api/authorization/codes")
async def create_auth_code(data: AuthCodeCreate, _=Depends(get_current_token)):
    code = config_manager.create_auth_code(
        expire_time=data.expire_time,
        auth_group=data.auth_group,
        max_uses=data.max_uses
    )
    return {"success": True, "message": "授权码已创建", "code": code}


@app.delete("/api/authorization/codes/{code}")
async def delete_auth_code(code: str, _=Depends(get_current_token)):
    if config_manager.delete_auth_code(code):
        return {"success": True, "message": "授权码已删除"}
    raise HTTPException(status_code=404, detail="授权码不存在")


@app.get("/api/authorization/authorizations")
async def get_authorizations(_=Depends(get_current_token)):
    authorizations = config_manager.get_authorizations()
    result = []
    for gid, data in authorizations.items():
        result.append({
            "group_id": gid,
            "expire_time": data.get("expire_time"),
            "auth_group": data.get("auth_group", ""),
            "activate_time": data.get("activate_time", ""),
            "code": data.get("code", "")
        })
    return result


@app.delete("/api/authorization/authorizations/{group_id}")
async def remove_authorization(group_id: str, _=Depends(get_current_token)):
    if config_manager.remove_group_authorization(int(group_id)):
        return {"success": True, "message": "群授权已移除"}
    raise HTTPException(status_code=404, detail="群授权不存在")


@app.get("/api/custom-api")
async def get_custom_api(_=Depends(get_current_token)):
    return config_manager.get_custom_api_config()


@app.post("/api/custom-api/enabled")
async def set_custom_api_enabled(data: CustomApiEnabledUpdate, _=Depends(get_current_token)):
    config_manager.set_custom_api_enabled(data.enabled)
    return {"success": True, "message": f"自定义API已{'开启' if data.enabled else '关闭'}"}


@app.get("/api/custom-api/apis")
async def get_custom_apis(_=Depends(get_current_token)):
    apis = config_manager.get_custom_apis()
    result = []
    for name, data in apis.items():
        result.append({
            "name": name,
            "trigger": data.get("trigger", ""),
            "url": data.get("url", ""),
            "method": data.get("method", "GET"),
            "response_type": data.get("response_type", "text"),
            "json_path": data.get("json_path", ""),
            "timeout": data.get("timeout", 10),
            "headers": data.get("headers", {}),
            "enabled": data.get("enabled", True)
        })
    return result


@app.post("/api/custom-api/apis")
async def create_custom_api(data: CustomApiCreate, _=Depends(get_current_token)):
    config_manager.add_custom_api(
        name=data.name,
        trigger=data.trigger,
        url=data.url,
        method=data.method or "GET",
        response_type=data.response_type or "text",
        json_path=data.json_path or "",
        timeout=data.timeout or 10,
        headers=data.headers or {},
        enabled=data.enabled if data.enabled is not None else True
    )
    return {"success": True, "message": "自定义API已添加"}


@app.post("/api/custom-api/apis/{name}")
async def update_custom_api(name: str, data: CustomApiUpdate, _=Depends(get_current_token)):
    update_data = data.model_dump(exclude_none=True)
    if not config_manager.update_custom_api(name, **update_data):
        raise HTTPException(status_code=404, detail="API不存在")
    return {"success": True, "message": "自定义API已更新"}


@app.delete("/api/custom-api/apis/{name}")
async def delete_custom_api(name: str, _=Depends(get_current_token)):
    if config_manager.delete_custom_api(name):
        return {"success": True, "message": "自定义API已删除"}
    raise HTTPException(status_code=404, detail="API不存在")


def _do_restart():
    threading.Event().wait(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


@app.post("/api/system/restart")
async def restart_system(_=Depends(get_current_token)):
    threading.Thread(target=_do_restart, daemon=True).start()
    return {"success": True, "message": "框架正在重启..."}


@app.post("/api/broadcast")
async def broadcast_message(data: BroadcastRequest, _=Depends(get_current_token)):
    try:
        from core import get_bots
        from core.onebot import Message

        bots = get_bots()
        if not bots:
            raise HTTPException(status_code=503, detail="Bot 未连接，无法发送群发消息")
        bot = list(bots.values())[0]

        results = {"success": [], "failed": []}
        for gid in data.group_ids:
            try:
                await bot.send_group_msg(
                    group_id=int(gid),
                    message=Message(data.message)
                )
                results["success"].append(gid)
            except Exception as e:
                results["failed"].append({"group_id": gid, "error": str(e)})

        return {
            "success": True,
            "total": len(data.group_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"群发消息失败: {str(e)}")


# === AI聊天 API ===

@app.get("/api/ai-chat")
async def get_ai_chat_config(_=Depends(get_current_token)):
    return config_manager.get_ai_chat_config()


@app.post("/api/ai-chat/enabled")
async def set_ai_chat_enabled(data: AiChatEnabledUpdate, _=Depends(get_current_token)):
    config_manager.set_ai_chat_enabled(data.enabled)
    return {"success": True, "message": f"AI聊天已{'开启' if data.enabled else '关闭'}"}


@app.get("/api/ai-chat/providers")
async def get_ai_providers(_=Depends(get_current_token)):
    providers = config_manager.get_ai_providers()
    result = []
    for name, data in providers.items():
        result.append({
            "name": name,
            "api_base": data.get("api_base", ""),
            "api_key": data.get("api_key", ""),
            "default_model": data.get("default_model", ""),
            "enabled": data.get("enabled", True),
            "api_format": data.get("api_format", "openai")
        })
    return result


@app.post("/api/ai-chat/providers")
async def create_ai_provider(data: AiProviderCreate, _=Depends(get_current_token)):
    config_manager.add_ai_provider(
        name=data.name,
        api_base=data.api_base,
        api_key=data.api_key or "",
        default_model=data.default_model or "",
        enabled=data.enabled if data.enabled is not None else True,
        api_format=data.api_format or "openai"
    )
    return {"success": True, "message": "AI供应商已添加"}


@app.post("/api/ai-chat/providers/{name}")
async def update_ai_provider(name: str, data: AiProviderUpdate, _=Depends(get_current_token)):
    update_data = data.model_dump(exclude_none=True)
    if not config_manager.update_ai_provider(name, **update_data):
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"success": True, "message": "AI供应商已更新"}


@app.delete("/api/ai-chat/providers/{name}")
async def delete_ai_provider(name: str, _=Depends(get_current_token)):
    if config_manager.delete_ai_provider(name):
        return {"success": True, "message": "AI供应商已删除"}
    raise HTTPException(status_code=404, detail="供应商不存在")


@app.post("/api/ai-chat/providers/{name}/models")
async def fetch_provider_models(name: str, _=Depends(get_current_token)):
    providers = config_manager.get_ai_providers()
    if name not in providers:
        raise HTTPException(status_code=404, detail="供应商不存在")
    provider = providers[name]
    api_base = provider.get("api_base", "")
    api_key = provider.get("api_key", "")
    api_format = provider.get("api_format", "openai")

    if not api_base:
        raise HTTPException(status_code=400, detail="供应商配置不完整")

    try:
        if api_format == "ollama":
            url = f"{api_base.rstrip('/')}/api/tags"
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{api_base.rstrip('/')}/models"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise HTTPException(status_code=502, detail=f"获取模型列表失败({resp.status}): {body[:200]}")
                data = await resp.json()
                if api_format == "ollama":
                    models = sorted([m["name"] for m in data.get("models", [])])
                else:
                    models = sorted([m["id"] for m in data.get("data", [])])
                return {"models": models}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@app.get("/api/groups/{group_id}/ai-chat")
async def get_ai_chat_group_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_ai_chat_group_config(int(group_id))


@app.post("/api/groups/{group_id}/ai-chat")
async def update_ai_chat_group_config(group_id: str, data: AiChatGroupConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_ai_chat_group_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "群AI聊天配置已更新"}


@app.post("/api/ai-chat/batch")
async def batch_update_ai_chat(data: AiChatBatchUpdate, _=Depends(get_current_token)):
    group_ids = [int(gid) for gid in data.group_ids]
    config = data.config.model_dump(exclude_none=True)
    config_manager.batch_update_ai_chat_group_config(group_ids, config)
    return {"success": True, "message": f"已批量更新 {len(group_ids)} 个群的AI聊天配置"}


@app.get("/api/groups/{group_id}/content-check")
async def get_content_check_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_content_check_config(int(group_id))


@app.post("/api/groups/{group_id}/content-check")
async def update_content_check_config(group_id: str, data: ContentCheckConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_content_check_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "群违规检测配置已更新"}


@app.post("/api/content-check/batch")
async def batch_update_content_check(data: ContentCheckBatchUpdate, _=Depends(get_current_token)):
    group_ids = [int(gid) for gid in data.group_ids]
    config = data.config.model_dump(exclude_none=True)
    config_manager.batch_update_content_check_config(group_ids, config)
    return {"success": True, "message": f"已批量更新 {len(group_ids)} 个群的违规检测配置"}


@app.get("/api/groups/{group_id}/schedule")
async def get_schedule_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_schedule_config(int(group_id))


@app.post("/api/groups/{group_id}/schedule")
async def update_schedule_config(group_id: str, data: ScheduleConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_schedule_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "定时功能配置已更新"}


@app.get("/api/groups/{group_id}/webmaster")
async def get_webmaster_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_webmaster_config(int(group_id))


@app.post("/api/groups/{group_id}/webmaster")
async def update_webmaster_config(group_id: str, data: WebmasterConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_webmaster_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "站长工具配置已更新"}


@app.get("/api/groups/{group_id}/points")
async def get_points_config(group_id: str, _=Depends(get_current_token)):
    return config_manager.get_points_config(int(group_id))


@app.post("/api/groups/{group_id}/points")
async def update_points_config(group_id: str, data: PointsConfigUpdate, _=Depends(get_current_token)):
    config_manager.update_points_config(int(group_id), data.model_dump(exclude_none=True))
    return {"success": True, "message": "积分系统配置已更新"}


# === 群管理面板 API（群级 JWT） ===

@app.get("/api/group-panel/{group_id}")
async def get_group_panel_config(group_id: str, _=Depends(get_group_admin)):
    gid = int(group_id)
    config = config_manager.config.get("group_settings", {}).get(group_id, {})
    if config is None:
        raise HTTPException(status_code=404, detail="群不存在")
    panel_data = {
        "group_id": group_id,
        "group_name": config_manager.get_group_name(gid),
        "enabled": config.get("enabled", True),
        "menu_enabled": config.get("menu_enabled", True),
        "notify": config_manager.get_notify_config(gid),
        "checkin": config_manager.get_checkin_config(gid),
        "verify": config_manager.get_verify_config(gid),
        "newcomer": config_manager.get_newcomer_config(gid),
        "ai_chat": config_manager.get_ai_chat_group_config(gid),
        "schedule": config_manager.get_schedule_config(gid),
        "webmaster": config_manager.get_webmaster_config(gid),
        "points": config_manager.get_points_config(gid),
        "content_check": config_manager.get_content_check_config(gid),
    }
    try:
        from plugins.group_stats import stats_data
        from datetime import date, timedelta
        today = date.today()
        start = today - timedelta(days=7)
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(None, stats_data.get_group_stats, gid, start, today)
        top_members = []
        if stats.get("user_counts"):
            sorted_users = sorted(stats["user_counts"].items(), key=lambda x: -x[1])[:10]
            for uid, count in sorted_users:
                try:
                    from core import get_bots
                    bots = get_bots()
                    if bots:
                        bot = list(bots.values())[0]
                        info = await bot.get_group_member_info(group_id=gid, user_id=int(uid))
                        nickname = info.get("card") or info.get("nickname", uid)
                    else:
                        nickname = uid
                except Exception:
                    nickname = uid
                top_members.append({"user_id": uid, "nickname": nickname, "count": count})
        panel_data["stats"] = {
            "total_messages_7d": stats["total_messages"],
            "active_users_7d": stats["active_users"],
            "top_members": top_members,
        }
    except Exception:
        panel_data["stats"] = {"total_messages_7d": 0, "active_users_7d": 0, "top_members": []}
    return panel_data


@app.post("/api/group-panel/{group_id}/config")
async def update_group_panel_config(group_id: str, data: GroupPanelConfigUpdate, _=Depends(get_group_admin)):
    gid = int(group_id)
    if data.enabled is not None:
        config_manager.set_group_enabled(gid, data.enabled)
    if data.menu_enabled is not None:
        config_manager.set_menu_enabled(gid, data.menu_enabled)
    if data.notify:
        config_manager.update_notify_config(gid, data.notify.model_dump(exclude_none=True))
    if data.checkin:
        config_manager.update_checkin_config(gid, data.checkin.model_dump(exclude_none=True))
    if data.verify:
        config_manager.update_verify_config(gid, data.verify.model_dump(exclude_none=True))
    if data.newcomer:
        config_manager.update_newcomer_config(gid, data.newcomer.model_dump(exclude_none=True))
    if data.ai_chat:
        config_manager.update_ai_chat_group_config(gid, data.ai_chat.model_dump(exclude_none=True))
    if data.schedule:
        config_manager.update_schedule_config(gid, data.schedule.model_dump(exclude_none=True))
    if data.webmaster:
        config_manager.update_webmaster_config(gid, data.webmaster.model_dump(exclude_none=True))
    if data.points:
        config_manager.update_points_config(gid, data.points.model_dump(exclude_none=True))
    if data.content_check:
        config_manager.update_content_check_config(gid, data.content_check.model_dump(exclude_none=True))
    return {"success": True, "message": "群配置已更新"}


@app.get("/api/groups/{group_id}/points/users")
async def get_group_users_points(group_id: str, _=Depends(get_current_token)):
    from plugins.group_checkin import checkin_data
    users = checkin_data.data.get(str(group_id), {})
    user_list = []
    for uid, udata in users.items():
        entry = {"user_id": uid, **udata}
        try:
            from core import get_bots
            bots = get_bots()
            if bots:
                bot = list(bots.values())[0]
                info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(uid))
                entry["nickname"] = info.get("card") or info.get("nickname", uid)
            else:
                entry["nickname"] = uid
        except Exception:
            entry["nickname"] = uid
        user_list.append(entry)
    user_list.sort(key=lambda x: -x.get("points", 0))
    return user_list


@app.post("/api/groups/{group_id}/points/users/{user_id}")
async def update_group_user_points(group_id: str, user_id: str, data: UserPointsUpdate, _=Depends(get_current_token)):
    from plugins.group_checkin import checkin_data
    gid_str = str(group_id)
    user_data = checkin_data.get_user_data(int(group_id), int(user_id))
    if data.operation == "set":
        user_data["points"] = data.points
    elif data.operation == "add":
        user_data["points"] = user_data.get("points", 0) + data.points
    elif data.operation == "subtract":
        user_data["points"] = max(0, user_data.get("points", 0) - data.points)
    else:
        raise HTTPException(status_code=400, detail="无效的 operation，支持 set/add/subtract")
    checkin_data.update_user_data(gid_str, user_id, user_data)
    return {"success": True, "points": user_data["points"]}


@app.get("/api/group-panel/{group_id}/points/users")
async def get_group_panel_users_points(group_id: str, _=Depends(get_group_admin)):
    from plugins.group_checkin import checkin_data
    users = checkin_data.data.get(str(group_id), {})
    user_list = []
    for uid, udata in users.items():
        entry = {"user_id": uid, **udata}
        try:
            from core import get_bots
            bots = get_bots()
            if bots:
                bot = list(bots.values())[0]
                info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(uid))
                entry["nickname"] = info.get("card") or info.get("nickname", uid)
            else:
                entry["nickname"] = uid
        except Exception:
            entry["nickname"] = uid
        user_list.append(entry)
    user_list.sort(key=lambda x: -x.get("points", 0))
    return user_list


@app.post("/api/group-panel/{group_id}/points/users/{user_id}")
async def update_group_panel_user_points(group_id: str, user_id: str, data: UserPointsUpdate, _=Depends(get_group_admin)):
    from plugins.group_checkin import checkin_data
    gid_str = str(group_id)
    user_data = checkin_data.get_user_data(int(group_id), int(user_id))
    if data.operation == "set":
        user_data["points"] = data.points
    elif data.operation == "add":
        user_data["points"] = user_data.get("points", 0) + data.points
    elif data.operation == "subtract":
        user_data["points"] = max(0, user_data.get("points", 0) - data.points)
    else:
        raise HTTPException(status_code=400, detail="无效的 operation，支持 set/add/subtract")
    checkin_data.update_user_data(gid_str, user_id, user_data)
    return {"success": True, "points": user_data["points"]}


# SPA catch-all: return index.html for any non-API GET route (must be after all API routes)
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_catchall(path: str):
    file_path = os.path.join(_FRONTEND_DIST_DIR, path)
    if os.path.isfile(file_path):
        from fastapi.responses import FileResponse
        return FileResponse(file_path)
    if os.path.exists(_FRONTEND_INDEX_HTML):
        with open(_FRONTEND_INDEX_HTML, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebUI not built. Run <code>npm run build</code> in webui/frontend/</h1>", status_code=404)


# Serve React static assets (must be mounted after all routes)
if os.path.isdir(_FRONTEND_DIST_DIR):
    _assets_dir = os.path.join(_FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


def run_webui(host: str = "0.0.0.0", port: int = 8081):
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_webui()
