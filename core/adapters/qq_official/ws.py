"""QQ 官方机器人 WebSocket 事件接收。

遵循 QQ 机器人官方 API v2 规范:
  https://bot.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html

OpCode 定义(官方):
  0  Dispatch     服务端推送事件(payload.t 为事件类型,payload.d 为数据)
  1  Heartbeat    客户端发送心跳(d 为最近收到的 s,首次为 null)
  2  Identify     客户端发送鉴权
  6  Resume       客户端恢复连接
  7  Reconnect    服务端通知客户端重连
  9  Invalid Session 鉴权失败,需重新 IDENTIFY
  10 Hello        连接建立后服务端下发,含心跳间隔
  11 Heartbeat ACK 心跳回应
"""
import asyncio
import json
import logging
from typing import Any, Callable, Optional

import aiohttp

logger = logging.getLogger("qq_official_ws")


class QQOfficialWS:
    """QQ 官方机器人 WebSocket 客户端,接收事件推送。

    生命周期:
      1. GET /gateway 获取 wss URL
      2. 建立 WS 连接,收到 op=10 Hello(含 heartbeat_interval)
      3. 发送 op=2 IDENTIFY 鉴权
      4. 收到 op=0 t=READY 事件(含 session_id) → 鉴权成功
      5. 周期发送 op=1 心跳(d=最新 s)
      6. 收到 op=0 事件 → 转给 on_event 回调
      7. 断线时若有 session_id,用 op=6 Resume 恢复;否则重新 IDENTIFY
    """

    def __init__(self, client: "QQOfficialClient", on_event: Callable):
        """
        Args:
            client: QQOfficialClient 实例(用于获取 access_token)
            on_event: 事件回调函数,签名 async fn(payload: dict)
        """
        self.client = client
        self.on_event = on_event
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_heartbeat_seq: Optional[int] = None  # 最近收到的 s
        self._session_id: Optional[str] = None  # READY 事件下发的会话 ID,用于 Resume

    async def _get_wss_url(self) -> str:
        """获取 WebSocket 网关地址。

        官方接口:GET /gateway,返回 {"url": "wss://api.sgroup.qq.com/websocket/"}
        """
        data = await self.client.call_api("GET", "/gateway")
        url = data.get("url", "")
        if not url:
            raise Exception("获取 WebSocket 网关地址失败")
        return url

    async def start(self) -> None:
        """启动 WebSocket 连接循环(自动重连)。"""
        self._running = True
        self._session = aiohttp.ClientSession()
        while self._running:
            try:
                wss_url = await self._get_wss_url()
                logger.info(f"[QQ官方] 连接 WebSocket: {wss_url}")
                async with self._session.ws_connect(wss_url) as ws:
                    await self._handle_ws(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[QQ官方] WebSocket 连接异常: {e}")
            # 清理心跳任务
            self._stop_heartbeat()
            if self._running:
                logger.info("[QQ官方] WebSocket 5 秒后重连...")
                await asyncio.sleep(5)
        await self.close()

    async def _handle_ws(self, ws) -> None:
        """处理 WebSocket 消息循环。"""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("[QQ官方] WebSocket 已关闭")
                break
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                payload = json.loads(msg.data)
            except Exception:
                continue

            op_code = payload.get("op")
            seq = payload.get("s")
            event_type = payload.get("t", "")

            # 更新心跳序列号(所有带 s 的下行消息都要记录)
            if seq is not None:
                self._last_heartbeat_seq = seq

            if op_code == 10:
                # Hello: 服务端下发心跳间隔,随后发送 IDENTIFY
                d = payload.get("d", {}) or {}
                interval = d.get("heartbeat_interval", 30000)
                self._start_heartbeat(ws, interval)
                # 首次连接无 session_id,发送 IDENTIFY;重连有 session_id 发送 Resume
                if self._session_id:
                    await self._send_resume(ws)
                else:
                    await self._send_identify(ws)
            elif op_code == 11:
                # 心跳 ACK,忽略
                continue
            elif op_code == 0:
                # Dispatch: 事件推送
                if event_type == "READY":
                    # 鉴权成功,记录 session_id
                    d = payload.get("d", {}) or {}
                    self._session_id = d.get("session_id", "")
                    user = d.get("user", {}) or {}
                    logger.info(
                        f"[QQ官方] 鉴权成功(session={self._session_id}, "
                        f"bot={user.get('username', '')} id={user.get('id', '')})"
                    )
                elif event_type == "RESUMED":
                    logger.info("[QQ官方] 会话恢复成功(RESUMED)")
                else:
                    # 业务事件转发给回调
                    asyncio.create_task(self.on_event(payload))
            elif op_code == 7:
                # 服务端要求重连:断开后外层循环会重新连接
                logger.info("[QQ官方] 服务端要求重连(RECONNECT)")
                break
            elif op_code == 9:
                # 鉴权失败:清空 session_id,下次重新 IDENTIFY
                logger.warning("[QQ官方] 鉴权失败(Invalid Session),将重新 IDENTIFY")
                self._session_id = None
                # 等待 2 秒后重连
                await asyncio.sleep(2)
                break
            # 其他 op 忽略

    async def _send_identify(self, ws) -> None:
        """发送 IDENTIFY 鉴权 payload。

        intents 为位掩码:
          1 << 25 = GROUP_AND_C2C_EVENT
            订阅 GROUP_AT_MESSAGE_CREATE(群@机器人)、C2C_MESSAGE_CREATE 等群机器人事件
        """
        access_token = await self.client.get_access_token()
        identify = {
            "op": 2,
            "d": {
                "token": f"QQBot {access_token}",
                "intents": 1 << 25,  # GROUP_AND_C2C_EVENT
                "shard": [0, 1],
            },
        }
        await ws.send_str(json.dumps(identify))
        logger.info("[QQ官方] IDENTIFY 已发送, intents=1<<25 (GROUP_AND_C2C_EVENT)")

    async def _send_resume(self, ws) -> None:
        """发送 RESUME 恢复会话 payload。"""
        access_token = await self.client.get_access_token()
        resume = {
            "op": 6,
            "d": {
                "token": f"QQBot {access_token}",
                "session_id": self._session_id,
                "seq": self._last_heartbeat_seq,
            },
        }
        await ws.send_str(json.dumps(resume))
        logger.info(
            f"[QQ官方] RESUME 已发送(session={self._session_id}, seq={self._last_heartbeat_seq})"
        )

    def _start_heartbeat(self, ws, interval_ms: int) -> None:
        """启动心跳 task。"""
        self._stop_heartbeat()

        async def _heartbeat():
            while True:
                await asyncio.sleep(interval_ms / 1000)
                hb = {"op": 1, "d": self._last_heartbeat_seq}
                try:
                    await ws.send_str(json.dumps(hb))
                except Exception:
                    break

        self._heartbeat_task = asyncio.create_task(_heartbeat())

    def _stop_heartbeat(self) -> None:
        """停止心跳 task。"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                # 不能 await,因为可能在非异步上下文调用
                pass
            except Exception:
                pass
        self._heartbeat_task = None

    async def stop(self) -> None:
        """停止 WebSocket。"""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        await self.close()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
