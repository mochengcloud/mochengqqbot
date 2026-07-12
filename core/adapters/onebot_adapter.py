"""OneBot v11 适配器:封装现有 WSClientManager/WSServerManager 逻辑。"""
import asyncio
import logging
from typing import Any, Optional

from core.adapters.base import Adapter
from core.connection import WSClientManager, WSServerManager

logger = logging.getLogger("onebot_adapter")


class OneBotAdapter(Adapter):
    """OneBot v11 协议适配器。
    
    config 字段:
      - mode: "ws_client" 或 "ws_server"
      - ws_client 模式: url, access_token, reconnect_interval, heartbeat_interval
      - ws_server 模式: host, port, access_token
    """
    
    adapter_type = "onebot_v11"
    
    def __init__(self, adapter_id: str, name: str, config: dict):
        super().__init__(adapter_id, name, config)
        self._manager: Optional[Any] = None  # WSClientManager 或 WSServerManager
        self._task: Optional[asyncio.Task] = None
        self._fastapi_app: Optional[Any] = None  # ws_server 模式专用
    
    async def start(self) -> None:
        """启动 OneBot 适配器连接循环(在后台 task 中运行)。"""
        self._running = True
        mode = self.config.get("mode", "ws_client")
        if mode == "ws_client":
            url = self.config.get("url", "ws://127.0.0.1:3001")
            access_token = self.config.get("access_token", "")
            self._manager = WSClientManager()
            # 在后台 task 中运行,避免阻塞 AdapterManager
            self._task = asyncio.create_task(self._run_ws_client(url, access_token))
        elif mode == "ws_server":
            # ws_server 模式需要 FastAPI app,由 AdapterManager 统一挂载路由
            # 这里仅创建 manager,实际路由注册由 AdapterManager 处理
            self._manager = WSServerManager()
            # ws_server 模式通过路由挂载运行,不创建 task
            logger.info(f"[适配器 {self.adapter_id}] WSServer 模式,等待路由挂载")
        else:
            raise ValueError(f"未知 OneBot 模式: {mode}")
    
    async def _run_ws_client(self, url: str, access_token: str) -> None:
        """WS 客户端模式运行循环。"""
        try:
            await self._manager.start(url, access_token)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[适配器 {self.adapter_id}] WS 客户端异常: {e}")
        finally:
            self._running = False
    
    def setup_ws_server_routes(self, fastapi_app: Any) -> None:
        """ws_server 模式:在 FastAPI app 上注册 WS 路由。
        
        每个 ws_server 适配器注册到独立路径 /onebot/v11/ws/{adapter_id}。
        """
        if not isinstance(self._manager, WSServerManager):
            return
        access_token = self.config.get("access_token", "")
        # 为每个适配器注册独立端点
        endpoint = f"/onebot/v11/ws/{self.adapter_id}"
        self._manager.setup_routes(fastapi_app, access_token, endpoint)
        logger.info(f"[适配器 {self.adapter_id}] WSServer 路由挂载: {endpoint}")
    
    async def stop(self) -> None:
        """停止适配器。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._manager:
            await self._manager.stop()
            self._manager = None
    
    async def test_connection(self) -> dict:
        """测试连接:OneBot 调 get_login_info。"""
        try:
            from core.lifecycle import get_driver
            # 找到本适配器对应的 bot
            bots = get_driver().get_bots()
            for (self_id, adapter_type), bot in bots.items():
                if adapter_type == self.adapter_type and self_id:
                    try:
                        result = await asyncio.wait_for(
                            bot.call_api("get_login_info"), timeout=10
                        )
                        return {
                            "success": True,
                            "info": f"Bot {self_id} 连接正常",
                            "error": "",
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "info": "",
                            "error": f"调用 get_login_info 失败: {e}",
                        }
            return {
                "success": False,
                "info": "",
                "error": "未找到已连接的 OneBot Bot,请先启动适配器",
            }
        except Exception as e:
            return {"success": False, "info": "", "error": str(e)}
