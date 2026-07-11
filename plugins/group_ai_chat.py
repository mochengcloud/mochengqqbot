import aiohttp
import asyncio
import base64
import json as json_module
import random
from typing import Dict, List, Optional

from core import on_message, on_command, on_startup, on_shutdown, CommandArg, FinishedException, GROUP_ADMIN, GROUP_OWNER, SUPERUSER
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

# 共享HTTP Session（连接池，支持高并发）
_http_session: Optional[aiohttp.ClientSession] = None


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        connector = aiohttp.TCPConnector(
            limit=0,           # 0 = 不限制总连接数
            limit_per_host=0,  # 0 = 不限制每host连接数
            ttl_dns_cache=300, # DNS缓存5分钟
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        _http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _http_session


async def _close_session():
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        _http_session = None


on_shutdown(_close_session)

ai_chat_handler = on_message(priority=4, block=False)

# 群管理员AI配置命令
ai_set_provider = on_command("ai供应商", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_set_model = on_command("ai模型", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_set_prompt = on_command("ai提示词", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_toggle = on_command("ai开关", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_set_temp = on_command("ai温度", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_set_tokens = on_command("ai长度", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_set_context = on_command("ai上下文", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_show_config = on_command("ai配置", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_list_providers = on_command("ai供应商列表", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_fetch_models = on_command("ai拉取模型", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_proactive_toggle = on_command("主动回复", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
ai_proactive_prob = on_command("主动回复概率", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

import time as time_module

# 对话上下文存储: key="{group_id}-{user_id}", value={"messages": [...], "last_access": timestamp}
chat_contexts: Dict[str, dict] = {}
MAX_CONTEXTS = 10000
CONTEXT_TTL = 7200


def _get_context_key(group_id: int, user_id: int) -> str:
    return f"{group_id}-{user_id}"


def _get_context(key: str) -> List[dict]:
    entry = chat_contexts.get(key)
    if entry:
        entry["last_access"] = time_module.time()
        return entry["messages"]
    return []


def _set_context(key: str, messages: List[dict]):
    chat_contexts[key] = {"messages": messages, "last_access": time_module.time()}
    if len(chat_contexts) > MAX_CONTEXTS:
        oldest = min(chat_contexts.items(), key=lambda x: x[1]["last_access"])
        del chat_contexts[oldest[0]]


def _cleanup_contexts():
    now = time_module.time()
    expired = [k for k, v in chat_contexts.items() if now - v["last_access"] > CONTEXT_TTL]
    for k in expired:
        del chat_contexts[k]


on_startup(_cleanup_contexts)
on_shutdown(_cleanup_contexts)


def _extract_text(event: GroupMessageEvent) -> str:
    parts = []
    for seg in event.message:
        if seg.type == "text":
            parts.append(seg.data.get("text", "").strip())
    return " ".join(parts).strip()


def _extract_images(event: GroupMessageEvent) -> List[str]:
    """提取消息中的图片URL列表"""
    urls = []
    for seg in event.message:
        if seg.type == "image":
            url = seg.data.get("url", "") or seg.data.get("file", "")
            if url:
                urls.append(url)
    return urls


async def _download_image_as_base64(url: str) -> Optional[str]:
    """下载图片并转为base64"""
    try:
        session = await _get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.read()
                return base64.b64encode(data).decode("utf-8")
    except Exception:
        pass
    return None


async def _call_chat_api(api_base: str, api_key: str, model: str,
                         messages: List[dict], max_tokens: int = 2048,
                         temperature: float = 0.7,
                         api_format: str = "openai",
                         images: Optional[List[str]] = None) -> str:
    if api_format == "ollama":
        # Ollama格式: POST /api/chat
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
        # Ollama多模态: 在最后一条user消息中添加images字段(base64列表)
        if images and payload["messages"]:
            last_msg = payload["messages"][-1]
            if last_msg.get("role") == "user":
                last_msg["images"] = images
    else:
        # OpenAI格式: POST /chat/completions
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
        # OpenAI多模态: 将最后一条user消息的content改为多部分格式
        if images and payload["messages"]:
            last_msg = payload["messages"][-1]
            if last_msg.get("role") == "user":
                text_content = last_msg.get("content", "")
                content_parts = []
                if text_content:
                    content_parts.append({"type": "text", "text": text_content})
                for img_b64 in images:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                    })
                last_msg["content"] = content_parts

    session = await _get_session()
    async with session.post(url, headers=headers, json=payload,
                            timeout=aiohttp.ClientTimeout(total=120)) as resp:
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


async def _call_with_failover(
    providers_order: List[tuple],
    messages: List[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
    images: Optional[List[str]] = None,
) -> tuple:
    """按顺序尝试多个供应商,失败切换下一个。

    Args:
        providers_order: 有序供应商列表,每项为 (provider_name, provider_config, model)
                         provider_config 含 api_base/api_key/api_format/default_model
    Returns:
        (reply_text, used_provider_name, used_model) 成功时
        (None, None, None) 全部失败时
    """
    last_error = ""
    for provider_name, provider, model in providers_order:
        api_base = provider.get("api_base", "")
        api_key = provider.get("api_key", "")
        api_format = provider.get("api_format", "openai")
        try:
            reply = await _call_chat_api(
                api_base, api_key, model, messages,
                max_tokens=max_tokens, temperature=temperature,
                api_format=api_format, images=images,
            )
            return reply, provider_name, model
        except Exception as e:
            last_error = str(e)
            # 继续尝试下一个供应商
            continue
    return None, None, None


async def _fetch_models(api_base: str, api_key: str, api_format: str = "openai") -> List[str]:
    if api_format == "ollama":
        url = f"{api_base.rstrip('/')}/api/tags"
        headers = {"Content-Type": "application/json"}
    else:
        url = f"{api_base.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    session = await _get_session()
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise Exception(f"获取模型列表失败({resp.status}): {body[:500]}")
        data = await resp.json()
        if api_format == "ollama":
            models = [m["name"] for m in data.get("models", [])]
        else:
            models = [m["id"] for m in data.get("data", [])]
        models.sort()
        return models


@ai_chat_handler.handle()
async def handle_ai_chat(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id

    # 检查全局AI聊天开关
    ai_chat_config = config_manager.get_ai_chat_config()
    if not ai_chat_config.get("enabled", True):
        return

    # 检查群启用
    if not config_manager.is_group_enabled(group_id):
        return

    # 获取群AI配置
    group_ai_config = config_manager.get_ai_chat_group_config(group_id)
    if not group_ai_config.get("enabled", False):
        return

    # 判断触发方式
    is_at_trigger = event.to_me

    if is_at_trigger:
        # @触发
        user_input = _extract_text(event)
        image_urls = _extract_images(event)
        if not user_input and not image_urls:
            await ai_chat_handler.finish(reply_msg(event, "请在@我后输入你想说的话"))
    elif group_ai_config.get("proactive_reply", False):
        # 主动回复：按概率触发
        probability = group_ai_config.get("proactive_reply_probability", 0.1)
        if random.random() < probability:
            user_input = _extract_text(event)
            image_urls = _extract_images(event)
            if not user_input:
                return  # 空消息不主动回复
        else:
            return
    else:
        return

    # 检查授权（仅在触发后检查，避免对每条消息都响应）
    if not config_manager.is_feature_authorized(group_id, "AI聊天"):
        await ai_chat_handler.finish(reply_msg(event, "本群未授权AI聊天功能，请联系管理员"))

    # 获取供应商配置(支持故障转移)
    provider_name = group_ai_config.get("provider", "")
    providers = config_manager.get_ai_providers()

    # 构建有序供应商尝试列表:首选群配置的 provider,然后其它 enabled providers
    providers_order: List[tuple] = []
    if provider_name and provider_name in providers:
        provider = providers[provider_name]
        if provider.get("enabled", True):
            model = group_ai_config.get("model", "").strip() or provider.get("default_model", "")
            if provider.get("api_base", "") and model and (provider.get("api_format", "openai") == "ollama" or provider.get("api_key", "")):
                providers_order.append((provider_name, provider, model))

    # 追加其它 enabled providers 作为 fallback
    for name, prov in providers.items():
        if name == provider_name:
            continue
        if not prov.get("enabled", True):
            continue
        # fallback provider 用其自己的 default_model(群配置 model 可能不适用其它供应商)
        m = prov.get("default_model", "")
        if prov.get("api_base", "") and m and (prov.get("api_format", "openai") == "ollama" or prov.get("api_key", "")):
            providers_order.append((name, prov, m))

    if not providers_order:
        await ai_chat_handler.finish(reply_msg(event, "无可用AI供应商，请联系管理员"))

    # 构建消息列表
    system_prompt = group_ai_config.get("system_prompt", "你是一个友好的AI助手")
    max_context = group_ai_config.get("max_context", 10)
    max_tokens = group_ai_config.get("max_tokens", 2048)
    temperature = group_ai_config.get("temperature", 0.7)

    key = _get_context_key(group_id, user_id)
    ctx_messages = _get_context(key)

    # 并行下载图片为base64
    image_base64_list: List[str] = []
    if image_urls:
        tasks = [_download_image_as_base64(url) for url in image_urls[:5]]
        results = await asyncio.gather(*tasks)
        image_base64_list = [r for r in results if r]

    # 如果没有文字但有图片，设置默认提示
    if not user_input and image_base64_list:
        user_input = "请描述这张图片"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(ctx_messages[-max_context:])
    messages.append({"role": "user", "content": user_input})

    log_manager.log_command(user_id, group_id, "AI聊天",
                            f"{user_input[:100]}{' [+图片]' if image_base64_list else ''}")

    # 调用API(带故障转移:首选失败自动切换备用供应商)
    reply, used_provider, used_model = await _call_with_failover(
        providers_order, messages,
        max_tokens=max_tokens, temperature=temperature,
        images=image_base64_list if image_base64_list else None,
    )

    if reply is None:
        log_manager.log_command(user_id, group_id, "AI聊天错误", "所有供应商均不可用")
        await ai_chat_handler.finish(reply_msg(event, "无可用AI供应商，请联系管理员"))

    # 更新上下文
    ctx_messages.append({"role": "user", "content": user_input})
    ctx_messages.append({"role": "assistant", "content": reply})
    # 限制上下文长度
    if len(ctx_messages) > max_context * 2:
        ctx_messages = ctx_messages[-max_context * 2:]
    _set_context(key, ctx_messages)

    # 截断过长回复
    if len(reply) > 4500:
        reply = reply[:4490] + "\n...(回复过长已截断)"

    await ai_chat_handler.finish(reply_msg(event, reply))


async def _handle_list_models(bot: Bot, event: GroupMessageEvent, group_ai_config: dict):
    provider_name = group_ai_config.get("provider", "")
    providers = config_manager.get_ai_providers()

    if not provider_name or provider_name not in providers:
        await ai_chat_handler.finish(reply_msg(event, "未配置AI供应商，无法获取模型列表"))

    provider = providers[provider_name]
    api_base = provider.get("api_base", "")
    api_key = provider.get("api_key", "")

    if not api_base or not api_key:
        await ai_chat_handler.finish(reply_msg(event, "AI供应商配置不完整"))

    try:
        models = await _fetch_models(api_base, api_key)
        if not models:
            await ai_chat_handler.finish(reply_msg(event, "该供应商暂无可用模型"))

        lines = [f"供应商 {provider_name} 可用模型："]
        for i, m in enumerate(models[:30], 1):
            default_model = provider.get("default_model", "")
            marker = " (默认)" if m == default_model else ""
            lines.append(f"  {i}. {m}{marker}")

        if len(models) > 30:
            lines.append(f"  ...共 {len(models)} 个模型，仅显示前30个")

        await ai_chat_handler.finish(reply_msg(event, "\n".join(lines)))
    except asyncio.TimeoutError:
        await ai_chat_handler.finish(reply_msg(event, "获取模型列表超时，请稍后再试"))
    except FinishedException:
        raise
    except Exception as e:
        await ai_chat_handler.finish(reply_msg(event, f"获取模型列表失败：{str(e)[:200]}"))


# === 群管理员AI配置命令 ===

@ai_toggle.handle()
async def handle_ai_toggle(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        status = "已开启" if config.get("enabled", False) else "已关闭"
        await ai_toggle.finish(reply_msg(event, f"当前群AI聊天{status}\n用法: ai开关 开/关"))

    if arg in ("开", "开启", "on", "true"):
        config_manager.update_ai_chat_group_config(group_id, {"enabled": True})
        await ai_toggle.finish(reply_msg(event, "AI聊天已开启"))
    elif arg in ("关", "关闭", "off", "false"):
        config_manager.update_ai_chat_group_config(group_id, {"enabled": False})
        await ai_toggle.finish(reply_msg(event, "AI聊天已关闭"))
    else:
        await ai_toggle.finish(reply_msg(event, "参数错误，请输入 开 或 关"))


@ai_list_providers.handle()
async def handle_ai_list_providers(bot: Bot, event: GroupMessageEvent):
    providers = config_manager.get_ai_providers()
    if not providers:
        await ai_list_providers.finish(reply_msg(event, "暂无可用供应商，请在WebUI中添加"))

    lines = ["可用AI供应商："]
    for name, data in providers.items():
        status = "已启用" if data.get("enabled", True) else "已禁用"
        default_model = data.get("default_model", "未设置")
        lines.append(f"  {name} - {status} - 默认模型: {default_model}")

    await ai_list_providers.finish(reply_msg(event, "\n".join(lines)))


@ai_set_provider.handle()
async def handle_ai_set_provider(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    provider_name = args.extract_plain_text().strip()

    if not provider_name:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("provider", "未设置")
        await ai_set_provider.finish(reply_msg(event, f"当前供应商: {current}\n用法: ai供应商 供应商名称\n发送 ai供应商列表 查看所有供应商"))

    providers = config_manager.get_ai_providers()
    if provider_name not in providers:
        await ai_set_provider.finish(reply_msg(event, f"供应商 {provider_name} 不存在，发送 ai供应商列表 查看可用供应商"))

    if not providers[provider_name].get("enabled", True):
        await ai_set_provider.finish(reply_msg(event, f"供应商 {provider_name} 已禁用"))

    config_manager.update_ai_chat_group_config(group_id, {"provider": provider_name})
    await ai_set_provider.finish(reply_msg(event, f"已设置AI供应商为: {provider_name}"))


@ai_set_model.handle()
async def handle_ai_set_model(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    model_name = args.extract_plain_text().strip()

    if not model_name:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("model", "") or "使用供应商默认"
        provider_name = config.get("provider", "未设置")
        await ai_set_model.finish(reply_msg(event, f"当前供应商: {provider_name}\n当前模型: {current}\n用法: ai模型 模型名称\n发送 ai拉取模型 获取可用模型列表"))

    config_manager.update_ai_chat_group_config(group_id, {"model": model_name})
    await ai_set_model.finish(reply_msg(event, f"已设置AI模型为: {model_name}"))


@ai_set_prompt.handle()
async def handle_ai_set_prompt(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    prompt = args.extract_plain_text().strip()

    if not prompt:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("system_prompt", "你是一个友好的AI助手")
        await ai_set_prompt.finish(reply_msg(event, f"当前系统提示词: {current}\n用法: ai提示词 你是一个猫娘助手"))

    config_manager.update_ai_chat_group_config(group_id, {"system_prompt": prompt})
    await ai_set_prompt.finish(reply_msg(event, f"已设置系统提示词为: {prompt}"))


@ai_set_temp.handle()
async def handle_ai_set_temp(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("temperature", 0.7)
        await ai_set_temp.finish(reply_msg(event, f"当前温度: {current}\n用法: ai温度 0.7\n范围: 0~2，越高回复越随机"))

    try:
        temp = float(arg)
        if temp < 0 or temp > 2:
            await ai_set_temp.finish(reply_msg(event, "温度范围: 0~2"))
    except ValueError:
        await ai_set_temp.finish(reply_msg(event, "请输入有效数字，如 0.7"))

    config_manager.update_ai_chat_group_config(group_id, {"temperature": temp})
    await ai_set_temp.finish(reply_msg(event, f"已设置温度为: {temp}"))


@ai_set_tokens.handle()
async def handle_ai_set_tokens(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("max_tokens", 2048)
        await ai_set_tokens.finish(reply_msg(event, f"当前最大Token: {current}\n用法: ai长度 2048\n范围: 256~32768"))

    try:
        tokens = int(arg)
        if tokens < 256 or tokens > 32768:
            await ai_set_tokens.finish(reply_msg(event, "Token范围: 256~32768"))
    except ValueError:
        await ai_set_tokens.finish(reply_msg(event, "请输入有效整数，如 2048"))

    config_manager.update_ai_chat_group_config(group_id, {"max_tokens": tokens})
    await ai_set_tokens.finish(reply_msg(event, f"已设置最大Token为: {tokens}"))


@ai_set_context.handle()
async def handle_ai_set_context(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("max_context", 10)
        await ai_set_context.finish(reply_msg(event, f"当前最大上下文: {current}条\n用法: ai上下文 10\n范围: 0~50，0为不保留上下文"))

    try:
        ctx = int(arg)
        if ctx < 0 or ctx > 50:
            await ai_set_context.finish(reply_msg(event, "上下文范围: 0~50"))
    except ValueError:
        await ai_set_context.finish(reply_msg(event, "请输入有效整数，如 10"))

    config_manager.update_ai_chat_group_config(group_id, {"max_context": ctx})
    await ai_set_context.finish(reply_msg(event, f"已设置最大上下文为: {ctx}条"))


@ai_show_config.handle()
async def handle_ai_show_config(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config = config_manager.get_ai_chat_group_config(group_id)
    providers = config_manager.get_ai_providers()
    provider_name = config.get("provider", "")

    provider_info = ""
    if provider_name and provider_name in providers:
        p = providers[provider_name]
        provider_info = f"  供应商状态: {'启用' if p.get('enabled', True) else '禁用'}\n  API地址: {p.get('api_base', '')}"

    lines = [
        f"AI聊天配置 (群{group_id}):",
        f"  状态: {'开启' if config.get('enabled', False) else '关闭'}",
        f"  供应商: {provider_name or '未设置'}",
        provider_info,
        f"  模型: {config.get('model', '') or '使用供应商默认'}",
        f"  触发方式: @机器人",
        f"  主动回复: {'开启' if config.get('proactive_reply', False) else '关闭'} (概率: {config.get('proactive_reply_probability', 0.1)})",
        f"  系统提示词: {config.get('system_prompt', '你是一个友好的AI助手')}",
        f"  温度: {config.get('temperature', 0.7)}",
        f"  最大Token: {config.get('max_tokens', 2048)}",
        f"  最大上下文: {config.get('max_context', 10)}条",
        "",
        "配置命令:",
        "  ai开关 开/关 | ai供应商 名称 | ai模型 名称",
        "  ai提示词 内容 | ai温度 0~2 | ai长度 256~32768 | ai上下文 0~50",
        "  主动回复 开/关 | 主动回复概率 0~1",
        "  ai供应商列表 | ai拉取模型 | ai配置",
    ]

    await ai_show_config.finish(reply_msg(event, "\n".join(lines)))


@ai_fetch_models.handle()
async def handle_ai_fetch_models(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    config = config_manager.get_ai_chat_group_config(group_id)
    provider_name = config.get("provider", "")
    providers = config_manager.get_ai_providers()

    if not provider_name or provider_name not in providers:
        await ai_fetch_models.finish(reply_msg(event, "未设置供应商，请先使用 ai供应商 名称 设置"))

    provider = providers[provider_name]
    api_base = provider.get("api_base", "")
    api_key = provider.get("api_key", "")
    api_format = provider.get("api_format", "openai")

    if not api_base or (api_format != "ollama" and not api_key):
        await ai_fetch_models.finish(reply_msg(event, "供应商配置不完整，请在WebUI中完善"))

    try:
        models = await _fetch_models(api_base, api_key, api_format=api_format)
        if not models:
            await ai_fetch_models.finish(reply_msg(event, "该供应商暂无可用模型"))

        lines = [f"供应商 {provider_name} 可用模型："]
        for i, m in enumerate(models[:30], 1):
            default_model = provider.get("default_model", "")
            current_model = config.get("model", "")
            marker = ""
            if m == default_model:
                marker += " (供应商默认)"
            if m == current_model:
                marker += " (当前使用)"
            lines.append(f"  {i}. {m}{marker}")

        if len(models) > 30:
            lines.append(f"  ...共 {len(models)} 个模型，仅显示前30个")

        lines.append("\n使用 ai模型 模型名称 设置当前群使用的模型")
        await ai_fetch_models.finish(reply_msg(event, "\n".join(lines)))
    except asyncio.TimeoutError:
        await ai_fetch_models.finish(reply_msg(event, "获取模型列表超时，请稍后再试"))
    except Exception as e:
        await ai_fetch_models.finish(reply_msg(event, f"获取模型列表失败：{str(e)[:200]}"))


@ai_proactive_toggle.handle()
async def handle_ai_proactive_toggle(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        status = "已开启" if config.get("proactive_reply", False) else "已关闭"
        prob = config.get("proactive_reply_probability", 0.1)
        await ai_proactive_toggle.finish(reply_msg(event,
            f"主动回复{status}\n当前概率: {prob}\n用法: 主动回复 开/关"))

    if arg in ("开", "开启", "on", "true"):
        config_manager.update_ai_chat_group_config(group_id, {"proactive_reply": True})
        await ai_proactive_toggle.finish(reply_msg(event, "主动回复已开启"))
    elif arg in ("关", "关闭", "off", "false"):
        config_manager.update_ai_chat_group_config(group_id, {"proactive_reply": False})
        await ai_proactive_toggle.finish(reply_msg(event, "主动回复已关闭"))
    else:
        await ai_proactive_toggle.finish(reply_msg(event, "参数错误，请输入 开 或 关"))


@ai_proactive_prob.handle()
async def handle_ai_proactive_prob(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id
    arg = args.extract_plain_text().strip()

    if not arg:
        config = config_manager.get_ai_chat_group_config(group_id)
        current = config.get("proactive_reply_probability", 0.1)
        await ai_proactive_prob.finish(reply_msg(event,
            f"当前主动回复概率: {current}\n用法: 主动回复概率 0.1\n范围: 0~1，0.1表示10%概率主动回复"))

    try:
        prob = float(arg)
        if prob < 0 or prob > 1:
            await ai_proactive_prob.finish(reply_msg(event, "概率范围: 0~1"))
    except ValueError:
        await ai_proactive_prob.finish(reply_msg(event, "请输入有效数字，如 0.1"))

    config_manager.update_ai_chat_group_config(group_id, {"proactive_reply_probability": prob})
    await ai_proactive_prob.finish(reply_msg(event, f"已设置主动回复概率为: {prob}"))


# ==================== 菜单注册 ====================
from core.menu_registry import menu_registry

_GROUP_AI_CHAT_MENU_ITEMS = {
    "ai供应商": "🤖 AI供应商",
    "ai模型": "🤖 AI模型",
    "ai提示词": "🤖 AI提示词",
    "ai开关": "🤖 AI开关",
    "ai温度": "🤖 AI温度",
    "ai长度": "🤖 AI长度",
    "ai上下文": "🤖 AI上下文",
    "ai配置": "🤖 AI配置",
    "ai供应商列表": "🤖 AI供应商列表",
    "ai拉取模型": "🤖 AI拉取模型",
    "主动回复": "🤖 主动回复",
    "主动回复概率": "🤖 主动回复概率",
}

for _item_name, _text in _GROUP_AI_CHAT_MENU_ITEMS.items():
    menu_registry.register(
        category="AI对话",
        item_name=_item_name,
        text=_text,
        category_title="🤖◇━AI对话━◇🤖",
        category_trigger="AI对话",
        category_description="AI供应商·模型·提示词·开关·配置",
    )
