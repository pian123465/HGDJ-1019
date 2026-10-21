"""平台适配器基类 — 每个短剧平台都要实现这个接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Drama:
    """短剧元数据。"""
    platform: str            # 平台名,比如 "hongguo" / "hema"
    drama_id: str            # 平台内唯一 ID
    title: str               # 剧名
    cover: str = ""          # 封面 URL
    description: str = ""    # 简介
    episode_count: int = 0   # 总集数
    tags: list[str] = field(default_factory=list)


@dataclass
class Episode:
    """单集视频。"""
    episode_id: str          # 集内 ID
    title: str               # 比如 "第1集"
    index: int               # 集序号,从 1 开始
    play_url: str            # 播放地址(m3u8 或 mp4)
    duration: int = 0        # 秒
    # ---- 以下字段为红果内核移植新增(默认值,不影响旧平台) ----
    platform: str = ""       # 平台标识,如 "hongguo"
    drama_title: str = ""    # 所属短剧名(用于下载目录)
    extra: dict = field(default_factory=dict)  # 平台私有信息(spade_a/vid/series_id 等)


@dataclass
class DownloadOptions:
    """下载参数。"""
    fmt: str = "mp4"             # "mp4" / "ts" / "mkv"
    resolution: str = "1080p"    # "480p" / "720p" / "1080p" / "source"(取源)
    episodes: list[int] | None = None   # 要下载的集序号,None = 全集
    save_dir: str = "./downloads"
    concurrency: int = 4         # 并发分片下载数


class BasePlatform(ABC):
    """所有平台都要实现 search / get_episodes / resolve_url 三个方法。"""

    name: str = "base"
    # 该平台支持解析的域名(用于分享链接路由)
    url_domains: list[str] = []

    @abstractmethod
    async def search(self, keyword: str, page: int = 1) -> AsyncIterator[Drama]:
        """模糊搜索。返回异步迭代器,边搜边出结果。"""
        raise NotImplementedError

    @abstractmethod
    async def get_episodes(self, drama: Drama) -> list[Episode]:
        """拉取整部剧的所有集。"""
        raise NotImplementedError

    @abstractmethod
    async def resolve_url(self, episode: Episode, options: DownloadOptions) -> str:
        """把播放地址解析成可下载的真实 URL(m3u8 / mp4 直链)。
        这里通常需要带签名参数重新请求一次拿到真实播放地址。"""
        raise NotImplementedError

    async def parse_share_url(self, parsed) -> Drama | None:
        """从分享链接解析出 Drama 对象。
        默认实现:把 drama_id 当作搜索关键字回搜一次,拿第一条。
        各平台可覆盖,直接调详情接口更准。"""
        if not parsed or not parsed.drama_id:
            return None
        async for d in self.search(parsed.drama_id, page=1):
            if d.drama_id == parsed.drama_id:
                return d
        return None