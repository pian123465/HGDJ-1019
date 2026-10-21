"""分享链接解析。

流程:
    分享文本 (随便什么格式)
        └─► 提取 URL(正则)
            └─► HEAD 请求跟随重定向,拿到最终 URL
                └─► 按域名路由到平台解析器
                    └─► 提取 video_id / drama_id

支持平台(域名匹配):
    - v.douyin.com / www.iesdouyin.com / www.douyin.com  →  抖音 / 红果短剧
    - 河马 / 其他平台                                       →  按需扩展
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

import aiohttp
from loguru import logger


URL_REGEX = re.compile(r'https?://[^\s<>"\'`]+', re.IGNORECASE)

# 各平台最终 URL 的 ID 提取规则
DOMAIN_RULES: list[tuple[str, str]] = [
    # (domain_match, regex_for_id)
    ("iesdouyin.com", r"/(?:video|note)/(\d+)"),
    ("douyin.com", r"/video/(\d+)"),
    ("hongguoduanju.com", r"series_id=(\d+)"),   # 红果官网 /player /detail
    ("hongguo", r"/drama/(\w+)"),
    ("hema", r"/(?:drama|play)/(\w+)"),
]


@dataclass
class ParsedLink:
    raw_text: str            # 原始分享文本
    url: str                 # 提取出的 URL
    final_url: str           # 跟随重定向后的最终 URL
    domain: str              # 顶级域名
    platform: str            # 识别出的平台(iesdouyin / douyin / hema / ...)
    drama_id: str            # 解析出的剧 ID
    extra: dict              # 额外参数(query string)


class LinkParser:
    """分享链接解析器。"""

    def __init__(self, timeout: float = 10.0):
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    # ---------- 步骤 1:提取 URL ----------
    @staticmethod
    def extract_url(text: str) -> str | None:
        """从一段分享文本里抓第一个 URL。"""
        if not text:
            return None
        m = URL_REGEX.search(text)
        return m.group(0).rstrip(".,;:!?)") if m else None

    # ---------- 步骤 2:跟随重定向 ----------
    async def follow_redirect(self, url: str) -> str:
        """短链 → 最终 URL。
        用 HEAD 优先;不支持 HEAD 的服务,fallback 到 GET Range:bytes=0-0。"""
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        }
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            try:
                async with s.head(url, headers=headers, allow_redirects=True) as r:
                    if r.status < 400:
                        return str(r.url)
            except aiohttp.ClientError:
                pass
            # fallback
            async with s.get(url, headers={**headers, "Range": "bytes=0-0"},
                              allow_redirects=True) as r:
                r.raise_for_status()
                return str(r.url)

    # ---------- 步骤 3:解析最终 URL ----------
    @staticmethod
    def parse(final_url: str) -> ParsedLink | None:
        """从最终 URL 拆出 platform + drama_id。"""
        parsed = urlparse(final_url)
        host = (parsed.netloc or "").lower()
        # 找匹配规则
        for dom_match, id_regex in DOMAIN_RULES:
            if dom_match in host:
                # path 优先,query 兜底(如 hongguoduanju.com/detail?series_id=123456)
                m = re.search(id_regex, parsed.path) or re.search(id_regex, parsed.query)
                if m:
                    # 提取额外 query
                    qs = parse_qs(parsed.query)
                    extra = {k: v[0] for k, v in qs.items()}
                    return ParsedLink(
                        raw_text="",
                        url=final_url,
                        final_url=final_url,
                        domain=host,
                        platform=dom_match,
                        drama_id=m.group(1),
                        extra=extra,
                    )
        logger.warning(f"无法解析的 URL:{final_url}")
        return None

    # ---------- 一站式 ----------
    async def parse_share(self, text: str) -> ParsedLink | None:
        """从分享文本一路走到 ParsedLink。
        None 表示识别不出(没 URL、URL 不在支持列表里)。"""
        url = self.extract_url(text)
        if not url:
            return None
        try:
            final_url = await self.follow_redirect(url)
        except Exception as e:
            logger.error(f"重定向失败:{url} → {e}")
            return None
        result = self.parse(final_url)
        if result:
            result.raw_text = text
            result.url = url
        return result


# 同步包装,方便 UI 在普通函数里调用
def parse_share_sync(text: str) -> ParsedLink | None:
    """同步版(UI 用),内部新开事件循环跑异步部分。"""
    import asyncio
    return asyncio.run(LinkParser().parse_share(text))


# ---------- 单元测试 ----------
if __name__ == "__main__":
    # 这个 demo 会 print 中文测试数据,cp1252 / cp936 控制台会 UnicodeEncodeError
    # (打包后的 GUI 程序不走这里,console=False 时 sys.stdout 是 None,print 是空操作)
    import sys
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name, None)
        if _stream is None:
            continue
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    import asyncio
    tests = [
        "[红果短剧] 龙王驾到 https://v.douyin.com/abc123/ 快来看",
        "https://www.iesdouyin.com/share/video/7123456789012345678/?...",
        "【河马短剧】xx短剧 https://hema.example/drama/12345",
    ]
    parser = LinkParser()
    for t in tests:
        url = LinkParser.extract_url(t)
        print(f"text: {t}\n  -> url: {url}")

    # 解析逻辑(不需要网络)
    for u in [
        "https://www.iesdouyin.com/share/video/7123456789012345678/?region=CN",
        "https://www.douyin.com/video/7123456789012345678",
        "https://api.hema.example/drama/abc12345",
    ]:
        print(f"final: {u}\n  -> {LinkParser.parse(u)}")