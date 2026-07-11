from core import on_command, FinishedException
from core.onebot import Bot, GroupMessageEvent

from log_manager import log_manager
from plugins.utils import reply_msg

like_me = on_command("赞我", priority=1, block=True)


@like_me.handle()
async def handle_like_me(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    try:
        await bot.send_like(user_id=user_id, times=50)
        log_manager.log_notice("like", f"Sent 50 likes to user {user_id}")
        await like_me.finish(reply_msg(event, "👍 已为你点赞50次！"))
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_error("like", f"Failed to send like to {user_id}: {e}")
        await like_me.finish(reply_msg(event, "点赞失败，可能原因：非好友关系或今日点赞次数已达上限"))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

menu_registry.register(
    category="娱乐功能",
    item_name="赞我",
    text="👍 赞我",
    subcategory="点赞",
    subcategory_title="👍◇━点赞━◇👍",
    subcategory_trigger="点赞",
    subcategory_description="每日点赞",
)
