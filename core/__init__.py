"""QQ Bot 核心包:统一导出事件总线、权限、生命周期、插件加载、OneBot 协议层与 BotApp。"""

# 事件总线
from core.event_bus import (
    on_message, on_command, on_notice, on_request,
    Matcher, FinishedException, CommandArg, ArgStr, T_State,
    dispatch, get_event_bus,
)

# 权限
from core.permission import (
    Permission, SUPERUSER, GROUP_ADMIN, GROUP_OWNER,
)

# 生命周期
from core.lifecycle import (
    get_driver, get_bot, get_bots,
    on_startup, on_shutdown, on_bot_connect, on_bot_disconnect,
)

# 插件加载
from core.plugin_loader import (
    load_plugins, load_plugin, reload_plugin,
)

# OneBot 协议层
from core.onebot import (
    Bot, Message, MessageSegment,
    GroupMessageEvent, PrivateMessageEvent, MessageEvent,
    NoticeEvent, GroupIncreaseNoticeEvent, GroupDecreaseNoticeEvent,
    GroupAdminNoticeEvent, GroupRecallNoticeEvent,
    RequestEvent, GroupRequestEvent,
    MetaEvent, LifecycleMetaEvent,
    parse_event,
)

# 版本号
from core.version import __version__

# BotApp
from core.app import BotApp

__all__ = [
    # event bus
    "on_message", "on_command", "on_notice", "on_request",
    "Matcher", "FinishedException", "CommandArg", "ArgStr", "T_State",
    "dispatch", "get_event_bus",
    # permission
    "Permission", "SUPERUSER", "GROUP_ADMIN", "GROUP_OWNER",
    # lifecycle
    "get_driver", "get_bot", "get_bots",
    "on_startup", "on_shutdown", "on_bot_connect", "on_bot_disconnect",
    # plugin loader
    "load_plugins", "load_plugin", "reload_plugin",
    # onebot
    "Bot", "Message", "MessageSegment",
    "GroupMessageEvent", "PrivateMessageEvent", "MessageEvent",
    "NoticeEvent", "GroupIncreaseNoticeEvent", "GroupDecreaseNoticeEvent",
    "GroupAdminNoticeEvent", "GroupRecallNoticeEvent",
    "RequestEvent", "GroupRequestEvent",
    "MetaEvent", "LifecycleMetaEvent",
    "parse_event",
    # app
    "BotApp",
    # version
    "__version__",
]
