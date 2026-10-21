"""分享文本 → Drama 的统一入口。

用法:
    resolver = ShareResolver(platforms=[HongguoPlatform(), HemaPlatform()])
    drama = await resolver.resolve(share_text)
"""
from __future__ import annotations

from loguru import logger

from .base import BasePlatform, Drama
from .link_parser import LinkParser, ParsedLink


class ShareResolver:
    """根据链接域名路由到对应平台解析。"""

    def __init__(self, platforms: list[BasePlatform]):
        self.platforms = platforms
        self.parser = LinkParser()

    def _route(self, parsed: ParsedLink) -> BasePlatform | None:
        """按 platform/domain 找一个能处理的平台。"""
        for p in self.platforms:
            for d in p.url_domains:
                if d in parsed.platform or d in parsed.domain:
                    return p
        return None

    async def resolve(self, text: str) -> tuple[ParsedLink, Drama | None]:
        """从分享文本 → Drama。

        Returns:
            (ParsedLink, Drama or None)
            Drama 为 None 的几种情况:
                - 文本里没 URL
                - URL 短链重定向失败
                - URL 不在支持的平台列表里
                - 平台适配器未实现(签名未逆向)
        """
        parsed = await self.parser.parse_share(text)
        if not parsed:
            logger.warning("未能从分享文本提取 URL")
            return ParsedLink(raw_text=text, url="", final_url="", domain="",
                              platform="", drama_id="", extra={}), None
        platform = self._route(parsed)
        if not platform:
            logger.warning(f"不支持的平台:{parsed.platform}/{parsed.domain}")
            return parsed, None
        try:
            drama = await platform.parse_share_url(parsed)
            return parsed, drama
        except NotImplementedError:
            logger.warning(f"{platform.name} 适配器未接入")
            return parsed, None
        except Exception as e:
            logger.exception(f"{platform.name} 解析失败:{e}")
            return parsed, None