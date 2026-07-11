import aiohttp
import asyncio
import json as json_module

from core import on_message, FinishedException
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg

custom_api_handler = on_message(priority=5, block=False)


def _extract_json_value(data: dict, path: str):
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


@custom_api_handler.handle()
async def handle_custom_api(bot: Bot, event: GroupMessageEvent):
    custom_api_config = config_manager.get_custom_api_config()
    if not custom_api_config.get("enabled", True):
        return

    group_id = event.group_id
    if not config_manager.is_group_enabled(group_id):
        return

    if not config_manager.is_feature_authorized(group_id, "自定义API"):
        return

    raw_message = event.raw_message.strip()
    if not raw_message:
        return

    apis = custom_api_config.get("apis", {})
    matched_api = None
    user_input = ""

    for name, api_config in apis.items():
        if not api_config.get("enabled", True):
            continue
        trigger = api_config.get("trigger", "")
        if not trigger:
            continue
        if raw_message == trigger:
            if "*" in api_config.get("url", ""):
                await custom_api_handler.finish(reply_msg(event, f"⚠️ 请输入参数，例如：{trigger} 内容"))
            matched_api = api_config
            user_input = ""
            break
        elif raw_message.startswith(trigger + " ") or raw_message.startswith(trigger):
            after_trigger = raw_message[len(trigger):].strip()
            if after_trigger or "*" not in api_config.get("url", ""):
                matched_api = api_config
                user_input = after_trigger
                break

    if matched_api is None:
        return

    url = matched_api.get("url", "")
    method = matched_api.get("method", "GET").upper()
    response_type = matched_api.get("response_type", "text")
    json_path = matched_api.get("json_path", "")
    timeout = matched_api.get("timeout", 10)
    headers = matched_api.get("headers", {})

    if "*" in url:
        if not user_input:
            await custom_api_handler.finish(reply_msg(event, f"⚠️ 请输入参数，例如：{matched_api['trigger']} 内容"))
        url = url.replace("*", user_input)

    log_manager.log_command(f"自定义API调用: {matched_api.get('trigger')} -> {url}")

    try:
        async with aiohttp.ClientSession() as session:
            request_headers = {}
            if headers:
                request_headers.update(headers)

            if method == "POST":
                async with session.post(url, headers=request_headers,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        await custom_api_handler.finish(reply_msg(event, f"❌ API请求失败，状态码：{resp.status}"))
                    content_type = resp.content_type or ""
                    body = await resp.read()
            else:
                async with session.get(url, headers=request_headers,
                                       timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        await custom_api_handler.finish(reply_msg(event, f"❌ API请求失败，状态码：{resp.status}"))
                    content_type = resp.content_type or ""
                    body = await resp.read()

    except asyncio.TimeoutError:
        await custom_api_handler.finish(reply_msg(event, "❌ API请求超时，请稍后再试"))
    except aiohttp.ClientError as e:
        await custom_api_handler.finish(reply_msg(event, f"❌ API请求出错：{str(e)}"))
    except FinishedException:
        raise
    except Exception as e:
        await custom_api_handler.finish(reply_msg(event, f"❌ 请求异常：{str(e)}"))

    if response_type == "image":
        if content_type.startswith("image/"):
            import base64
            b64_data = base64.b64encode(body).decode("utf-8")
            ext = content_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"
            msg = MessageSegment.image(f"base64://{b64_data}")
            await custom_api_handler.finish(reply_msg(event, msg))
        else:
            text = body.decode("utf-8", errors="replace")
            if text.startswith("http"):
                msg = MessageSegment.image(text)
                await custom_api_handler.finish(reply_msg(event, msg))
            else:
                try:
                    json_data = json_module.loads(text)
                    if json_path:
                        result = _extract_json_value(json_data, json_path)
                        if result:
                            if str(result).startswith("http"):
                                msg = MessageSegment.image(str(result))
                                await custom_api_handler.finish(reply_msg(event, msg))
                            else:
                                await custom_api_handler.finish(reply_msg(event, str(result)))
                        else:
                            await custom_api_handler.finish(reply_msg(event, f"❌ 未找到指定字段：{json_path}"))
                    else:
                        await custom_api_handler.finish(reply_msg(event, text[:2000]))
                except json_module.JSONDecodeError:
                    await custom_api_handler.finish(reply_msg(event, text[:2000]))

    elif response_type == "json":
        text = body.decode("utf-8", errors="replace")
        try:
            json_data = json_module.loads(text)
            if json_path:
                result = _extract_json_value(json_data, json_path)
                if result is not None:
                    if isinstance(result, (dict, list)):
                        await custom_api_handler.finish(reply_msg(event, json_module.dumps(result, ensure_ascii=False, indent=2)[:2000]))
                    else:
                        await custom_api_handler.finish(reply_msg(event, str(result)))
                else:
                    await custom_api_handler.finish(reply_msg(event, f"❌ 未找到指定字段：{json_path}"))
            else:
                await custom_api_handler.finish(reply_msg(event, json_module.dumps(json_data, ensure_ascii=False, indent=2)[:2000]))
        except json_module.JSONDecodeError:
            await custom_api_handler.finish(reply_msg(event, text[:2000]))

    else:
        text = body.decode("utf-8", errors="replace")
        await custom_api_handler.finish(reply_msg(event, text[:2000] if text else "❌ API返回内容为空"))
