import abc
from typing import Any, Optional


class Adapter(abc.ABC):
    """适配器抽象基类。所有 bot 适配器(OneBot v11、QQ 官方等)均继承此类。"""

    adapter_type: str = ""  # 子类覆盖,如 "onebot_v11" / "qq_official"

    def __init__(self, adapter_id: str, name: str, config: dict):
        self.adapter_id = adapter_id
        self.name = name
        self.config = config
        self._running = False

    @abc.abstractmethod
    async def start(self) -> None:
        """启动适配器连接循环(由 AdapterManager 调用)。"""

    @abc.abstractmethod
    async def stop(self) -> None:
        """停止适配器,清理连接。"""

    @abc.abstractmethod
    async def test_connection(self) -> dict:
        """测试连接是否正常。返回 {"success": bool, "info": str, "error": str}。"""

    @property
    def is_running(self) -> bool:
        return self._running
