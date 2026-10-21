"""搜索编排 — 跨平台并发模糊搜。"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from loguru import logger

from .base import BasePlatform, Drama


class SearchOrchestrator:
    """并发拉所有平台的搜索结果,先到先出。"""

    def __init__(self, platforms: list[BasePlatform]):
        self.platforms = platforms

    async def search_all(self, keyword: str, page: int = 1) -> AsyncIterator[Drama]:
        queue: asyncio.Queue = asyncio.Queue()

        async def _run(p: BasePlatform):
            try:
                async for d in p.search(keyword, page=page):
                    await queue.put(d)
            except NotImplementedError:
                logger.warning(f"[{p.name}] 尚未接入")
            except Exception as e:
                logger.exception(f"[{p.name}] 搜索失败: {e}")
            finally:
                await queue.put(None)  # 哨兵

        tasks = [asyncio.create_task(_run(p)) for p in self.platforms]
        finished = 0
        total = len(self.platforms)
        while finished < total:
            item = await queue.get()
            if item is None:
                finished += 1
                continue
            yield item