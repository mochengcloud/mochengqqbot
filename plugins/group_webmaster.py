import asyncio
import base64
import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from typing import Any, Dict, Optional

import aiohttp
from core import on_command, FinishedException, CommandArg, SUPERUSER, GROUP_ADMIN, GROUP_OWNER
from core.menu_registry import menu_registry
from core.onebot import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)

from config_manager import config_manager
from log_manager import log_manager
from plugins.utils import reply_msg


# ============ SSL上下文（跳过证书验证，懒加载） ============
_ssl_ctx = None

def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = ssl.CERT_NONE
    return _ssl_ctx


def _check_enabled(group_id: int) -> tuple:
    """返回 (通过, 提示消息)"""
    if not config_manager.is_group_enabled(group_id):
        return False, ""
    if not config_manager.is_feature_authorized(group_id, "站长工具"):
        return False, ""
    webmaster_config = config_manager.get_webmaster_config(group_id)
    if not webmaster_config.get("enabled", False):
        return False, "⚠️ 站长工具未开启，管理员请使用「开启站长工具」"
    return True, ""


def _check_base(group_id: int) -> bool:
    """仅检查群开关和授权"""
    if not config_manager.is_group_enabled(group_id):
        return False
    if not config_manager.is_feature_authorized(group_id, "站长工具"):
        return False
    return True


def _extract_domain(text: str) -> Optional[str]:
    """从文本中提取域名"""
    text = text.strip()
    text = re.sub(r'^https?://', '', text)
    text = text.split('/')[0]
    text = text.split(':')[0]
    if re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$', text):
        return text
    return None


# ============ 开启/关闭站长工具 ============
enable_webmaster = on_command("开启站长工具", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)
disable_webmaster = on_command("关闭站长工具", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)


@enable_webmaster.handle()
async def handle_enable_webmaster(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_webmaster_enabled(group_id, True)
    await enable_webmaster.finish(reply_msg(event, "✅ 站长工具已开启"))


@disable_webmaster.handle()
async def handle_disable_webmaster(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    if not _check_base(group_id):
        return
    config_manager.set_webmaster_enabled(group_id, False)
    await disable_webmaster.finish(reply_msg(event, "❌ 站长工具已关闭"))


# ============ 收录查询 ============
query_index = on_command("收录查询", priority=1, block=True)


@query_index.handle()
async def handle_query_index(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await query_index.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await query_index.finish(reply_msg(event, "格式：收录查询 域名\n例如：收录查询 baidu.com"))

    domain = _extract_domain(text)
    if not domain:
        await query_index.finish(reply_msg(event, "❌ 域名格式错误，请输入正确的域名\n例如：baidu.com"))

    await query_index.send(reply_msg(event, f"🔍 正在查询 {domain} 的收录情况..."))

    baidu_count = "暂不可用"
    bing_count = "暂不可用"

    try:
        connector = aiohttp.TCPConnector(ssl=_get_ssl_ctx())
        async with aiohttp.ClientSession(connector=connector) as session:
            # 百度收录 - apihz.cn
            try:
                api_url = f"https://cn.apihz.cn/api/wangzhan/baidurank.php?id=88888888&key=88888888&domain={domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get("code") == 200 and data.get("baidu"):
                            baidu_count = str(data["baidu"])
                        elif data.get("code") == 200:
                            baidu_count = "0"
            except Exception:
                pass

            # 必应收录 - 尝试api.99zc.com
            try:
                bing_api = f"http://api.99zc.com/api/bing?domain={domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(bing_api, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get("code") == 200 and data.get("data"):
                            bing_data = data["data"]
                            if isinstance(bing_data, dict):
                                bing_count = str(bing_data.get("count", bing_data.get("bing", "暂不可用")))
                            else:
                                bing_count = str(bing_data)
            except Exception:
                pass

        await query_index.finish(
            reply_msg(event,
            f"📋 收录查询结果\n"
            f"━━━━━━━━━━━━━\n"
            f"🌐 域名：{domain}\n"
            f"🔍 百度收录：约 {baidu_count} 条\n"
            f"🔍 必应收录：约 {bing_count} 条\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 数据仅供参考，实际以搜索引擎为准"
            )
        )
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"Index query error for {domain}: {e}")
        await query_index.finish(reply_msg(event, "❌ 查询失败，请稍后重试"))


# ============ 备案查询 ============
query_icp = on_command("备案查询", priority=1, block=True)


@query_icp.handle()
async def handle_query_icp(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await query_icp.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await query_icp.finish(reply_msg(event, "格式：备案查询 域名\n例如：备案查询 baidu.com"))

    domain = _extract_domain(text)
    if not domain:
        await query_icp.finish(reply_msg(event, "❌ 域名格式错误，请输入正确的域名\n例如：baidu.com"))

    await query_icp.send(reply_msg(event, f"🔍 正在查询 {domain} 的备案信息..."))

    try:
        connector = aiohttp.TCPConnector(ssl=_get_ssl_ctx())
        async with aiohttp.ClientSession(connector=connector) as session:
            icp_no = "未查到"
            company = "未查到"
            nature = "未查到"
            approve_date = "未查到"

            # 主API：apihz.cn
            try:
                api_url = f"https://cn.apihz.cn/api/wangzhan/icp.php?id=88888888&key=88888888&domain={domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get("code") == 200:
                            icp_no = data.get("icp", "未查到")
                            company = data.get("unit", "未查到")
                            nature = data.get("type", "未查到")
                            approve_date = data.get("time", "未查到")
            except Exception:
                pass

            # 备用API：api.99zc.com（WHOIS接口中包含ICP信息）
            if icp_no == "未查到":
                try:
                    backup_url = f"http://api.99zc.com/api/whois?domain={domain}"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(backup_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if data.get("code") == 200 and data.get("data"):
                                d = data["data"]
                                if d.get("icpcode"):
                                    icp_no = d["icpcode"]
                                if d.get("unitname"):
                                    company = d["unitname"]
                except Exception:
                    pass

            await query_icp.finish(
                reply_msg(event,
                f"📋 备案查询结果\n"
                f"━━━━━━━━━━━━━\n"
                f"🌐 域名：{domain}\n"
                f"📄 ICP备案号：{icp_no}\n"
                f"🏢 主办单位：{company}\n"
                f"📌 单位性质：{nature}\n"
                f"📅 审核时间：{approve_date}\n"
                f"━━━━━━━━━━━━━"
                )
            )
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"ICP query error for {domain}: {e}")
        await query_icp.finish(reply_msg(event, "❌ 查询失败，请稍后重试"))


# ============ WHOIS查询 ============
query_whois = on_command("whois查询", priority=1, block=True)


@query_whois.handle()
async def handle_query_whois(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await query_whois.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await query_whois.finish(reply_msg(event, "格式：whois查询 域名\n例如：whois查询 baidu.com"))

    domain = _extract_domain(text)
    if not domain:
        await query_whois.finish(reply_msg(event, "❌ 域名格式错误，请输入正确的域名\n例如：baidu.com"))

    await query_whois.send(reply_msg(event, f"🔍 正在查询 {domain} 的WHOIS信息..."))

    try:
        connector = aiohttp.TCPConnector(ssl=_get_ssl_ctx())
        async with aiohttp.ClientSession(connector=connector) as session:
            registrar = "未知"
            created = "未知"
            expires = "未知"
            updated = "未知"
            status_text = "未知"
            ns_text = "   未知"

            # 主API：meine-ip.info
            try:
                api_url = f"https://meine-ip.info/api/whois/{domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        parsed = data.get("parsed", {})
                        if parsed:
                            registrar = parsed.get("registrar", "未知")
                            created = parsed.get("created", "未知")
                            expires = parsed.get("expires", "未知")
                            updated = parsed.get("updated", "未知")

                            statuses = parsed.get("status", [])
                            if isinstance(statuses, list) and statuses:
                                status_text = ", ".join(statuses[:3])
                            elif statuses:
                                status_text = str(statuses)

                            nameservers = parsed.get("nameservers", [])
                            if isinstance(nameservers, list) and nameservers:
                                ns_text = "\n".join([f"   📡 {ns}" for ns in nameservers[:4]])
                            elif nameservers:
                                ns_text = f"   📡 {nameservers}"
            except Exception:
                pass

            # 备用API：api.99zc.com
            if registrar == "未知":
                try:
                    backup_url = f"http://api.99zc.com/api/whois?domain={domain}"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(backup_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if data.get("code") == 200 and data.get("data"):
                                d = data["data"]
                                registrar = d.get("business", "未知")
                                created = d.get("regtime", "未知")
                                expires = d.get("expirationtime", "未知")
                                updated = d.get("updatetime", "未知")
                                status_text = d.get("state", "未知")
                                dns = d.get("dnsserver", "")
                                if dns:
                                    ns_list = dns.split()
                                    ns_text = "\n".join([f"   📡 {ns}" for ns in ns_list[:4]])
                except Exception:
                    pass

            await query_whois.finish(
                reply_msg(event,
                f"📋 WHOIS查询结果\n"
                f"━━━━━━━━━━━━━\n"
                f"🌐 域名：{domain}\n"
                f"🏢 注册商：{registrar}\n"
                f"📅 注册时间：{created}\n"
                f"📅 到期时间：{expires}\n"
                f"📅 更新时间：{updated}\n"
                f"📌 域名状态：{status_text}\n"
                f"📡 DNS服务器：\n{ns_text}\n"
                f"━━━━━━━━━━━━━"
                )
            )
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"WHOIS query error for {domain}: {e}")
        await query_whois.finish(reply_msg(event, "❌ 查询失败，请稍后重试"))


# ============ 域名防红 ============
query_antiblock = on_command("域名防红", priority=1, block=True)


@query_antiblock.handle()
async def handle_query_antiblock(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await query_antiblock.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await query_antiblock.finish(reply_msg(event, "格式：域名防红 域名\n例如：域名防红 baidu.com"))

    domain = _extract_domain(text)
    if not domain:
        await query_antiblock.finish(reply_msg(event, "❌ 域名格式错误，请输入正确的域名\n例如：baidu.com"))

    await query_antiblock.send(reply_msg(event, f"🔍 正在检测 {domain} 的防红状态..."))

    qq_status = "检测失败"
    qq_desc = ""
    wx_status = "检测失败"
    wx_desc = ""

    try:
        connector = aiohttp.TCPConnector(ssl=_get_ssl_ctx())
        async with aiohttp.ClientSession(connector=connector) as session:
            # QQ拦截检测 - tmini.net
            try:
                qq_url = f"https://tmini.net/api/detailed?url={domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(qq_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get("status") == "safe":
                            qq_status = "✅ 安全"
                            qq_desc = data.get("data", {}).get("desc", "")
                        elif data.get("status") == "blocked":
                            qq_status = "❌ 被拦截"
                            qq_desc = data.get("data", {}).get("title", "")
                        else:
                            qq_status = "⚠️ 未知"
                    else:
                        qq_status = f"HTTP {resp.status}"
            except asyncio.TimeoutError:
                qq_status = "检测超时"
            except Exception:
                qq_status = "检测失败"

            # 微信拦截检测 - tmini.net
            try:
                wx_url = f"https://tmini.net/api/wechaturl?url={domain}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(wx_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        wx_code = data.get("code")
                        if wx_code == 0:
                            wx_status = "✅ 安全"
                            wx_desc = data.get("msg", "")
                        elif wx_code == -3:
                            wx_status = "❌ 被拦截"
                            wx_desc = data.get("msg", "")
                        else:
                            wx_status = f"⚠️ 未知({wx_code})"
                            wx_desc = data.get("msg", "")
                    else:
                        wx_status = f"HTTP {resp.status}"
            except asyncio.TimeoutError:
                wx_status = "检测超时"
            except Exception:
                wx_status = "检测失败"

        overall = "🟢 安全" if "安全" in qq_status and "安全" in wx_status else "🔴 存在拦截"
        qq_desc_text = f"\n   💬 {qq_desc}" if qq_desc else ""
        wx_desc_text = f"\n   💬 {wx_desc}" if wx_desc else ""

        await query_antiblock.finish(
            reply_msg(event,
            f"🛡️ 域名防红检测\n"
            f"━━━━━━━━━━━━━\n"
            f"🌐 域名：{domain}\n"
            f"📊 综合状态：{overall}\n"
            f"QQ：{qq_status}{qq_desc_text}\n"
            f"微信：{wx_status}{wx_desc_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 检测结果仅供参考"
            )
        )
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"Antiblock query error for {domain}: {e}")
        await query_antiblock.finish(reply_msg(event, "❌ 检测失败，请稍后重试"))


# ============ Ping ============
ping_cmd = on_command("ping", priority=1, block=True)


@ping_cmd.handle()
async def handle_ping(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await ping_cmd.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await ping_cmd.finish(reply_msg(event, "格式：ping 域名\n例如：ping baidu.com"))

    domain = _extract_domain(text)
    if not domain:
        await ping_cmd.finish(reply_msg(event, "❌ 域名格式错误，请输入正确的域名\n例如：baidu.com"))

    await ping_cmd.send(reply_msg(event, f"🔍 正在 Ping {domain} ..."))

    try:
        # 解析域名获取IP
        try:
            addr_info = await asyncio.get_event_loop().getaddrinfo(domain, None)
            ip = addr_info[0][4][0] if addr_info else None
        except socket.gaierror:
            ip = None
        except Exception:
            ip = None

        if not ip:
            await ping_cmd.finish(reply_msg(event, f"❌ 无法解析域名 {domain}"))

        # 使用TCP连接模拟ping（测量延迟）
        ping_results = []
        for i in range(4):
            try:
                start = time.time()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, 80),
                    timeout=5
                )
                end = time.time()
                delay = (end - start) * 1000  # 转换为毫秒
                ping_results.append(delay)
                writer.close()
            except asyncio.TimeoutError:
                ping_results.append(None)
            except ConnectionRefusedError:
                # 连接被拒绝但说明主机可达
                ping_results.append(0.1)
            except OSError:
                ping_results.append(None)
            if i < 3:
                await asyncio.sleep(0.5)

        lines = [f"📡 Ping {domain} ({ip})"]
        lines.append("━━━━━━━━━━━━━")

        for i, result in enumerate(ping_results, 1):
            if result is not None:
                lines.append(f"  回复 {i}：时间={result:.0f}ms")
            else:
                lines.append(f"  回复 {i}：超时")

        valid = [r for r in ping_results if r is not None]
        if valid:
            min_delay = min(valid)
            max_delay = max(valid)
            avg_delay = sum(valid) / len(valid)
            lost = 4 - len(valid)
            loss_rate = (lost / 4) * 100
            lines.append("━━━━━━━━━━━━━")
            lines.append(f"📊 最小={min_delay:.0f}ms 最大={max_delay:.0f}ms 平均={avg_delay:.0f}ms")
            lines.append(f"📉 丢包率={loss_rate:.0f}% ({lost}/4)")
        else:
            lines.append("━━━━━━━━━━━━━")
            lines.append("❌ 全部超时，无法连接")

        await ping_cmd.finish(reply_msg(event, "\n".join(lines)))
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"Ping error for {domain}: {e}")
        await ping_cmd.finish(reply_msg(event, "❌ Ping失败，请稍后重试"))


# ============ 网页截图 ============
screenshot_cmd = on_command("网页截图", priority=1, block=True)


def _find_chrome() -> Optional[str]:
    """查找本地Chrome或Edge浏览器路径"""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    # 尝试 PATH 中查找
    for name in ["chrome", "msedge"]:
        found = shutil.which(name)
        if found:
            candidates.insert(0, found)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _build_screenshot_url(text: str) -> Optional[str]:
    """从用户输入构建完整URL，返回None表示输入无效"""
    text = text.strip()
    if not text:
        return None
    # 已经是完整URL
    if text.startswith("http://") or text.startswith("https://"):
        return text
    # 纯域名，补 https://
    domain = _extract_domain(text)
    if domain:
        return f"https://{domain}"
    return None


@screenshot_cmd.handle()
async def handle_screenshot(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = event.group_id

    ok, msg = _check_enabled(group_id)
    if not ok:
        if msg:
            await screenshot_cmd.finish(reply_msg(event, msg))
        return

    text = args.extract_plain_text().strip()
    if not text:
        await screenshot_cmd.finish(reply_msg(event, "格式：网页截图 网址\n例如：网页截图 baidu.com\n例如：网页截图 https://www.baidu.com"))

    url = _build_screenshot_url(text)
    if not url:
        await screenshot_cmd.finish(reply_msg(event, "❌ 网址格式错误，请输入正确的域名或网址\n例如：baidu.com 或 https://www.baidu.com"))

    # 查找浏览器
    chrome_path = _find_chrome()
    if not chrome_path:
        await screenshot_cmd.finish(reply_msg(event, "❌ 未检测到Chrome或Edge浏览器，无法截图"))

    await screenshot_cmd.send(reply_msg(event, f"📸 正在截取 {text} 的网页截图..."))

    try:
        # 使用临时文件保存截图
        tmp_dir = tempfile.gettempdir()
        screenshot_path = os.path.join(tmp_dir, f"webshot_{event.group_id}_{int(time.time())}.png")
        # 独立的用户数据目录,避免 Chrome 已运行时复用实例导致截图失败
        profile_dir = os.path.join(tmp_dir, "chrome_screenshot_profile")

        cmd = [
            chrome_path,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-software-rasterizer",
            f"--user-data-dir={profile_dir}",
            "--disable-extensions",
            "--mute-audio",
            "--hide-scrollbars",
            f"--screenshot={screenshot_path}",
            "--window-size=1280,800",
            url,
        ]

        # Windows 下 SelectorEventLoop 不支持 asyncio 子进程,改用 subprocess.run 在线程中执行
        def _run_chrome():
            return subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        try:
            proc = await asyncio.to_thread(_run_chrome)
        except subprocess.TimeoutExpired:
            await screenshot_cmd.finish(reply_msg(event, "❌ 截图超时，网页可能加载过慢"))

        # 读取截图文件
        if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) < 1000:
            # 清理可能存在的空文件
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            # 捕获 stderr 用于调试
            stderr_msg = ""
            if proc.stderr:
                stderr_msg = proc.stderr.decode("utf-8", errors="ignore")[:200]
            if stderr_msg:
                log_manager.log_notice("webmaster", f"Screenshot failed for {url}: {stderr_msg}")
            await screenshot_cmd.finish(reply_msg(event, "❌ 截图失败，请检查网址是否可访问"))

        # 读取截图文件为 base64,使用 base64:// 协议发送(OneBot 标准协议,兼容性最好)
        try:
            with open(screenshot_path, "rb") as f:
                img_data = f.read()
            img_b64 = base64.b64encode(img_data).decode("ascii")
        finally:
            # 无论后续是否成功,先清理临时文件(base64 数据已在内存中)
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

        msg = MessageSegment.image(f"base64://{img_b64}")
        await screenshot_cmd.finish(reply_msg(event, msg))
    except FinishedException:
        raise
    except Exception as e:
        log_manager.log_notice("webmaster", f"Screenshot error for {url}: {type(e).__name__}: {e!r}")
        await screenshot_cmd.finish(reply_msg(event, f"❌ 截图失败：{type(e).__name__}: {e!r}"))


# ============ 注册菜单 ============
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 站长工具(无子分类)
_WEBMASTER_MENU_ITEMS = {
    "收录查询": "🌟收录查询*",
    "备案查询": "🌟备案查询*",
    "whois查询": "🌟whois查询*",
    "域名防红": "🌟域名防红*",
    "ping": "🌟ping*",
    "网页截图": "🌟网页截图*",
    "开启站长工具": "🌟开启站长工具",
    "关闭站长工具": "🌟关闭站长工具",
}

for _item_name, _text in _WEBMASTER_MENU_ITEMS.items():
    menu_registry.register(
        category="站长工具",
        item_name=_item_name,
        text=_text,
        category_title="🌱◇━站长工具━◇🌱",
        category_trigger="站长工具",
        category_description="收录·备案·WHOIS·防红·Ping·截图",
    )
