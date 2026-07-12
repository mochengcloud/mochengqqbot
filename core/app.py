"""Bot 主应用:整合连接管理、事件总线、插件加载与生命周期管理。

替代原 nonebot.init / nonebot.run 的启动流程。
"""
import argparse
import asyncio
import logging
import sys
import threading

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config_manager import config_manager
from log_manager import log_manager
from core.lifecycle import get_driver
from core.plugin_loader import load_plugins
from core.version import __version__


def _setup_logging():
    """配置根日志:带时间戳格式,输出到 stdout。"""
    root = logging.getLogger()
    # 避免重复添加 handler
    if any(getattr(h, "_bot_formatter", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler._bot_formatter = True
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class BotApp:
    """Bot 主应用,整合所有子系统。"""

    def __init__(self, host="0.0.0.0", port=8080, webui_port=8081,
                 mode="ws_client", ws_url="", access_token="",
                 webui_enabled=True):
        """
        Args:
            host: 监听地址
            port: Bot 端口(也用于反向 WS 服务)
            webui_port: WebUI 端口
            mode: "ws_client" 或 "ws_server"(保留向后兼容,不再使用)
            ws_url: 正向 WS 连接 URL(保留向后兼容,不再使用)
            access_token: WS 鉴权 token(保留向后兼容,不再使用)
            webui_enabled: 是否启动 WebUI
        """
        self.host = host
        self.port = port
        self.webui_port = webui_port
        self.mode = mode  # 保留但不再使用,仅向后兼容
        self.ws_url = ws_url  # 保留但不再使用
        self.access_token = access_token  # 保留但不再使用
        self.webui_enabled = webui_enabled

    # ---------------- 内部辅助 ----------------

    def _print_banner(self, title, show_webui=True):
        """打印连接信息横幅。"""
        adapters = config_manager.get_adapters()
        print("=" * 50)
        print(f"  {title}")
        print(f"  Version:     {__version__}")
        print("=" * 50)
        print(f"  Bot Port:    {self.port}")
        if show_webui:
            print(f"  WebUI Port:  {self.webui_port}")
            print(f"  WebUI URL:   http://127.0.0.1:{self.webui_port}")
        print(f"  Adapters:    {len(adapters)} 个")
        for i, a in enumerate(adapters, 1):
            atype = a.get("type", "?")
            name = a.get("name", "")
            enabled = "启用" if a.get("enabled", True) else "禁用"
            print(f"    [{i}] {name} ({atype}) - {enabled}")
            if atype == "onebot_v11":
                cfg = a.get("config", {})
                mode = cfg.get("mode", "ws_client")
                if mode == "ws_client":
                    print(f"        模式: ws_client → {cfg.get('url', '')}")
                else:
                    print(f"        模式: ws_server → {cfg.get('host', '')}:{cfg.get('port', 8080)}")
            elif atype == "qq_official":
                cfg = a.get("config", {})
                print(f"        AppID: {cfg.get('app_id', '')}")
        webui_config = config_manager.get_webui_config()
        print(f"  WebUI Token: {webui_config.get('access_token', '未设置')}")
        print("=" * 50)

    def _start_webui_thread(self):
        """在守护线程中启动 WebUI。"""
        from webui.app import app as webui_app
        import uvicorn

        def run_webui():
            log_manager.log_connection(
                "webui_started", f"WebUI running on port {self.webui_port}"
            )
            uvicorn.run(
                webui_app,
                host="127.0.0.1" if self.host == "0.0.0.0" else self.host,
                port=self.webui_port,
                log_level="critical",
                access_log=False,
            )

        thread = threading.Thread(target=run_webui, daemon=True)
        thread.start()
        return thread

    # ---------------- Bot 启动核心 ----------------

    def _run_adapters(self):
        """启动所有适配器(替代原 _run_bot)。"""
        from core.adapters.manager import get_adapter_manager

        async def _main():
            load_plugins("plugins")
            driver = get_driver()
            await driver.trigger_startup()
            # 使用全局单例,WebUI 也能访问同一实例
            manager = get_adapter_manager()
            try:
                await manager.start_all()
                # 保持运行,直到被中断
                # 使用 Event 让主协程等待,避免 start_all 返回后立即退出
                stop_event = asyncio.Event()
                # 注册信号处理(可选,Linux 下生效)
                try:
                    import signal
                    loop = asyncio.get_running_loop()
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        try:
                            loop.add_signal_handler(sig, stop_event.set)
                        except (NotImplementedError, RuntimeError):
                            pass  # Windows 不支持
                except Exception:
                    pass
                await stop_event.wait()
            finally:
                await manager.stop_all()
                await driver.trigger_shutdown()

        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            pass

    # ---------------- 对外入口 ----------------

    def run(self):
        """默认模式:同时启动 Bot + WebUI(线程)"""
        self._print_banner("陌城qqbot框架 - 正在启动...", show_webui=True)
        log_manager.log_connection("started", f"Bot starting on port {self.port}")
        if self.webui_enabled:
            self._start_webui_thread()
        self._run_adapters()

    def run_bot_only(self):
        """仅启动 Bot"""
        self._print_banner("QQ Bot Manager - Bot Only Mode", show_webui=False)
        log_manager.log_connection("started", f"Bot starting on port {self.port}")
        self._run_adapters()

    def run_webui_only(self):
        """仅启动 WebUI"""
        import uvicorn
        from webui.app import app as webui_app

        webui_config = config_manager.get_webui_config()
        print(f"[WebUI] Running at http://{self.host}:{self.webui_port}")
        print(f"[WebUI] Access Token: {webui_config.get('access_token', '未设置')}")
        log_manager.log_connection(
            "webui_started", f"WebUI running on port {self.webui_port}"
        )
        uvicorn.run(
            webui_app,
            host="127.0.0.1" if self.host == "0.0.0.0" else self.host,
            port=self.webui_port,
            log_level="critical",
            access_log=False,
        )


def main():
    """命令行入口:解析参数并创建 BotApp。"""
    _setup_logging()
    parser = argparse.ArgumentParser(description="QQ Bot Manager")
    parser.add_argument("--bot", action="store_true", help="Run bot only")
    parser.add_argument("--webui", action="store_true", help="Run WebUI only")
    parser.add_argument("--port", type=int, default=None, help="Bot port")
    parser.add_argument("--webui-port", type=int, default=None, help="WebUI port")
    parser.add_argument("--host", default=None, help="Host address")
    args = parser.parse_args()

    server_config = config_manager.get_server_config()
    host = args.host or server_config.get("host", "0.0.0.0")
    port = args.port or server_config.get("port", 8080)
    webui_port = args.webui_port or server_config.get("webui_port", 8081)

    app = BotApp(
        host=host,
        port=port,
        webui_port=webui_port,
        webui_enabled=True,
    )

    if args.webui:
        app.run_webui_only()
    elif args.bot:
        # bot only 模式也用 AdapterManager 启动
        app.run()
    else:
        app.run()


if __name__ == "__main__":
    main()
