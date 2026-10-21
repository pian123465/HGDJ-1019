"""平台适配器模板。

⚠️ 注意:
  - 红果短剧的完整实现已迁移到 `platforms/hongguo.py`
    (移植自 hongguo-downloader GPL-3.0:官网搜索 + 官方 API 解析 + spade_a
    密钥派生 + CENC-AES-CTR 解密),本文件保留的 HongguoPlatform 只是
    旧占位,不再被 ui.py 引用。
  - 河马短剧等新平台仍可参照本模板实现。

实操步骤:
    1. 用 Charles / mitmproxy / Charles + 模拟器抓 App 或小程序的请求
    2. 在 Network 里找返回剧目 JSON 的接口(通常是 GET /api/xxx/list)
    3. 找出请求里的签名 header(常见: sign / X-Sign / X-Bogus / X-Argus)
    4. 把签名算法用 Python 重写(通常 md5 / hmac / 自定义 crc)
    5. 填到下面的 search / resolve_url 里

字节系(红果)的关键签名:
    - X-Bogus:基于 body + UA + 时间戳的混淆
    - a-bogus:新版本,protobuf + crc32
    建议逆向位置: msdk / bytedance / X-Bogus 这几个 npm 包
    (红果官网 hongguoduanju.com 是服务端渲染,搜索/分集/直链无需签名,
    已由 platforms/hongguo.py 直接实现)
"""
from __future__ import annotations

from typing import AsyncIterator

from ..core.base import BasePlatform, Drama, DownloadOptions, Episode


class HongguoPlatform(BasePlatform):
    name = "红果短剧"

    BASE_URL = "https://api.example-hongguo.com"  # ← 改成真实域名
    url_domains = ["hongguo", "iesdouyin", "douyin"]

    def __init__(self, cookie: str = ""):
        self.cookie = cookie

    async def search(self, keyword: str, page: int = 1) -> AsyncIterator[Drama]:
        # TODO: 实现真实搜索
        # import aiohttp
        # async with aiohttp.ClientSession() as s:
        #     headers = self._sign_headers("/api/search", {"kw": keyword, "page": page})
        #     async with s.get(f"{self.BASE_URL}/api/search", params={"kw": keyword, "page": page}, headers=headers) as r:
        #         for item in (await r.json())["data"]["list"]:
        #             yield Drama(...)
        raise NotImplementedError("需要先逆向红果 API 签名 — 见模块顶部注释")

    async def get_episodes(self, drama: Drama) -> list[Episode]:
        raise NotImplementedError

    async def resolve_url(self, episode: Episode, options: DownloadOptions) -> str:
        raise NotImplementedError

    def _sign_headers(self, path: str, params: dict) -> dict:
        """签名算法占位 — 需要从 JS 端逆向。"""
        # TODO: 实现 X-Bogus / a-bogus 算法
        return {}


class HemaPlatform(BasePlatform):
    name = "河马短剧"

    BASE_URL = "https://api.example-hema.com"
    url_domains = ["hema"]

    def __init__(self):
        pass

    async def search(self, keyword: str, page: int = 1) -> AsyncIterator[Drama]:
        raise NotImplementedError("需要先逆向河马 API 签名")

    async def get_episodes(self, drama: Drama) -> list[Episode]:
        raise NotImplementedError

    async def resolve_url(self, episode: Episode, options: DownloadOptions) -> str:
        raise NotImplementedError