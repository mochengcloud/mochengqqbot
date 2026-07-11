"""陌城qqbot框架 - 命令行更新工具。

供 start.bat / start.sh 调用,提供交互式更新、纯检测(--check)和强制更新(--force)三种模式。

用法:
    python -m core.updater_cli              # 交互模式: 检测 -> 提示 y/n -> 更新
    python -m core.updater_cli --check      # 仅检测,输出单行 JSON 供脚本解析
    python -m core.updater_cli --force      # 跳过确认直接更新
    python -m core.updater_cli --help       # 帮助
"""

import os
import sys
import json
import argparse
import tempfile

# 框架根目录: core/ 的上一级
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============ 兼容导入 updater 模块 ============

try:
    # 作为包内模块运行: python -m core.updater_cli
    from core.updater import (
        check_update_sync,
        download_update,
        perform_update,
        rollback_update,
        trigger_restart,
        get_update_status,
    )
    try:
        from core.version import __version__ as CURRENT_VERSION
    except Exception:
        CURRENT_VERSION = "v0.0.0"
except Exception:
    # 直接在 core/ 目录下运行或作为脚本运行
    from updater import (
        check_update_sync,
        download_update,
        perform_update,
        rollback_update,
        trigger_restart,
        get_update_status,
    )
    try:
        from version import __version__ as CURRENT_VERSION
    except Exception:
        CURRENT_VERSION = "v0.0.0"


# ============ 进度回调 ============

def _format_size(num_bytes: int) -> str:
    """将字节数格式化为人类可读的字符串(如 1.2MB)。"""
    try:
        size = float(num_bytes)
    except Exception:
        return "0B"
    if size < 1024:
        return f"{int(size)}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f}GB"


def _progress_callback(downloaded: int, total: int) -> None:
    """下载进度回调,打印形如: [下载中] 1.2MB / 3.5MB (34%)"""
    if total > 0:
        pct = min(100, int(downloaded * 100 / total))
        print(f"\r[下载中] {_format_size(downloaded)} / {_format_size(total)} ({pct}%)",
              end="", flush=True)
    else:
        # 未知总大小时仅显示已下载量
        print(f"\r[下载中] 已下载 {_format_size(downloaded)}", end="", flush=True)


# ============ 模式实现 ============

def run_check_mode() -> int:
    """--check 模式: 输出单行 JSON 供脚本解析。

    返回退出码:
        0 有更新或无更新
        1 检测出错(但 error 字段已写入 JSON)
    """
    result = check_update_sync()
    current = result.get("current", CURRENT_VERSION)
    latest = result.get("latest")
    error = result.get("error")

    if error:
        # 错误时输出含 error 字段的 JSON
        output = {
            "has_update": False,
            "current": current,
            "error": error,
        }
        print(json.dumps(output, ensure_ascii=False))
        return 1

    if not result.get("has_update") or not latest:
        output = {
            "has_update": False,
            "current": current,
            "latest_version": None,
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0

    # 有更新: 提取关键字段
    latest_version = latest.get("version_number") or latest.get("version_name") or ""
    output = {
        "has_update": True,
        "current": current,
        "latest_version": latest_version,
        "version_name": latest.get("version_name", ""),
        "download_url": latest.get("download_url", ""),
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def run_update_flow(download_url: str) -> int:
    """执行更新流程: 下载 -> 安装 -> 重启。

    参数:
        download_url: 新版本下载地址

    返回退出码:
        0 成功(通常不会返回,因为会触发重启)
        1 失败
    """
    # 1. 下载新版本
    print("正在下载新版本...")
    temp_zip = None
    try:
        # 在系统临时目录生成临时 zip 文件
        fd, temp_zip = tempfile.mkstemp(prefix="qqbot_update_", suffix=".zip")
        os.close(fd)
        # 若 mkstemp 已创建空文件,download_update 会以 "wb" 覆盖,无需手动删除
        download_update(download_url, temp_zip, progress_callback=_progress_callback)
        # 进度打印末尾换行,避免后续输出挤在同一行
        print()
    except Exception as e:
        print()
        print(f"[错误] 下载失败: {e}")
        # 清理可能残留的临时文件
        if temp_zip and os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except Exception:
                pass
        return 1

    # 2. 安装更新
    print("正在安装更新...")
    try:
        success = perform_update(temp_zip, BASE_DIR)
    except Exception as e:
        # perform_update 内部已回滚
        print(f"[错误] 更新失败,已回滚到旧版本: {e}")
        # 清理临时文件
        if temp_zip and os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except Exception:
                pass
        return 1

    # 3. 清理临时文件
    if temp_zip and os.path.exists(temp_zip):
        try:
            os.remove(temp_zip)
        except Exception:
            pass

    if not success:
        # perform_update 返回 False 表示失败且已内部回滚
        status = get_update_status()
        detail = status.get("message", "未知错误")
        print(f"[错误] 更新失败,已回滚到旧版本: {detail}")
        return 1

    # 4. 成功 -> 重启
    print("更新完成!正在重启框架...")
    try:
        trigger_restart()
        # trigger_restart 正常情况下不会返回
    except Exception as e:
        print(f"[错误] 重启失败: {e}")
        print("请手动重启框架。")
        return 1

    return 0


def run_interactive_mode(force: bool = False) -> int:
    """交互模式(或 --force 模式)。

    参数:
        force: True 时跳过 y/n 确认直接更新

    返回退出码:
        0 成功或用户跳过
        1 失败
    """
    # 1. 打印横幅
    print("陌城qqbot框架 - 版本更新检测")
    print()

    # 2. 检测更新
    result = check_update_sync()

    # 3. 检测出错
    if result.get("error"):
        print(f"[错误] 检测更新失败: {result['error']}")
        return 1

    current = result.get("current", CURRENT_VERSION)
    latest = result.get("latest")

    # 4. 无更新
    if not result.get("has_update") or not latest:
        print("当前已是最新版本")
        return 0

    # 5. 有更新: 打印详情
    latest_version = latest.get("version_number") or latest.get("version_name") or ""
    version_name = latest.get("version_name", "")
    released_at = latest.get("released_at", "")
    download_url = latest.get("download_url", "")
    vtype = latest.get("type", "")
    type_label = "正式版" if vtype == "Official" else "测试版" if vtype == "beta" else ""

    print("========================================")
    print("  发现新版本可用!")
    print(f"  当前版本: {current}")
    print(f"  最新版本: {latest_version}" + (f" [{type_label}]" if type_label else ""))
    print(f"  版本名称: {version_name}")
    print(f"  发布时间: {released_at}")
    print("========================================")

    # 6. 确认更新
    if not force:
        while True:
            try:
                answer = input("是否立即更新? (y/n): ").strip().lower()
            except EOFError:
                # 非交互环境(如管道输入已关闭),按跳过处理
                print("已跳过更新")
                return 0
            except KeyboardInterrupt:
                print()
                print("已取消更新")
                return 0

            if answer == "y":
                break
            elif answer == "n":
                print("已跳过更新")
                return 0
            else:
                print("请输入 y 或 n")
                continue

    # 7. 执行更新流程
    if not download_url:
        print("[错误] 下载地址为空,无法更新")
        return 1

    return run_update_flow(download_url)


# ============ 主入口 ============

def main() -> int:
    """命令行主入口,解析参数并分发到对应模式。

    返回退出码。
    """
    parser = argparse.ArgumentParser(
        prog="python -m core.updater_cli",
        description="陌城qqbot框架 - 命令行更新工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m core.updater_cli              # 交互模式\n"
            "  python -m core.updater_cli --check      # 仅检测,输出 JSON\n"
            "  python -m core.updater_cli --force      # 跳过确认直接更新\n"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检测是否有更新,输出单行 JSON 供脚本解析,不执行更新",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过 y/n 确认,直接执行更新流程",
    )

    args = parser.parse_args()

    # --check 优先,且与 --force 互斥(--check 时忽略 --force)
    if args.check:
        return run_check_mode()

    return run_interactive_mode(force=args.force)


if __name__ == "__main__":
    sys.exit(main())
