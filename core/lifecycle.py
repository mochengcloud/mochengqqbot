import asyncio
from typing import Callable, Dict, Optional, List, Any

class LifecycleManager:
    """生命周期管理器,替代 nonebot 的 Driver 钩子机制"""
    
    def __init__(self):
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._bot_connect_hooks: List[Callable] = []
        self._bot_disconnect_hooks: List[Callable] = []
        self._bots: Dict[tuple, Any] = {}  # (self_id, adapter_type) -> Bot 实例
    
    def on_startup(self, func):
        """注册启动钩子(支持同步和异步函数)"""
        self._startup_hooks.append(func)
        return func
    
    def on_shutdown(self, func):
        """注册关闭钩子"""
        self._shutdown_hooks.append(func)
        return func
    
    def on_bot_connect(self, func):
        """注册 Bot 连接钩子"""
        self._bot_connect_hooks.append(func)
        return func
    
    def on_bot_disconnect(self, func):
        """注册 Bot 断连钩子"""
        self._bot_disconnect_hooks.append(func)
        return func
    
    async def trigger_startup(self):
        """触发所有启动钩子"""
        for hook in self._startup_hooks:
            result = hook()
            if asyncio.iscoroutine(result):
                await result
    
    async def trigger_shutdown(self):
        """触发所有关闭钩子"""
        for hook in self._shutdown_hooks:
            result = hook()
            if asyncio.iscoroutine(result):
                await result
    
    async def trigger_bot_connect(self, bot):
        """触发 Bot 连接钩子"""
        key = (bot.self_id, getattr(bot, "adapter_type", "onebot_v11"))
        self._bots[key] = bot
        for hook in self._bot_connect_hooks:
            result = hook(bot)
            if asyncio.iscoroutine(result):
                await result
    
    async def trigger_bot_disconnect(self, bot):
        """触发 Bot 断连钩子"""
        key = (bot.self_id, getattr(bot, "adapter_type", "onebot_v11"))
        self._bots.pop(key, None)
        for hook in self._bot_disconnect_hooks:
            result = hook(bot)
            if asyncio.iscoroutine(result):
                await result
    
    def get_bot(self, adapter_type: Optional[str] = None) -> Optional[Any]:
        """获取第一个连接的 Bot 实例。可按 adapter_type 筛选。"""
        for (sid, atype), bot in self._bots.items():
            if adapter_type is None or atype == adapter_type:
                return bot
        return None
    
    def get_bots(self, adapter_type: Optional[str] = None) -> Dict[tuple, Any]:
        """获取所有已连接的 Bot 实例。可按 adapter_type 筛选。"""
        if adapter_type is None:
            return dict(self._bots)
        return {k: v for k, v in self._bots.items() if k[1] == adapter_type}


# 全局单例
_lifecycle = LifecycleManager()

# 模块级函数(替代 nonebot 的 get_driver/get_bot/get_bots)
def get_driver() -> LifecycleManager:
    return _lifecycle

def get_bot(adapter_type: Optional[str] = None):
    return _lifecycle.get_bot(adapter_type)

def get_bots(adapter_type: Optional[str] = None) -> Dict[tuple, Any]:
    return _lifecycle.get_bots(adapter_type)

# 装饰器(替代 nonebot 的 @driver.on_startup 等)
def on_startup(func):
    return _lifecycle.on_startup(func)

def on_shutdown(func):
    return _lifecycle.on_shutdown(func)

def on_bot_connect(func):
    return _lifecycle.on_bot_connect(func)

def on_bot_disconnect(func):
    return _lifecycle.on_bot_disconnect(func)
