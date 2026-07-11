import aiohttp
import asyncio
import json as json_module
from typing import Dict, List, Optional

from core import on_message, on_command, on_shutdown, CommandArg, GROUP_ADMIN, GROUP_OWNER, SUPERUSER
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from config_manager import config_manager
from log_manager import log_manager

# 全局共享Session和并发信号量
_session: Optional[aiohttp.ClientSession] = None
_semaphore: Optional[asyncio.Semaphore] = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=10,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _session


async def _close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


on_shutdown(_close_session)


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(10)
    return _semaphore


def _update_semaphore(max_concurrent: int) -> None:
    global _semaphore
    _semaphore = asyncio.Semaphore(max(1, max_concurrent))


content_check_handler = on_message(priority=3, block=False)

# 群管理员违规检测配置命令
cc_toggle = on_command("违规检测", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_type = on_command("违规类型", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_desc = on_command("违规描述", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_warning = on_command("违规提示", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_provider = on_command("违规供应商", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_model = on_command("违规模型", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_set_concurrent = on_command("违规并发", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
cc_show_config = on_command("违规配置", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

# 违规类型列表
VIOLATION_TYPES = ["广告", "脏话", "骂人", "色情"]

# 违规类型默认描述（AI检测用）
VIOLATION_TYPE_DEFAULTS = {
    "广告": "推销产品、带联系方式（QQ/微信/链接/网盘/资源号/二维码），包括标准链接、变体链接写法（如'点'代替'.'、'dot'代替'.'、空格或符号隔开、谐音替换）、明显指向某个站点的域名/子域名、任何形式的引流信息（加好友、进群、私聊领福利、刷单等）",
    "脏话": "含侮辱性脏词（如SB、TMD、草泥马、傻逼）或明显的粗俗用语",
    "骂人": "人身攻击、诅咒、羞辱对方或其家人（如'你去死''你智商有问题''全家'）",
    "色情": "描述性行为、露骨色情用语、求资源/视频/网站/网盘、约炮、发'你懂的'等隐晦色情暗示",
}


def _build_check_prompt(enabled_types_info: List[dict], custom_prompt: str = "") -> str:
    """构建检测用的prompt"""
    if custom_prompt:
        return custom_prompt

    type_lines = []
    for i, info in enumerate(enabled_types_info, 1):
        type_lines.append(f" {i}. {info['name']}：{info['description']}")

    enabled_names = "、".join(info['name'] for info in enabled_types_info)

    return f"""你是一个内容安全审核助手。请判断以下用户发言是否违规。违规类型包括：
{chr(10).join(type_lines)}

若违规，请按格式输出：
违规：是
类型：{enabled_names}（可多个）
原因：简要说明判断理由

若不违规，输出：
违规：否"""


def _parse_violation_result(result_text: str) -> dict:
    """解析AI返回的违规检测结果，返回 {violation: bool, type: str, reason: str}"""
    text = result_text.strip()

    # 检查是否违规
    is_violation = False
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("违规"):
            # 匹配 "违规：是" / "违规:是" / "违规：否" 等
            if "是" in line and "否" not in line:
                is_violation = True
            break

    # 也兼容简单的"是/否"回答
    if not is_violation and "违规" not in text:
        lower = text.lower()
        neg_words = ["不是", "不属于", "否", "没有", "no"]
        for w in neg_words:
            if w in lower:
                return {"violation": False, "type": "", "reason": ""}
        pos_words = ["是", "属于", "yes"]
        for w in pos_words:
            if w in lower:
                is_violation = True
                break

    if not is_violation:
        return {"violation": False, "type": "", "reason": ""}

    # 提取类型
    violation_type = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("类型"):
            # 匹配 "类型：广告" / "类型:广告/脏话" 等
            content = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            violation_type = content
            break

    # 提取原因
    reason = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("原因"):
            content = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            reason = content
            break

    if not reason:
        reason = text[:100]

    return {"violation": True, "type": violation_type, "reason": reason}


def _get_enabled_types_info(violation_types: dict) -> List[dict]:
    """获取启用的违规类型信息列表"""
    result = []
    for t in VIOLATION_TYPES:
        type_config = violation_types.get(t, True)
        if isinstance(type_config, bool):
            if type_config:
                result.append({
                    "name": t,
                    "description": VIOLATION_TYPE_DEFAULTS.get(t, t),
                })
        elif isinstance(type_config, dict):
            if type_config.get("enabled", True):
                result.append({
                    "name": t,
                    "description": type_config.get("description", VIOLATION_TYPE_DEFAULTS.get(t, t)),
                })
    return result


async def _call_chat_api(api_base: str, api_key: str, model: str,
                        messages: List[dict], max_tokens: int = 128,
                        temperature: float = 0.1,
                        api_format: str = "openai") -> str:
    if api_format == "ollama":
        url = f"{api_base.rstrip('/')}/api/chat"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature
            }
        }
    else:
        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

    sem = _get_semaphore()
    async with sem:
        session = _get_session()
        async with session.post(url, headers=headers, json=payload,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                try:
                    err_data = json_module.loads(body)
                    err_msg = err_data.get("error", {})
                    if isinstance(err_msg, dict):
                        msg = err_msg.get("message", body[:200])
                    else:
                        msg = str(err_msg)
                except Exception:
                    msg = body[:200]
                raise Exception(f"API请求失败({resp.status}): {msg}")
            data = await resp.json()
            if api_format == "ollama":
                return data["message"]["content"]
            else:
                return data["choices"][0]["message"]["content"]


def _get_provider_for_group(group_id: int) -> Optional[dict]:
    """获取群配置的供应商，若未配置则使用全局第一个可用供应商"""
    config = config_manager.get_content_check_config(group_id)
    provider_name = config.get("provider", "")

    providers = config_manager.get_ai_providers()
    if provider_name and provider_name in providers and providers[provider_name].get("enabled", True):
        return {"name": provider_name, **providers[provider_name]}

    # 回退到群AI聊天配置的供应商
    ai_config = config_manager.get_ai_chat_group_config(group_id)
    provider_name = ai_config.get("provider", "")
    if provider_name and provider_name in providers and providers[provider_name].get("enabled", True):
        return {"name": provider_name, **providers[provider_name]}

    # 回退到全局第一个可用供应商
    for name, data in providers.items():
        if data.get("enabled", True):
            return {"name": name, **data}

    return None


def _get_model_for_group(group_id: int) -> str:
    """获取群配置的模型，若未配置则使用供应商默认模型"""
    config = config_manager.get_content_check_config(group_id)
    model = config.get("model", "").strip()
    if model:
        return model

    # 回退到群AI聊天配置的模型
    ai_config = config_manager.get_ai_chat_group_config(group_id)
    model = ai_config.get("model", "").strip()
    if model:
        return model

    # 回退到供应商默认模型
    provider = _get_provider_for_group(group_id)
    if provider:
        return provider.get("default_model", "")

    return ""


def _is_admin(event: GroupMessageEvent) -> bool:
    """检查用户是否为管理员/群主/超级用户"""
    superusers = config_manager.config.get("bot", {}).get("superusers", [])
    if str(event.user_id) in superusers:
        return True
    role = getattr(event.sender, "role", "")
    return role in ("admin", "owner")


@content_check_handler.handle()
async def handle_content_check(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id

    # 检查群是否启用
    if not config_manager.is_group_enabled(group_id):
        return

    # 检查违规检测是否启用
    config = config_manager.get_content_check_config(group_id)
    if not config.get("enabled", False):
        return

    # 更新并发信号量
    max_concurrent = config.get("max_concurrent", 10)
    _update_semaphore(max_concurrent)

    # 跳过管理员消息
    if _is_admin(event):
        return

    # 检查授权
    if not config_manager.is_feature_authorized(group_id, "AI违规检测"):
        return

    # 获取消息纯文本
    plain_text = event.get_plaintext().strip()
    if not plain_text or len(plain_text) < 2:
        return

    # 获取启用的违规类型信息
    violation_types = config.get("violation_types", {})
    enabled_types_info = _get_enabled_types_info(violation_types)
    if not enabled_types_info:
        return

    # 获取供应商和模型
    provider = _get_provider_for_group(group_id)
    if not provider:
        return

    api_base = provider.get("api_base", "")
    api_key = provider.get("api_key", "")
    api_format = provider.get("api_format", "openai")
    model = _get_model_for_group(group_id)

    if not api_base or not model or (api_format != "ollama" and not api_key):
        return

    # 构建检测prompt
    custom_prompt = config.get("custom_prompt", "").strip()
    system_prompt = _build_check_prompt(enabled_types_info, custom_prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": plain_text}
    ]

    temperature = config.get("temperature", 0.1)
    max_tokens = config.get("max_tokens", 128)

    # 调用AI检测
    try:
        result_text = await _call_chat_api(api_base, api_key, model, messages,
                                           max_tokens=max_tokens, temperature=temperature,
                                           api_format=api_format)
    except Exception as e:
        log_manager.log_command(user_id, group_id, "违规检测错误", str(e)[:200])
        return

    # 解析结果
    result = _parse_violation_result(result_text)
    if not result["violation"]:
        return

    violation_type = result["type"] or "违规"
    reason = result["reason"] or result_text.strip()[:100]

    log_manager.log_command(user_id, group_id, "违规检测", f"类型={violation_type} 原因={reason} 内容={plain_text[:50]}")

    # 撤回消息
    try:
        await bot.delete_msg(message_id=event.message_id)
    except Exception as e:
        log_manager.log_command(user_id, group_id, "违规撤回失败", str(e)[:100])

    # 发送警告
    warning_template = config.get("warning_template", "@用户 ⚠️ 你的发言因【{type}】已被撤回")
    warning_text = warning_template.replace("{type}", violation_type).replace("{reason}", reason)

    at_seg = MessageSegment.at(user_id)
    await bot.send_group_msg(group_id=group_id, message=at_seg + " " + warning_text)


# === 群管理员配置命令 ===

@cc_toggle.handle()
async def handle_cc_toggle(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_content_check_config(group_id)
        status = "已开启" if config.get("enabled", False) else "已关闭"
        await cc_toggle.finish(f"当前群违规检测{status}\n用法: 违规检测 开/关")

    if arg in ("开", "开启", "on", "true"):
        config_manager.update_content_check_config(group_id, {"enabled": True})
        await cc_toggle.finish("违规检测已开启")
    elif arg in ("关", "关闭", "off", "false"):
        config_manager.update_content_check_config(group_id, {"enabled": False})
        await cc_toggle.finish("违规检测已关闭")
    else:
        await cc_toggle.finish("参数错误，请输入 开 或 关")


@cc_set_type.handle()
async def handle_cc_set_type(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_content_check_config(group_id)
        violation_types = config.get("violation_types", {})
        lines = ["违规类型开关状态："]
        for t in VIOLATION_TYPES:
            type_config = violation_types.get(t, True)
            if isinstance(type_config, dict):
                enabled = type_config.get("enabled", True)
            else:
                enabled = bool(type_config)
            status = "开启" if enabled else "关闭"
            lines.append(f"  {t}: {status}")
        lines.append("\n用法: 违规类型 类型名 开/关")
        lines.append(f"可用类型: {'、'.join(VIOLATION_TYPES)}")
        await cc_set_type.finish("\n".join(lines))

    parts = arg.split()
    if len(parts) != 2:
        await cc_set_type.finish("用法: 违规类型 类型名 开/关\n可用类型: " + "、".join(VIOLATION_TYPES))

    type_name, action = parts

    # 支持简写
    type_map = {
        "广告": "广告",
        "脏话": "脏话",
        "骂人": "骂人",
        "色情": "色情",
        "色": "色情",
    }
    full_type = type_map.get(type_name, type_name)
    if full_type not in VIOLATION_TYPES:
        await cc_set_type.finish(f"未知违规类型: {type_name}\n可用类型: " + "、".join(VIOLATION_TYPES))

    config = config_manager.get_content_check_config(group_id)
    violation_types = config.get("violation_types", {})
    # 确保所有类型都有完整结构
    for t in VIOLATION_TYPES:
        if t not in violation_types:
            violation_types[t] = {"enabled": True, "description": VIOLATION_TYPE_DEFAULTS.get(t, t)}
        elif isinstance(violation_types[t], bool):
            violation_types[t] = {"enabled": violation_types[t], "description": VIOLATION_TYPE_DEFAULTS.get(t, t)}

    if action in ("开", "开启", "on", "true"):
        violation_types[full_type]["enabled"] = True
        config_manager.update_content_check_config(group_id, {"violation_types": violation_types})
        await cc_set_type.finish(f"已开启【{full_type}】检测")
    elif action in ("关", "关闭", "off", "false"):
        violation_types[full_type]["enabled"] = False
        config_manager.update_content_check_config(group_id, {"violation_types": violation_types})
        await cc_set_type.finish(f"已关闭【{full_type}】检测")
    else:
        await cc_set_type.finish("参数错误，请输入 开 或 关")


@cc_set_desc.handle()
async def handle_cc_set_desc(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_content_check_config(group_id)
        violation_types = config.get("violation_types", {})
        lines = ["违规类型描述："]
        for t in VIOLATION_TYPES:
            type_config = violation_types.get(t, True)
            if isinstance(type_config, dict):
                desc = type_config.get("description", VIOLATION_TYPE_DEFAULTS.get(t, t))
            else:
                desc = VIOLATION_TYPE_DEFAULTS.get(t, t)
            lines.append(f"  {t}: {desc}")
        lines.append("\n用法: 违规描述 类型名 描述内容")
        await cc_set_desc.finish("\n".join(lines))

    parts = arg.split(maxsplit=1)
    if len(parts) < 2:
        await cc_set_desc.finish("用法: 违规描述 类型名 描述内容\n可用类型: " + "、".join(VIOLATION_TYPES))

    type_name, description = parts

    type_map = {
        "广告": "广告",
        "脏话": "脏话",
        "骂人": "骂人",
        "色情": "色情",
        "色": "色情",
    }
    full_type = type_map.get(type_name, type_name)
    if full_type not in VIOLATION_TYPES:
        await cc_set_desc.finish(f"未知违规类型: {type_name}\n可用类型: " + "、".join(VIOLATION_TYPES))

    config = config_manager.get_content_check_config(group_id)
    violation_types = config.get("violation_types", {})
    # 确保结构完整
    for t in VIOLATION_TYPES:
        if t not in violation_types:
            violation_types[t] = {"enabled": True, "description": VIOLATION_TYPE_DEFAULTS.get(t, t)}
        elif isinstance(violation_types[t], bool):
            violation_types[t] = {"enabled": violation_types[t], "description": VIOLATION_TYPE_DEFAULTS.get(t, t)}

    violation_types[full_type]["description"] = description
    config_manager.update_content_check_config(group_id, {"violation_types": violation_types})
    await cc_set_desc.finish(f"已设置【{full_type}】描述为: {description}")


@cc_set_warning.handle()
async def handle_cc_set_warning(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_content_check_config(group_id)
        current = config.get("warning_template", "@用户 ⚠️ 你的发言因违规已被撤回")
        await cc_set_warning.finish(f"当前提示语: {current}\n用法: 违规提示 提示内容\n可用占位符: {{reason}}(原因)")

    config_manager.update_content_check_config(group_id, {"warning_template": arg})
    await cc_set_warning.finish(f"已设置违规提示语为: {arg}")


@cc_set_provider.handle()
async def handle_cc_set_provider(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    provider_name = args.extract_plain_text().strip()

    if not provider_name:
        config = config_manager.get_content_check_config(group_id)
        current = config.get("provider", "自动选择")
        await cc_set_provider.finish(f"当前供应商: {current}\n用法: 违规供应商 供应商名称\n留空则自动选择可用供应商")

    if provider_name in ("自动", "auto", "默认"):
        config_manager.update_content_check_config(group_id, {"provider": ""})
        await cc_set_provider.finish("已设置为自动选择供应商")

    providers = config_manager.get_ai_providers()
    if provider_name not in providers:
        await cc_set_provider.finish(f"供应商 {provider_name} 不存在")

    if not providers[provider_name].get("enabled", True):
        await cc_set_provider.finish(f"供应商 {provider_name} 已禁用")

    config_manager.update_content_check_config(group_id, {"provider": provider_name})
    await cc_set_provider.finish(f"已设置违规检测供应商为: {provider_name}")


@cc_set_model.handle()
async def handle_cc_set_model(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    model_name = args.extract_plain_text().strip()

    if not model_name:
        config = config_manager.get_content_check_config(group_id)
        current = config.get("model", "") or "自动选择"
        await cc_set_model.finish(f"当前模型: {current}\n用法: 违规模型 模型名称\n留空则自动选择")

    if model_name in ("自动", "auto", "默认"):
        config_manager.update_content_check_config(group_id, {"model": ""})
        await cc_set_model.finish("已设置为自动选择模型")

    config_manager.update_content_check_config(group_id, {"model": model_name})
    await cc_set_model.finish(f"已设置违规检测模型为: {model_name}")


@cc_set_concurrent.handle()
async def handle_cc_set_concurrent(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_content_check_config(group_id)
        current = config.get("max_concurrent", 10)
        await cc_set_concurrent.finish(f"当前最大并发数: {current}\n用法: 违规并发 数字(1-50)")

    try:
        val = int(arg)
        if val < 1 or val > 50:
            raise ValueError
    except ValueError:
        await cc_set_concurrent.finish("参数错误，请输入1-50之间的数字")

    config_manager.update_content_check_config(group_id, {"max_concurrent": val})
    _update_semaphore(val)
    await cc_set_concurrent.finish(f"已设置最大并发数为: {val}")


@cc_show_config.handle()
async def handle_cc_show_config(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config = config_manager.get_content_check_config(group_id)

    violation_types = config.get("violation_types", {})
    type_lines = []
    for t in VIOLATION_TYPES:
        type_config = violation_types.get(t, True)
        if isinstance(type_config, dict):
            enabled = type_config.get("enabled", True)
            desc = type_config.get("description", VIOLATION_TYPE_DEFAULTS.get(t, t))
        else:
            enabled = bool(type_config)
            desc = VIOLATION_TYPE_DEFAULTS.get(t, t)
        status = "开启" if enabled else "关闭"
        type_lines.append(f"  {t}: {status} | {desc}")

    provider = config.get("provider", "") or "自动选择"
    model = config.get("model", "") or "自动选择"

    lines = [
        f"违规检测配置 (群{group_id}):",
        f"  状态: {'开启' if config.get('enabled', False) else '关闭'}",
        f"  供应商: {provider}",
        f"  模型: {model}",
        f"  违规类型:",
        *type_lines,
        f"  提示语: {config.get('warning_template', '@用户 ⚠️ 你的发言因违规已被撤回')}",
        f"  温度: {config.get('temperature', 0.1)}",
        f"  最大Token: {config.get('max_tokens', 128)}",
        f"  最大并发数: {config.get('max_concurrent', 10)}",
        "",
        "配置命令:",
        "  违规检测 开/关 | 违规类型 类型名 开/关",
        "  违规描述 类型名 描述内容 | 违规提示 内容",
        "  违规供应商 名称 | 违规模型 名称 | 违规并发 数字",
        "  违规配置",
    ]

    await cc_show_config.finish("\n".join(lines))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_CONTENT_CHECK_MENU_ITEMS = {
    "违规检测": "🛡️ 违规检测开关",
    "违规类型": "🛡️ 违规类型",
    "违规描述": "🛡️ 违规描述",
    "违规提示": "🛡️ 违规提示",
    "违规供应商": "🛡️ 违规供应商",
    "违规模型": "🛡️ 违规模型",
    "违规并发": "🛡️ 违规并发",
    "违规配置": "🛡️ 违规配置",
}

for _item_name, _text in _CONTENT_CHECK_MENU_ITEMS.items():
    menu_registry.register(
        category="违规检测",
        item_name=_item_name,
        text=_text,
        category_title="🛡️◇━违规检测━◇🛡️",
        category_trigger="违规检测",
        category_description="AI违规检测·类型·提示·配置",
    )
