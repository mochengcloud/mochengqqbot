"""Bot 主应用:整合连接管理、事件总线、插件加载与生命周期管理。

替代原 nonebot.init / nonebot.run 的启动流程。
"""
import argparse
import asyncio
import logging
import os
import sys
import threading

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config_manager import config_manager
from log_manager import log_manager
from core.connection import WSClientManager, WSServerManager
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
            mode: "ws_client" 或 "ws_server"
            ws_url: 正向 WS 连接 URL(ws_client 模式)
            access_token: WS 鉴权 token
            webui_enabled: 是否启动 WebUI
        """
        self.host = host
        self.port = port
        self.webui_port = webui_port
        self.mode = mode
        self.ws_url = ws_url
        self.access_token = access_token
        self.webui_enabled = webui_enabled

    # ---------------- 内部辅助 ----------------

    def _print_banner(self, title, show_webui=True):
        """打印连接信息横幅。"""
        onebot_cfg = config_manager.get_onebot_config()
        mode = onebot_cfg.get("mode", "ws_client")
        print("=" * 50)
        print(f"  {title}")
        print(f"  Version:     {__version__}")
        print("=" * 50)
        print(f"  Bot Port:    {self.port}")
        if show_webui:
            print(f"  WebUI Port:  {self.webui_port}")
            print(f"  WebUI URL:   http://127.0.0.1:{self.webui_port}")
        print(f"  OneBot Mode: {mode}")
        if mode == "ws_client":
            ws_client = onebot_cfg.get("ws_client", {})
            url = ws_client.get("url", "ws://127.0.0.1:3001")
            token = ws_client.get("access_token", "")
            print(f"  Connecting to: {url}")
            if token:
                print(f"  Access Token: ***")
        elif mode == "ws_server":
            ws_server = onebot_cfg.get("ws_server", {})
            print(f"  WS Server: {ws_server.get('host', '0.0.0.0')}:{ws_server.get('port', 3000)}")
        webui_config = config_manager.get_webui_config()
        print(f"  WebUI Token: {webui_config.get('access_token', '未设置')}")
        print("=" * 50)

    def _log_mode(self):
        """根据模式记录连接日志。"""
        onebot_cfg = config_manager.get_onebot_config()
        mode = onebot_cfg.get("mode", "ws_client")
        if mode == "ws_client":
            ws_client = onebot_cfg.get("ws_client", {})
            log_manager.log_connection(
                "connecting",
                f"Connecting to {ws_client.get('url', 'ws://127.0.0.1:3001')}",
            )
        elif mode == "ws_server":
            ws_server = onebot_cfg.get("ws_server", {})
            log_manager.log_connection(
                "listening",
                f"WS Server listening on {ws_server.get('port', 3000)}",
            )

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

    def _run_ws_client(self):
        """正向 WS 客户端模式:Bot 主动连接 OneBot 实现的 WS 服务端。"""

        async def _main():
            load_plugins("plugins")
            driver = get_driver()
            await driver.trigger_startup()
            try:
                manager = WSClientManager()
                await manager.start(self.ws_url, self.access_token)
            finally:
                await driver.trigger_shutdown()

        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            pass

    def _run_ws_server(self):
        """反向 WS 服务端模式:OneBot 实现主动连接 Bot 的 WS 服务端。"""
        import uvicorn
        from fastapi import FastAPI

        load_plugins("plugins")
        driver = get_driver()
        asyncio.run(driver.trigger_startup())
        try:
            app = FastAPI()
            manager = WSServerManager()
            manager.setup_routes(app, self.access_token)
            uvicorn.run(app, host=self.host, port=self.port)
        finally:
            asyncio.run(driver.trigger_shutdown())

    def _run_bot(self):
        """根据 mode 启动 Bot 主循环。"""
        if self.mode == "ws_client":
            self._run_ws_client()
        elif self.mode == "ws_server":
            self._run_ws_server()
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    # ---------------- 对外入口 ----------------

    def run(self):
        """默认模式:同时启动 Bot + WebUI(线程)"""
        self._print_banner("陌城qqbot框架 - 正在启动...", show_webui=True)
        log_manager.log_connection("started", f"Bot starting on port {self.port}")
        self._log_mode()
        if self.webui_enabled:
            self._start_webui_thread()
        self._run_bot()

    def run_bot_only(self):
        """仅启动 Bot"""
        self._print_banner("QQ Bot Manager - Bot Only Mode", show_webui=False)
        log_manager.log_connection("started", f"Bot starting on port {self.port}")
        self._log_mode()
        self._run_bot()

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
    onebot_config = config_manager.get_onebot_config()

    host = args.host or server_config.get("host", "0.0.0.0")
    port = args.port or server_config.get("port", 8080)
    webui_port = args.webui_port or server_config.get("webui_port", 8081)

    mode = onebot_config.get("mode", "ws_client")
    if mode == "ws_client":
        ws_cfg = onebot_config.get("ws_client", {})
        ws_url = ws_cfg.get("url", "ws://127.0.0.1:3001")
        access_token = ws_cfg.get("access_token", "")
    elif mode == "ws_server":
        ws_cfg = onebot_config.get("ws_server", {})
        ws_url = ""
        access_token = ws_cfg.get("access_token", "")
    else:
        ws_url = ""
        access_token = ""

    app = BotApp(
        host=host,
        port=port,
        webui_port=webui_port,
        mode=mode,
        ws_url=ws_url,
        access_token=access_token,
        webui_enabled=True,
    )

    if args.webui:
        app.run_webui_only()
    elif args.bot:
        app.run_bot_only()
    else:
        app.run()


if __name__ == "__main__":
    main()
