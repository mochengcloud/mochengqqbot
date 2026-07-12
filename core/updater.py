"""版本检测与在线更新核心模块。

提供版本对比、在线检查更新、下载更新包、执行更新(含备份与回滚)以及重启框架等能力,
是陌城qqbot框架自动更新功能的底层实现。

主要功能:
    - 全局更新状态管理(供 WebUI / 命令行查询进度)
    - 版本号对比 compare_versions
    - 异步 / 同步检查更新 check_update / check_update_sync
    - 流式下载更新包 download_update
    - 执行更新 perform_update(解压 -> 备份 -> 覆盖 -> 清理,失败自动回滚)
    - 回滚 rollback_update
    - 重启框架 trigger_restart
"""

import os
import sys
import json
import shutil
import tempfile
import logging
import urllib.request
import urllib.error
import zipfile
from typing import Optional, Callable, Dict, Any, Tuple, List

# 框架根目录: core/ 的上一级
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

# 默认更新配置
DEFAULT_UPDATE_CONFIG = {
    "api_url": "https://bot.mcyvps.top/api/latest-version.php",
    "channel": "beta",
    "auto_check": True
}


# ============ 全局更新状态管理 ============

_update_status = {
    "status": "idle",      # idle/checking/downloading/extracting/backup/overwriting/restarting/error/done
    "progress": 0,         # 0-100
    "message": ""
}


def get_update_status() -> dict:
    """获取当前更新状态。

    返回字典的引用,调用方应只读使用。包含字段:
        status:   idle/checking/downloading/extracting/backup/overwriting/restarting/error/done
        progress: 0-100
        message:  人类可读的描述
    """
    return _update_status


def _set_status(status: str, progress: int, message: str):
    """设置当前更新状态并记录日志。"""
    _update_status["status"] = status
    _update_status["progress"] = progress
    _update_status["message"] = message
    logger.info("[更新] %s (%d%%) - %s", status, progress, message)


# ============ 版本对比 ============

def _parse_version(version: str) -> Tuple[int, int, int, int]:
    """解析版本号为 (major, minor, patch, is_official) 元组。

    仅提取数字部分和是否正式版,忽略 v 前缀。
    is_official: 1=正式版, 0=测试版(beta),约定 beta < 同版本号正式版。

    兼容以下格式:
        "v2.0.1-beta" / "2.0.1-beta" / "v2.0.1" / "2.0.1"
    """
    if not version:
        return (0, 0, 0, 1)
    v = version.strip()
    # 去除可能的 "v" / "V" 前缀
    if v and v[0] in ("v", "V"):
        v = v[1:]
    # 检测是否含 beta 后缀
    is_official = 1  # 默认正式版
    lower = v.lower()
    if "-beta" in lower:
        is_official = 0
        v = v[:lower.index("-beta")]
    elif lower.endswith("beta"):
        is_official = 0
        v = v[:len(v) - len("beta")]
    # 解析主版本号 major.minor.patch
    parts = v.split(".")
    nums: List[int] = []
    for p in parts:
        p = p.strip()
        if p.isdigit():
            nums.append(int(p))
        else:
            # 对非纯数字段,提取前导数字部分
            num_str = ""
            for ch in p:
                if ch.isdigit():
                    num_str += ch
                else:
                    break
            nums.append(int(num_str) if num_str else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], is_official)


def compare_versions(current: str, latest: str, latest_type: Optional[str] = None) -> int:
    """对比两个版本号(数字部分 + 正式版/测试版类型)。

    参数:
        current: 当前版本号,如 "v2.0.1-beta"
        latest:  最新版本号,如 "v2.0.2-beta" 或 "2.0.1" 或 "2.0.1-beta"
        latest_type: API 返回的 type 字段("Official"/"beta"),为 None 时从 latest 字符串推断

    返回:
         1  表示 latest > current(有更新)
         0  表示相等(数字相同且类型相同)
        -1  表示 latest < current
    """
    cur = _parse_version(current)
    nxt = _parse_version(latest)
    # 若显式传入 latest_type,以此为准(优先于字符串推断)
    if latest_type:
        lt = latest_type.lower()
        if lt == "official":
            nxt = (nxt[0], nxt[1], nxt[2], 1)
        elif lt == "beta":
            nxt = (nxt[0], nxt[1], nxt[2], 0)
    if nxt > cur:
        return 1
    elif nxt == cur:
        return 0
    else:
        return -1


# ============ 配置读取(避免循环依赖) ============

def _get_update_config() -> dict:
    """读取 update 配置。

    优先从 config_manager 读取,失败则使用 DEFAULT_UPDATE_CONFIG。
    通过延迟导入避免与 config_manager 产生循环依赖。
    """
    cfg = dict(DEFAULT_UPDATE_CONFIG)
    try:
        # 延迟导入,避免循环依赖
        from config_manager import config_manager
        update_cfg = config_manager.config.get("update", {})
        if isinstance(update_cfg, dict):
            for key in DEFAULT_UPDATE_CONFIG:
                if key in update_cfg:
                    cfg[key] = update_cfg[key]
    except Exception as e:
        logger.debug("[更新] 读取 config_manager 配置失败,使用默认值: %s", e)
    return cfg


def _get_current_version() -> str:
    """获取当前框架版本号,兼容多种导入路径。"""
    try:
        from core.version import __version__
        return __version__
    except Exception:
        try:
            from version import __version__
            return __version__
        except Exception:
            return "v0.0.0"


# ============ 异步检查更新 ============

async def check_update(api_url: Optional[str] = None, channel: Optional[str] = None) -> dict:
    """异步检查更新。

    参数:
        api_url:  官网 API 地址,为 None 时从配置读取
        channel:  更新通道("beta" 或 "Official"),为 None 时从配置读取

    返回:
        {
            "has_update": bool,
            "current": "v2.0.1-beta",
            "latest": {...} or None,
            "error": str or None
        }
    失败时 has_update=False,不抛异常。
    """
    _set_status("checking", 0, "正在检查更新...")
    current_version = _get_current_version()

    cfg = _get_update_config()
    if api_url is None:
        api_url = cfg["api_url"]
    if channel is None:
        channel = cfg["channel"]

    try:
        import aiohttp
    except Exception as e:
        _set_status("error", 0, f"aiohttp 不可用: {e}")
        return {
            "has_update": False,
            "current": current_version,
            "latest": None,
            "error": f"aiohttp 不可用: {e}"
        }

    try:
        url = api_url
        if channel:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}type={channel}"
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _set_status("error", 0, f"服务器返回状态码 {resp.status}")
                    return {
                        "has_update": False,
                        "current": current_version,
                        "latest": None,
                        "error": f"HTTP {resp.status}"
                    }
                data = await resp.json(content_type=None)
    except Exception as e:
        _set_status("error", 0, f"检查更新失败: {e}")
        return {
            "has_update": False,
            "current": current_version,
            "latest": None,
            "error": str(e)
        }

    return _analyze_update_response(data, current_version)


# ============ 同步检查更新 ============

def check_update_sync(api_url: Optional[str] = None, channel: Optional[str] = None) -> dict:
    """同步检查更新,供命令行工具(core/updater_cli.py)使用。

    返回格式同 check_update。
    """
    current_version = _get_current_version()

    cfg = _get_update_config()
    if api_url is None:
        api_url = cfg["api_url"]
    if channel is None:
        channel = cfg["channel"]

    try:
        url = api_url
        if channel:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}type={channel}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "MoCheng-QQBot-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        _set_status("error", 0, f"检查更新失败: {e}")
        return {
            "has_update": False,
            "current": current_version,
            "latest": None,
            "error": str(e)
        }

    return _analyze_update_response(data, current_version)


def _analyze_update_response(data: dict, current_version: str) -> dict:
    """解析 API 响应并判断是否有更新。

    API 返回格式:
        {"code":200,"data":{"version_name":"...","version_number":"2.0.0",
         "download_url":"...","type":"Official","released_at":"..."}}
    无版本时 data 为 null。
    """
    if not isinstance(data, dict) or data.get("code") != 200:
        _set_status("error", 0, "服务器返回异常")
        return {
            "has_update": False,
            "current": current_version,
            "latest": None,
            "error": "服务器返回异常"
        }

    latest = data.get("data")
    if not latest:
        _set_status("idle", 0, "暂无可用版本")
        return {
            "has_update": False,
            "current": current_version,
            "latest": None,
            "error": None
        }

    # 优先使用 version_number,其次回退到 version_name
    latest_version = latest.get("version_number") or latest.get("version_name") or ""
    # API 返回的 type 字段(Official/beta),用于区分正式版/测试版
    latest_type = latest.get("type") or ""

    # 对比数字部分 + 正式版/测试版类型
    cmp_result = compare_versions(current_version, latest_version, latest_type)
    has_update = cmp_result > 0

    msg = f"最新版本 {latest_version}({'有更新' if has_update else '已是最新'})"
    _set_status("idle", 0, msg)
    return {
        "has_update": has_update,
        "current": current_version,
        "latest": latest,
        "error": None
    }


# ============ 下载更新 ============

def download_update(url: str, dest_path: str,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
    """流式下载更新包到 dest_path。

    参数:
        url:               下载地址
        dest_path:         目标文件路径
        progress_callback: 进度回调 (downloaded_bytes, total_bytes),total 为 0 表示未知大小

    下载失败抛异常。
    """
    _set_status("downloading", 0, f"开始下载: {url}")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MoCheng-QQBot-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024  # 64KB
            # 确保目标目录存在
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        try:
                            progress_callback(downloaded, total)
                        except Exception:
                            # 回调失败不影响下载
                            pass
                    if total > 0:
                        pct = min(100, int(downloaded * 100 / total))
                        _set_status("downloading", pct,
                                    f"已下载 {downloaded}/{total} 字节")
        _set_status("downloading", 100, "下载完成")
    except Exception as e:
        _set_status("error", 0, f"下载失败: {e}")
        raise


# ============ 执行更新 ============

# 需要备份的目录(相对 base_dir)
_BACKUP_DIRS = ["core", "plugins"]
# webui 备份时需要排除的子路径(相对 webui/)
_WEBUI_EXCLUDE = ["frontend/node_modules"]
# 需要备份的单个文件(相对 base_dir)
_BACKUP_FILES = [
    "main.py",
    "config_manager.py",
    "log_manager.py",
    "requirements.txt",
    "start.bat",
    "start.sh",
    "更新日志.txt",
]
# 更新覆盖时严格保留(不覆盖)的路径(相对 base_dir)
_PRESERVE_PATHS = ["config", "venv", "webui/frontend/node_modules"]

# 框架内置插件清单(更新时只覆盖这些文件,其他 .py 视为用户自定义插件并保留)
_BUILTIN_PLUGINS = {
    "group_admin", "group_ai_chat", "group_board_games", "group_checkin",
    "group_content_check", "group_essence_stats", "group_fun", "group_games",
    "group_like", "group_newcomer", "group_notify", "group_owner",
    "group_points", "group_schedule", "group_simulation", "group_stats",
    "group_verify", "group_webmaster", "custom_api", "utils",
}


def _normalize_rel(path: str) -> str:
    """将路径规范化为正斜杠形式,便于前缀匹配。"""
    return path.replace("\\", "/")


def _is_under(rel_path: str, prefixes) -> bool:
    """判断 rel_path 是否位于任一前缀目录下或本身即该路径。

    参数使用相对路径(正斜杠分隔)。
    """
    norm = _normalize_rel(rel_path).strip("/")
    for p in prefixes:
        pp = _normalize_rel(p).strip("/")
        if not pp:
            continue
        if norm == pp or norm.startswith(pp + "/"):
            return True
    return False


def _backup_single(base_dir: str, backup_dir: str, rel_path: str) -> None:
    """备份 base_dir/rel_path 到 backup_dir/rel_path(支持文件与目录)。"""
    src = os.path.join(base_dir, rel_path)
    if not os.path.exists(src):
        return
    dst = os.path.join(backup_dir, rel_path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def perform_update(zip_path: str, base_dir: str) -> bool:
    """执行更新流程: 解压 -> 备份 -> 覆盖 -> 清理。

    参数:
        zip_path: 下载好的更新包路径
        base_dir:  框架根目录

    返回:
        True 成功, False 失败(失败时自动调用 rollback_update 回滚)。
    """
    backup_dir = os.path.join(base_dir, ".update_backup")
    temp_dir: Optional[str] = None
    try:
        # 1. 解压到临时目录
        _set_status("extracting", 0, "正在解压更新包...")
        temp_dir = tempfile.mkdtemp(prefix="qqbot_update_")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)
        _set_status("extracting", 100, "解压完成")

        # 定位解压后的根目录(处理 zip 内包含单层顶层目录的情况)
        src_root = temp_dir
        entries = os.listdir(temp_dir)
        if len(entries) == 1:
            only = os.path.join(temp_dir, entries[0])
            if os.path.isdir(only):
                src_root = only

        # 2. 备份当前文件
        _set_status("backup", 0, "正在备份当前文件...")
        # 清理可能残留的旧备份
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        os.makedirs(backup_dir, exist_ok=True)

        # 备份目录: core/、plugins/
        for d in _BACKUP_DIRS:
            _backup_single(base_dir, backup_dir, d)

        # 备份 webui/(排除 frontend/node_modules)
        webui_src = os.path.join(base_dir, "webui")
        if os.path.exists(webui_src):
            webui_dst = os.path.join(backup_dir, "webui")
            for root, dirs, files in os.walk(webui_src):
                rel = _normalize_rel(os.path.relpath(root, webui_src))
                # 过滤子目录: 排除 frontend/node_modules
                dirs[:] = [d for d in dirs if not _is_under(
                    (rel + "/" + d) if rel != "." else d, _WEBUI_EXCLUDE)]
                dst_root = webui_dst if rel == "." else os.path.join(webui_dst, rel)
                os.makedirs(dst_root, exist_ok=True)
                for fn in files:
                    shutil.copy2(os.path.join(root, fn),
                                 os.path.join(dst_root, fn))

        # 备份单个文件
        for f in _BACKUP_FILES:
            _backup_single(base_dir, backup_dir, f)
        _set_status("backup", 100, "备份完成")

        # 3. 用新文件覆盖(严格保留 config/、venv/、webui/frontend/node_modules/)
        _set_status("overwriting", 0, "正在覆盖文件...")
        _overwrite_files(src_root, base_dir)
        _set_status("overwriting", 100, "文件覆盖完成")

        # 4. 清理临时目录和备份(成功后)
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir = None
        shutil.rmtree(backup_dir, ignore_errors=True)

        _set_status("done", 100, "更新完成")
        logger.info("[更新] 更新流程成功完成")
        return True
    except Exception as e:
        logger.exception("[更新] 更新流程失败: %s", e)
        _set_status("error", 0, f"更新失败: {e}")
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        # 自动回滚
        try:
            rollback_update(base_dir)
        except Exception as re:
            logger.exception("[更新] 回滚失败: %s", re)
        return False


def _overwrite_files(src_root: str, base_dir: str) -> None:
    """将 src_root 下的文件覆盖到 base_dir。

    严格保留 _PRESERVE_PATHS 中的路径(不进入、不创建、不覆盖)。
    对于 plugins/ 目录:仅覆盖 _BUILTIN_PLUGINS 清单中的内置插件,
    其他 .py 文件视为用户自定义插件,原样保留(不覆盖、不删除)。
    """
    for root, dirs, files in os.walk(src_root):
        rel = _normalize_rel(os.path.relpath(root, src_root))
        # 若当前目录本身位于保留路径下,跳过且不递归
        if rel != "." and _is_under(rel, _PRESERVE_PATHS):
            dirs[:] = []
            continue
        # 每一层都过滤掉保留路径下的子目录
        dirs[:] = [d for d in dirs if not _is_under(
            (rel + "/" + d) if rel != "." else d, _PRESERVE_PATHS)]

        dst_root = base_dir if rel == "." else os.path.join(base_dir, rel)
        os.makedirs(dst_root, exist_ok=True)
        for fn in files:
            rel_file = (rel + "/" + fn) if rel != "." else fn
            if _is_under(rel_file, _PRESERVE_PATHS):
                continue
            # plugins/ 目录下只覆盖内置插件,保留用户自定义插件
            if rel == "plugins" and fn.endswith(".py"):
                stem = fn[:-3]
                if stem not in _BUILTIN_PLUGINS:
                    # 用户自定义插件:不覆盖
                    continue
            shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))


# ============ 回滚 ============

def rollback_update(base_dir: str) -> None:
    """从 base_dir/.update_backup/ 恢复所有备份的文件/目录。

    若备份目录不存在则记录警告并返回。
    """
    backup_dir = os.path.join(base_dir, ".update_backup")
    if not os.path.exists(backup_dir):
        logger.warning("[更新] 回滚目录不存在: %s", backup_dir)
        return
    _set_status("backup", 0, "正在回滚...")
    # 遍历备份目录,将所有文件恢复到 base_dir 对应位置
    for root, dirs, files in os.walk(backup_dir):
        rel = _normalize_rel(os.path.relpath(root, backup_dir))
        dst_root = base_dir if rel == "." else os.path.join(base_dir, rel)
        os.makedirs(dst_root, exist_ok=True)
        for fn in files:
            shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))
    _set_status("error", 0, "已回滚到更新前状态")
    logger.info("[更新] 回滚完成")


# ============ 重启 ============

def trigger_restart() -> None:
    """通过 os.execv 重启 main.py。

    使用当前 Python 解释器重新执行 sys.argv,此函数不会返回。
    """
    _set_status("restarting", 100, "正在重启框架...")
    logger.info("[更新] 准备重启框架: %s %s", sys.executable, sys.argv)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ============ 测试入口 ============

if __name__ == "__main__":
    # 配置基础日志输出,便于直接运行查看
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    print(f"框架根目录: {BASE_DIR}")
    print(f"当前版本: {_get_current_version()}")
    print("正在检查更新...")
    result = check_update_sync()
    print(json.dumps(result, ensure_ascii=False, indent=2))
