"""权限系统:替代 nonebot 的 SUPERUSER/GROUP_ADMIN/GROUP_OWNER。

提供 Permission 类(支持 | 运算符组合)和全局权限常量。
"""
from typing import Any, Callable, Optional


class Permission:
    """权限检查器。支持 | 运算符组合。

    用法::

        perm = GROUP_ADMIN | GROUP_OWNER | SUPERUSER

        if await perm(bot, event):
            ...
    """

    def __init__(self, checker: Callable):
        self.checker = checker  # async (bot, event) -> bool

    async def check(self, bot: Any, event: Any) -> bool:
        """检查权限是否满足。"""
        return await self.checker(bot, event)

    async def __call__(self, bot: Any, event: Any) -> bool:
        """支持 ``await permission(bot, event)`` 调用方式。"""
        return await self.check(bot, event)

    def __or__(self, other: Optional["Permission"]) -> "Permission":
        """组合权限:任一满足即可。"""
        if other is None:
            return self

        async def combined_checker(bot: Any, event: Any) -> bool:
            return await self.check(bot, event) or await other.check(bot, event)

        return Permission(combined_checker)

    def __ror__(self, other: Any) -> "Permission":
        """支持 ``None | Permission`` 的写法。"""
        if other is None:
            return self
        return self  # 其他类型无法组合,返回自身


async def _check_superuser(bot: Any, event: Any) -> bool:
    """检查 event.user_id 是否在 config_manager 的 superusers 列表中。"""
    from config_manager import config_manager

    superusers = config_manager.get_bot_config().get("superusers", [])
    user_id = str(getattr(event, "user_id", ""))
    return user_id in superusers


async def _check_group_admin(bot: Any, event: Any) -> bool:
    """检查用户是否为群管理员。通过 bot.get_group_member_info 获取 role。"""
    if not hasattr(event, "group_id") or not event.group_id:
        return False
    try:
        info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=event.user_id
        )
        return info.get("role") == "admin"
    except Exception:
        return False


async def _check_group_owner(bot: Any, event: Any) -> bool:
    """检查用户是否为群主。"""
    if not hasattr(event, "group_id") or not event.group_id:
        return False
    try:
        info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=event.user_id
        )
        return info.get("role") == "owner"
    except Exception:
        return False


# 全局权限常量(与 nonebot 兼容)
SUPERUSER = Permission(_check_superuser)
GROUP_ADMIN = Permission(_check_group_admin)
GROUP_OWNER = Permission(_check_group_owner)
