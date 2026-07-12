"""QQ 官方机器人适配器:串联 client + ws + bot。"""
import asyncio
import logging
from typing import Any, Optional

from core.adapters.base import Adapter
from core.adapters.qq_official.client import QQOfficialClient
from core.adapters.qq_official.ws import QQOfficialWS
from core.adapters.qq_official.bot import QQOfficialBot
from core.adapters.qq_official.models import convert_event

logger = logging.getLogger("qq_official_adapter")


class QQOfficialAdapter(Adapter):
    """QQ 官方机器人适配器。
    
    config 字段:
      - app_id: 机器人 AppID
      - app_secret: 机器人 AppSecret
      - token: 机器人 Token(WebSocket 鉴权用,可选)
    """
    
    adapter_type = "qq_official"
    
    def __init__(self, adapter_id: str, name: str, config: dict):
        super().__init__(adapter_id, name, config)
        self._client: Optional[QQOfficialClient] = None
        self._ws: Optional[QQOfficialWS] = None
        self._bot: Optional[QQOfficialBot] = None
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """启动适配器:创建 client、bot,启动 WS 事件接收循环。"""
        self._running = True
        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")
        token = self.config.get("token", "")
        if not app_id or not app_secret:
            raise ValueError("QQ 官方适配器缺少 app_id 或 app_secret")
        
        self._client = QQOfficialClient(app_id, app_secret, token)
        self._bot = QQOfficialBot(self._client, app_id)
        
        # 注册 bot 到 lifecycle
        from core.lifecycle import get_driver
        driver = get_driver()
        await driver.trigger_bot_connect(self._bot)
        logger.info(f"[适配器 {self.adapter_id}] QQ 官方 Bot {app_id} 已连接")
        
        # 启动 WS 事件接收循环
        self._ws = QQOfficialWS(self._client, self._on_event)
        self._task = asyncio.create_task(self._ws.start())
    
    async def _on_event(self, payload: dict) -> None:
        """WS 事件回调:转换并 dispatch 到事件总线。"""
        try:
            event_type = payload.get("t", "")
            # 接收事件时先记录日志,方便定位是否收到消息
            logger.info(
                f"[适配器 {self.adapter_id}] 收到事件 t={event_type} s={payload.get('s')}"
            )
            event = convert_event(payload, self._bot.self_id, self.adapter_type)
            if event is None:
                # 记录被丢弃的事件类型,便于排查
                logger.debug(f"[适配器 {self.adapter_id}] 事件 {event_type} 未被转换,丢弃")
                return
            from core.connection import _dispatch_and_limit
            await _dispatch_and_limit(self._bot, event)
        except Exception as e:
            logger.error(f"[适配器 {self.adapter_id}] 事件处理失败: {e}", exc_info=True)
    
    async def stop(self) -> None:
        """停止适配器。"""
        self._running = False
        if self._ws:
            await self._ws.stop()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.close()
        if self._bot:
            from core.lifecycle import get_driver
            await get_driver().trigger_bot_disconnect(self._bot)
        self._bot = None
        self._client = None
        self._ws = None
        self._task = None
    
    async def test_connection(self) -> dict:
        """测试连接:始终创建临时 client,避免复用已运行适配器的 session。

        已运行适配器的 client session 是在 BotApp 事件循环中创建的,
        在 WebUI 事件循环中复用会报 "Timeout context manager should be used inside a task"。
        所以始终创建临时 client 测试。
        """
        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")
        if not app_id or not app_secret:
            return {"success": False, "info": "", "error": "缺少 app_id 或 app_secret"}
        client = QQOfficialClient(app_id, app_secret)
        try:
            info = await client.get_app_info()
            await client.close()
            name = info.get("username") or info.get("id") or app_id
            return {"success": True, "info": f"机器人 {name} 连接正常", "error": ""}
        except Exception as e:
            await client.close()
            return {"success": False, "info": "", "error": str(e)}
