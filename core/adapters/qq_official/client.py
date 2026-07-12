"""QQ 官方机器人 API 客户端:鉴权与 HTTPS 调用。"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger("qq_official_client")

# 官方 API 基础地址(群机器人)
API_BASE = "https://api.sgroup.qq.com"
# 鉴权地址
AUTH_URL = "https://bots.qq.com/app/getAppAccessToken"


class QQOfficialClient:
    """QQ 官方机器人 API 客户端。
    
    负责鉴权(access_token 缓存与自动刷新)和 HTTPS API 调用。
    """
    
    def __init__(self, app_id: str, app_secret: str, token: str = ""):
        """
        Args:
            app_id: 机器人 AppID
            app_secret: 机器人 AppSecret
            token: 机器人 Token(用于 WebSocket 鉴权,与 access_token 不同)
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = token  # WebSocket 鉴权用
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0  # 过期时间戳
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # 不在 session 级别设置 timeout,避免跨事件循环时报
            # "Timeout context manager should be used inside a task"
            # timeout 改为在每次 request 调用时传入
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def get_access_token(self) -> str:
        """获取 access_token,缓存至过期前 60 秒,过期自动刷新。

        官方说明:
          - access_token 默认有效期 7200 秒(2 小时)
          - 接近过期 60 秒内可获取新 token,老 token 在该 60 秒内仍有效
          - 每次请求不会自动刷新,需开发者自行管理
        """
        async with self._lock:
            now = time.time()
            # 提前 60 秒刷新,避免边界过期
            if self._access_token and now < self._token_expire_at - 60:
                return self._access_token
            # 重新获取
            session = await self._get_session()
            payload = {
                "appId": self.app_id,
                "clientSecret": self.app_secret,
            }
            try:
                async with session.post(AUTH_URL, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise Exception(f"获取 access_token 失败({resp.status}): {body[:200]}")
                    data = await resp.json()
                    self._access_token = data.get("access_token", "")
                    expire_in = int(data.get("expires_in", 7200))
                    # 缓存到实际过期时间(减 60 秒余量)
                    self._token_expire_at = now + expire_in - 60
                    if not self._access_token:
                        raise Exception("access_token 为空")
                    logger.info(f"[QQ官方] access_token 刷新成功,有效期 {expire_in} 秒")
                    return self._access_token
            except Exception as e:
                logger.error(f"[QQ官方] 获取 access_token 失败: {e}")
                raise
    
    async def call_api(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """调用官方 HTTPS API。
        
        Args:
            method: HTTP 方法(GET/POST/PUT/DELETE)
            path: API 路径,如 /v2/groups/{group_openid}/messages
            **kwargs: 传递给 aiohttp request 的参数(json=, params= 等)
        """
        access_token = await self.get_access_token()
        session = await self._get_session()
        url = f"{API_BASE}{path}"
        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json",
        }
        try:
            # 在 request 级别设置 timeout(避免 session 级别 timeout 跨事件循环问题)
            timeout = aiohttp.ClientTimeout(total=30)
            async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise Exception(f"API 调用失败({resp.status}): {body[:300]}")
                if not body:
                    return {}
                return json.loads(body)
        except Exception as e:
            logger.error(f"[QQ官方] API 调用失败 {method} {path}: {e}")
            raise
    
    async def get_app_info(self) -> Dict[str, Any]:
        """获取机器人自身信息(用于测试连接)。

        官方接口:GET /users/@me,返回 {id, username, avatar, ...}
        """
        return await self.call_api("GET", "/users/@me")
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
