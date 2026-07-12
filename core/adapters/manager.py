"""适配器管理器:统一管理多个适配器实例的创建、启动、停止。"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.adapters.base import Adapter
from core.adapters.onebot_adapter import OneBotAdapter
from core.adapters.qq_official.adapter import QQOfficialAdapter

logger = logging.getLogger("adapter_manager")


class AdapterManager:
    """适配器管理器。
    
    根据 config_manager 中的 adapters 配置,创建对应的 Adapter 实例,
    并行启动所有 enabled 适配器的连接循环。
    """
    
    # 适配器类型 → 类的映射
    _ADAPTER_CLASSES = {
        "onebot_v11": OneBotAdapter,
        "qq_official": QQOfficialAdapter,
    }
    
    def __init__(self):
        self._adapters: Dict[str, Adapter] = {}  # adapter_id -> Adapter 实例
        self._fastapi_app: Optional[Any] = None  # ws_server 模式共享的 FastAPI app
    
    def _create_adapter(self, config: dict) -> Optional[Adapter]:
        """根据配置创建适配器实例(不启动)。"""
        adapter_type = config.get("type", "")
        adapter_cls = self._ADAPTER_CLASSES.get(adapter_type)
        if adapter_cls is None:
            logger.error(f"未知适配器类型: {adapter_type}(适配器 {config.get('id', '?')})")
            return None
        adapter_id = config.get("id", "")
        name = config.get("name", "")
        adapter_config = config.get("config", {}) or {}
        try:
            return adapter_cls(adapter_id, name, adapter_config)
        except Exception as e:
            logger.error(f"创建适配器 {adapter_id} 失败: {e}")
            return None
    
    async def start_all(self) -> None:
        """启动所有 enabled 适配器。"""
        from config_manager import config_manager
        adapters_config = config_manager.get_adapters()
        enabled = [a for a in adapters_config if a.get("enabled", True)]
        if not enabled:
            logger.warning("[适配器管理] 没有启用的适配器")
            return
        
        logger.info(f"[适配器管理] 准备启动 {len(enabled)} 个适配器")
        
        # 先创建所有适配器实例
        for cfg in enabled:
            adapter = self._create_adapter(cfg)
            if adapter is None:
                continue
            self._adapters[cfg["id"]] = adapter
        
        # 如果有 ws_server 模式的 OneBot 适配器,需要创建共享 FastAPI app
        has_ws_server = any(
            isinstance(a, OneBotAdapter) and a.config.get("mode") == "ws_server"
            for a in self._adapters.values()
        )
        if has_ws_server:
            from fastapi import FastAPI
            self._fastapi_app = FastAPI()
            # 为每个 ws_server 适配器挂载路由
            for adapter in self._adapters.values():
                if isinstance(adapter, OneBotAdapter) and adapter.config.get("mode") == "ws_server":
                    adapter.setup_ws_server_routes(self._fastapi_app)
        
        # 并行启动所有适配器
        tasks = []
        for adapter_id, adapter in list(self._adapters.items()):
            tasks.append(self._start_one(adapter_id, adapter))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 如果有 FastAPI app(ws_server 模式),在后台启动
        if self._fastapi_app is not None:
            asyncio.create_task(self._run_fastapi())
    
    async def _start_one(self, adapter_id: str, adapter: Adapter) -> None:
        """启动单个适配器,异常不传播。"""
        try:
            await adapter.start()
            logger.info(f"[适配器管理] 适配器 {adapter_id}({adapter.name})已启动")
        except Exception as e:
            logger.error(f"[适配器管理] 适配器 {adapter_id} 启动失败: {e}", exc_info=True)
    
    async def _run_fastapi(self) -> None:
        """在后台运行 FastAPI(ws_server 模式)。"""
        import uvicorn
        from config_manager import config_manager
        server_config = config_manager.get_server_config()
        host = server_config.get("host", "0.0.0.0")
        port = server_config.get("port", 8080)
        config = uvicorn.Config(
            self._fastapi_app,
            host=host,
            port=port,
            log_level="critical",
            access_log=False,
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    async def stop_all(self) -> None:
        """停止所有适配器。"""
        tasks = []
        for adapter_id, adapter in list(self._adapters.items()):
            tasks.append(self._stop_one(adapter_id, adapter))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._adapters.clear()
    
    async def _stop_one(self, adapter_id: str, adapter: Adapter) -> None:
        try:
            await adapter.stop()
            logger.info(f"[适配器管理] 适配器 {adapter_id} 已停止")
        except Exception as e:
            logger.error(f"[适配器管理] 停止适配器 {adapter_id} 失败: {e}")
    
    def get_adapter(self, adapter_id: str) -> Optional[Adapter]:
        """按 id 获取已运行的适配器实例。"""
        return self._adapters.get(adapter_id)
    
    def get_adapters(self) -> Dict[str, Adapter]:
        """获取所有已运行的适配器。"""
        return dict(self._adapters)
    
    async def reload_adapter(self, adapter_id: str) -> bool:
        """重载单个适配器(先停止再创建+启动)。返回是否成功。"""
        # 停止旧的
        old = self._adapters.pop(adapter_id, None)
        if old:
            await self._stop_one(adapter_id, old)
        # 从 config 读取新配置并启动
        from config_manager import config_manager
        cfg = config_manager.get_adapter_by_id(adapter_id)
        if not cfg or not cfg.get("enabled", True):
            return True
        adapter = self._create_adapter(cfg)
        if adapter is None:
            return False
        self._adapters[adapter_id] = adapter
        await self._start_one(adapter_id, adapter)
        return True


# 全局单例
_manager_instance: Optional["AdapterManager"] = None


def get_adapter_manager() -> "AdapterManager":
    """获取全局 AdapterManager 单例。

    WebUI 等外部模块通过此函数访问适配器管理器,
    以便查询已运行的适配器实例并调用其方法(如 test_connection)。
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = AdapterManager()
    return _manager_instance
