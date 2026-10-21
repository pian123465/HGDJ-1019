# -*- coding: utf-8 -*-
r"""红果短剧平台适配器 —— 从 hongguo-downloader (GPL-3.0) 移植。

移植来源:hongguo-downloader 1.1.0
  - src/native/hongguo.js   (API / 官网数据源 / 播放直链解析)
  - main.js 搜索嗅探逻辑    (SNIFFER_JS:从官网搜索/分类页提取剧集卡片)

说明:
  - 原 Electron 版用「内嵌浏览器 + executeJavaScript」嗅探官网 DOM;
    这里等价改为「HTTP 拉取 HTML + 正则提取」,提取规则与 SNIFFER_JS 一致:
      链接里 series_id=(\d{6,}) -> 剧 ID;剧名优先取 img[alt],再取
      [class*=title],再取整块文本;封面优先 picture>source[srcset],
      兜底 img[src] / img[data-src];总集数取 [class*=episode] 里的
      「N 集」;标签取 [class*=tag-text](最多 4 个)。
  - search / get_episodes / resolve_url / parse_share_url 完整实现,
    替换掉原 _template.py 里的 TODO 占位。

GPL-3.0 说明:本文件基于 GPL-3.0 开源项目移植,分发/修改时须保留 GPL-3.0 协议声明。
"""
from __future__ import annotations

import html as html_lib
import re
from typing import AsyncIterator
from urllib.parse import quote

from loguru import logger

from ..core.base import BasePlatform, Drama, DownloadOptions, Episode
from ..core.hongguo_client import (
    SITE_ORIGIN,
    fetch_episode_list,
    fetch_play_url_single,
    fetch_site_html,
    resolve_series_id,
)

_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.S | re.I)


def _attr(tag: str, name: str) -> str:
    m = re.search(r'\b' + re.escape(name) + r'\s*=\s*"([^"]*)"', tag, re.I)
    return m.group(1) if m else ""


def _extract_cards(html_text: str) -> list[Drama]:
    """从官网 HTML 提取剧集卡片(对应原 SNIFFER_JS 的输出结构)。"""
    cards: list[Drama] = []
    seen: set[str] = set()
    for attrs, inner in _ANCHOR_RE.findall(html_text):
        href = _attr(attrs, "href") or ""
        m = re.search(r"series_id=(\d{6,})", href)
        if not m:
            continue
        sid = m.group(1)
        if sid in seen:
            continue
        seen.add(sid)

        # 剧名:优先 img[alt]
        title = ""
        im = _IMG_RE.search(inner)
        if im:
            alt = _attr(im.group(0), "alt")
            if alt:
                title = html_lib.unescape(alt).strip()
        if not title:
            tm = re.search(r'class="[^"]*title[^"]*"[^>]*>([^<]*)', inner)
            if tm:
                title = html_lib.unescape(tm.group(1)).strip()
        if not title:
            title = re.sub(r"<[^>]+>", " ", inner)
            title = html_lib.unescape(title).strip()
        if not title:
            continue

        # 封面:优先 picture>source[srcset]
        cover = ""
        pm = re.search(r"<picture\b[^>]*>(.*?)</picture>", inner, re.S | re.I)
        if pm:
            sm = re.search(r'<source\b[^>]*srcset="([^"]+)"', pm.group(1), re.I)
            if sm:
                cover = sm.group(1).split()[0]
        if not cover:
            src = _attr(im.group(0), "src") if im else ""
            if not src:
                src = _attr(im.group(0), "data-src") if im else ""
            cover = src

        # 总集数:「全86集」
        episode_count = 0
        em = re.search(r'class="[^"]*episode[^"]*"[^>]*>([^<]*)', inner)
        if em:
            mm = re.search(r"(\d+)\s*集", em.group(1))
            if mm:
                episode_count = int(mm.group(1))

        # 标签
        tags = [
            html_lib.unescape(t.group(1)).strip()
            for t in re.finditer(r'class="[^"]*tag-text[^"]*"[^>]*>([^<]*)', inner)
        ]
        tags = [t for t in tags if t][:4]

        cards.append(Drama(
            platform="红果短剧", drama_id=sid, title=title, cover=cover,
            description="", episode_count=episode_count, tags=tags,
        ))
    return cards


class HongguoPlatform(BasePlatform):
    """红果短剧平台(完整实现:搜索 / 分集 / 播放直链 / 分享链接)。"""

    name = "红果短剧"
    url_domains = ["douyin", "iesdouyin", "hongguoduanju", "hongguo"]

    def __init__(self, cookie: str = ""):
        self.cookie = cookie

    # ---------------- 搜索 ----------------
    async def search(self, keyword: str, page: int = 1) -> AsyncIterator[Drama]:
        """官网站内搜索(服务端渲染,无签名)。"""
        url = f"{SITE_ORIGIN}/search/{quote(str(keyword))}"
        try:
            html_text = await fetch_site_html(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[红果] 搜索页拉取失败: {e}")
            return
        for card in _extract_cards(html_text):
            yield card

    # ---------------- 分集 ----------------
    async def get_episodes(self, drama: Drama) -> list[Episode]:
        data = await fetch_episode_list(drama.drama_id)
        episodes = []
        for e in data["episodes"]:
            episodes.append(Episode(
                platform="hongguo",
                episode_id=str(e["vid"]),
                title=e.get("title") or f"第{e['vid_index']}集",
                index=e["vid_index"],
                play_url="",
                drama_title=data["series_title"],
                extra={
                    "vid": str(e["vid"]),
                    "series_id": str(data["series_id"]),
                    "cover": e.get("cover") or data.get("cover") or "",
                    "platform": "hongguo",
                },
            ))
        episodes.sort(key=lambda ep: ep.index)
        return episodes

    # ---------------- 播放直链 ----------------
    async def resolve_url(self, episode: Episode, options: DownloadOptions) -> str:
        """取单集播放直链与 spade_a(加密 key 信息)。

        官网兜底时 spade_a 为空、直链为明文 MP4。
        """
        play = await fetch_play_url_single(
            (episode.extra or {}).get("vid"),
            (episode.extra or {}).get("series_id"),
        )
        if not play or not play.get("url"):
            raise RuntimeError("未获取到有效播放地址")
        episode.play_url = play["url"]
        episode.extra["spade_a"] = play.get("spadeA") or None
        episode.extra["codec"] = play.get("codec") or ""
        return play["url"]

    # ---------------- 分享链接 ----------------
    async def parse_share_url(self, parsed) -> Drama | None:
        """分享链接 -> Drama(与 hongguo.resolveSeriesId 逻辑一致)。"""
        url = (parsed.final_url or parsed.url or "").strip()
        if not url:
            return None
        sid = await resolve_series_id(url)
        data = await fetch_episode_list(sid)
        return Drama(
            platform="红果短剧",
            drama_id=data["series_id"],
            title=data["series_title"],
            cover=data.get("cover") or "",
            description="",
            episode_count=data["total"],
            tags=[],
        )

    # ---------------- 兼容旧签名接口(占位) ----------------
    def _sign_headers(self, path: str, params: dict) -> dict:
        """红果官方接口无需额外签名(带设备指纹参数即可);保留接口兼容。"""
        return {}
