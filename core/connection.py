import asyncio
import json
import logging
from typing import Optional, Any

import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from core.onebot.models import parse_event, LifecycleMetaEvent
from core.onebot.bot import Bot
from core.event_bus import dispatch
from core.lifecycle import get_driver

logger = logging.getLogger("connection")

# 全局 dispatch 并发限制 Semaphore(由 config dispatch.max_concurrent 控制)
_dispatch_semaphore: Optional[asyncio.Semaphore] = None
_dispatch_semaphore_size: int = 16


def _get_dispatch_semaphore() -> asyncio.Semaphore:
    """获取全局 dispatch Semaphore,根据 config 动态调整大小。"""
    global _dispatch_semaphore, _dispatch_semaphore_size
    try:
        from config_manager import config_manager
        desired = int(config_manager.get_dispatch_config().get("max_concurrent", 16))
    except Exception:
        desired = 16
    if desired < 1:
        desired = 1
    if _dispatch_semaphore is None or _dispatch_semaphore_size != desired:
        _dispatch_semaphore = asyncio.Semaphore(desired)
        _dispatch_semaphore_size = desired
    return _dispatch_semaphore


async def _dispatch_and_limit(bot: Any, event: Any) -> None:
    """用全局 Semaphore 限制并发 dispatch。"""
    sem = _get_dispatch_semaphore()
    async with sem:
        await dispatch(bot, event)


class WSClientManager:
    """正向 WebSocket 客户端管理器。
    
    Bot 作为客户端主动连接 OneBot 实现的 WebSocket 服务端。
    """
    
    def __init__(self, adapter_id: str = "default"):
        self._session: Optional[aiohttp.ClientSession] = None
        self._bot: Optional[Bot] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.adapter_id = adapter_id  # 适配器唯一标识,用于日志
    
    async def start(self, url: str, access_token: str = ""):
        """启动正向 WS 客户端连接循环。
        
        连接流程:
        1. 创建 aiohttp ClientSession
        2. 循环:
           a. 连接 ws_url,携带 Authorization header
           b. 等待 LifecycleMetaEvent (sub_type=connect),获取 self_id
           c. 创建 Bot 实例,触发 on_bot_connect
           d. 持续接收消息:
              - API 响应(echo 字段存在) → bot.handle_api_response(data)
              - 事件(post_type 字段存在) → parse_event + dispatch
           e. 连接断开时触发 on_bot_disconnect,等待 3 秒后重连
        """
        self._running = True
        self._session = aiohttp.ClientSession()
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        
        while self._running:
            try:
                async with self._session.ws_connect(url, headers=headers, heartbeat=30) as ws:
                    logger.info(f"WebSocket connected to {url}")
                    
                    bot = None
                    # 等待 LifecycleMetaEvent 获取 self_id
                    while self._running:
                        try:
                            msg = await ws.receive()
                        except asyncio.TimeoutError:
                            # read 超时不断连,继续等待
                            continue
                        except Exception as e:
                            logger.error(f"WS receive error: {e}")
                            break
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            
                            # API 响应
                            if "echo" in data and bot:
                                bot.handle_api_response(data)
                                continue
                            
                            # 事件
                            if "post_type" in data:
                                event = parse_event(data)
                                if event is None:
                                    continue
                                
                                # LifecycleMetaEvent — 创建 Bot
                                if isinstance(event, LifecycleMetaEvent):
                                    self_id = str(event.self_id)
                                    bot = Bot(ws, self_id, adapter_type="onebot_v11")
                                    self._bot = bot
                                    driver = get_driver()
                                    await driver.trigger_bot_connect(bot)
                                    logger.info(f"[适配器 {self.adapter_id}] Bot {self_id} connected")
                                    continue

                                # 日志: 收到事件
                                post_type = getattr(event, "post_type", "")
                                if post_type == "message":
                                    message_type = getattr(event, "message_type", "")
                                    group_id = getattr(event, "group_id", None)
                                    user_id = getattr(event, "user_id", None)
                                    content = ""
                                    try:
                                        content = event.get_plaintext()[:50]
                                    except Exception:
                                        content = str(getattr(event, "raw_message", ""))[:50]
                                    if message_type == "group":
                                        logger.info(f"[群消息] {group_id} | {user_id} | {content}")
                                    elif message_type == "private":
                                        logger.info(f"[私聊消息] {user_id} | {content}")
                                    else:
                                        logger.info(f"[消息] {user_id} | {content}")
                                elif post_type == "notice":
                                    logger.info(f"[通知] {getattr(event, 'notice_type', '')}")
                                elif post_type == "request":
                                    logger.info(f"[请求] {getattr(event, 'request_type', '')}")

                                # 普通事件 — 分发
                                if bot:
                                    asyncio.create_task(_dispatch_and_limit(bot, event))
                        
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                            logger.warning("WebSocket closed by server")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error: {ws.exception()}")
                            break
                    
                    # 连接断开
                    if bot:
                        driver = get_driver()
                        await driver.trigger_bot_disconnect(bot)
                        self._bot = None
                        
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
            
            if self._running:
                logger.info("Reconnecting in 3 seconds...")
                await asyncio.sleep(3.0)
    
    async def stop(self):
        """停止连接"""
        self._running = False
        if self._bot:
            driver = get_driver()
            await driver.trigger_bot_disconnect(self._bot)
            self._bot = None
        if self._session:
            await self._session.close()
            self._session = None
        if self._task:
            self._task.cancel()
            self._task = None


class WSServerManager:
    """反向 WebSocket 服务端管理器。
    
    OneBot 实现主动连接到 Bot 的 WebSocket 服务端。
    """
    
    def __init__(self):
        self._connections = {}  # self_id -> Bot
    
    def setup_routes(self, app: FastAPI, access_token: str = "", endpoint: str = "/onebot/v11/ws"):
        """在 FastAPI 应用上注册 WebSocket 端点。
        
        OneBot 实现会连接到 ws://host:port/onebot/v11/ws
        """
        
        @app.websocket(endpoint)
        async def ws_endpoint(websocket: WebSocket):
            # 鉴权
            if access_token:
                auth = websocket.headers.get("Authorization", "")
                if auth != f"Bearer {access_token}" and auth != access_token:
                    await websocket.close(code=4001)
                    return
            
            await websocket.accept()
            logger.info("WebSocket server: client connected")
            
            bot = None
            try:
                while True:
                    data = await websocket.receive_json()
                    
                    # API 响应
                    if "echo" in data and bot:
                        bot.handle_api_response(data)
                        continue
                    
                    # 事件
                    if "post_type" in data:
                        event = parse_event(data)
                        if event is None:
                            continue
                        
                        # LifecycleMetaEvent — 创建 Bot
                        if getattr(event, "post_type", None) == "meta_event" and getattr(event, "meta_event_type", None) == "lifecycle":
                            self_id = str(event.self_id)
                            bot = Bot(websocket, self_id, adapter_type="onebot_v11")
                            self._connections[self_id] = bot
                            driver = get_driver()
                            await driver.trigger_bot_connect(bot)
                            logger.info(f"Bot {self_id} connected (reverse WS)")
                            continue

                        # 日志: 收到事件
                        post_type = getattr(event, "post_type", "")
                        if post_type == "message":
                            message_type = getattr(event, "message_type", "")
                            group_id = getattr(event, "group_id", None)
                            user_id = getattr(event, "user_id", None)
                            content = ""
                            try:
                                content = event.get_plaintext()[:50]
                            except Exception:
                                content = str(getattr(event, "raw_message", ""))[:50]
                            if message_type == "group":
                                logger.info(f"[群消息] {group_id} | {user_id} | {content}")
                            elif message_type == "private":
                                logger.info(f"[私聊消息] {user_id} | {content}")
                            else:
                                logger.info(f"[消息] {user_id} | {content}")
                        elif post_type == "notice":
                            logger.info(f"[通知] {getattr(event, 'notice_type', '')}")
                        elif post_type == "request":
                            logger.info(f"[请求] {getattr(event, 'request_type', '')}")

                        # 普通事件
                        if bot:
                            asyncio.create_task(_dispatch_and_limit(bot, event))
            
            except WebSocketDisconnect:
                logger.info("WebSocket server: client disconnected")
            except Exception as e:
                logger.error(f"WebSocket server error: {e}")
            finally:
                if bot:
                    self._connections.pop(bot.self_id, None)
                    driver = get_driver()
                    await driver.trigger_bot_disconnect(bot)
    
    def get_bot(self) -> Optional[Bot]:
        """获取第一个连接的 Bot"""
        for bot in self._connections.values():
            return bot
        return None
    
    def get_bots(self) -> dict:
        return self._connections
