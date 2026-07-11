import asyncio
from typing import Callable, Dict, Optional, List, Any

class LifecycleManager:
    """生命周期管理器,替代 nonebot 的 Driver 钩子机制"""
    
    def __init__(self):
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._bot_connect_hooks: List[Callable] = []
        self._bot_disconnect_hooks: List[Callable] = []
        self._bots: Dict[str, Any] = {}  # self_id -> Bot 实例
    
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
        self._bots[bot.self_id] = bot
        for hook in self._bot_connect_hooks:
            result = hook(bot)
            if asyncio.iscoroutine(result):
                await result
    
    async def trigger_bot_disconnect(self, bot):
        """触发 Bot 断连钩子"""
        self._bots.pop(bot.self_id, None)
        for hook in self._bot_disconnect_hooks:
            result = hook(bot)
            if asyncio.iscoroutine(result):
                await result
    
    def get_bot(self) -> Optional[Any]:
        """获取当前连接的第一个 Bot 实例"""
        for bot in self._bots.values():
            return bot
        return None
    
    def get_bots(self) -> Dict[str, Any]:
        """获取所有已连接的 Bot 实例"""
        return self._bots


# 全局单例
_lifecycle = LifecycleManager()

# 模块级函数(替代 nonebot 的 get_driver/get_bot/get_bots)
def get_driver() -> LifecycleManager:
    return _lifecycle

def get_bot():
    return _lifecycle.get_bot()

def get_bots() -> Dict[str, Any]:
    return _lifecycle.get_bots()

# 装饰器(替代 nonebot 的 @driver.on_startup 等)
def on_startup(func):
    return _lifecycle.on_startup(func)

def on_shutdown(func):
    return _lifecycle.on_shutdown(func)

def on_bot_connect(func):
    return _lifecycle.on_bot_connect(func)

def on_bot_disconnect(func):
    return _lifecycle.on_bot_disconnect(func)
