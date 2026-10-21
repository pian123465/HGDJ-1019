"""下载引擎 - 支持四种引擎:
    1. aria2(推荐,断点续传/分片最强)
    2. yt-dlp(部分短剧源可能它已经支持)
    3. native(自研,aiohttp + ffmpeg HLS 合并)
    4. hongguo(红果 CENC 加密直链:流式下载 -> spade_a 派生 AES Key
               -> CENC-AES-CTR 解密 -> 输出 mp4,移植自 hongguo-downloader GPL-3.0)

二进制(aria2c / ffmpeg)优先用打包内置的(随 .exe 分发),找不到再走 PATH。
"""
from __future__ import annotations

import asyncio
import enum
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger

from .aria2_client import Aria2Client
from .base import DownloadOptions, Episode
from .binary_locator import ffmpeg_path
from .hongguo_client import HONGGUO_UA, VIDEO_REFERER
from .hongguo_crypto import decrypt_mp4_buffer, derive_key


class EngineKind(str, enum.Enum):
    ARIA2 = "aria2"
    YT_DLP = "yt-dlp"
    NATIVE = "native"
    HONGGUO = "hongguo"


@dataclass
class DownloadResult:
    success: bool
    path: Path | None = None
    error: str = ""
    engine: str = ""


class DownloadEngine:
    """根据 URL 类型和可用引擎自动选择最佳方案。

    选择策略:
    - aria2 装了 + URL 是 http(s) → aria2(最快)
    - aria2 没装 → 试 yt-dlp(可能直接拉全)
    - yt-dlp 也不支持 → 自研 fallback
    """

    def __init__(self, options: DownloadOptions, prefer: EngineKind | None = None):
        self.options = options
        self.prefer = prefer
        self.aria2 = Aria2Client() if Aria2Client.is_installed() else None

    async def download(
        self,
        episode: Episode,
        url: str,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> DownloadResult:
        """统一入口。返回 (ok, path, error)。"""
        is_hongguo = (episode.extra or {}).get("platform") == "hongguo" or episode.platform == "hongguo"
        # 红果的源永远是 MP4(API 直链是 CENC 加密 MP4 / 官网兜底是明文 MP4),
        # 强制 mp4 后缀,避免用户选了 mkv 却把 mp4 内容存成 .mkv。
        fmt = "mp4" if is_hongguo else self.options.fmt
        # 下载目录:优先用剧名(红果),否则退回原来的「集标题/集ID」逻辑
        folder = (episode.drama_title or "").strip()
        if not folder:
            folder = episode.title.split("/")[0] or episode.episode_id
        out_dir = Path(self.options.save_dir) / self._safe(folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = self._safe(f"{episode.index:03d}_{episode.title}")
        target = out_dir / f"{safe}.{fmt}"

        # 红果加密直链(带 spade_a):必须走解密引擎,不能交给 aria2/yt-dlp(会下到密文)
        if is_hongguo and (episode.extra or {}).get("spade_a"):
            return await self._via_hongguo(episode, url, target, on_progress)

        # 引擎选择顺序
        order = self._pick_engine_order(url)
        last_err = ""
        for kind in order:
            try:
                if kind == EngineKind.ARIA2 and self.aria2:
                    return await self._via_aria2(episode, url, target, on_progress)
                if kind == EngineKind.YT_DLP:
                    return await self._via_ytdlp(episode, url, target, on_progress)
                if kind == EngineKind.NATIVE:
                    return await self._via_native(episode, url, target, on_progress)
            except Exception as e:
                logger.warning(f"{kind} 失败: {e},尝试下一个引擎")
                last_err = str(e)
        return DownloadResult(success=False, error=f"所有引擎失败: {last_err}")

    # ---------- 引擎选择 ----------
    def _pick_engine_order(self, url: str) -> list[EngineKind]:
        if self.prefer:
            order = [self.prefer]
        else:
            order = []
        # 默认优先级
        if EngineKind.ARIA2 not in order and self.aria2:
            order.append(EngineKind.ARIA2)
        # m3u8 → yt-dlp 处理很稳
        if EngineKind.YT_DLP not in order and ("m3u8" in url or url.endswith(".m3u8")):
            order.append(EngineKind.YT_DLP)
        if EngineKind.NATIVE not in order:
            order.append(EngineKind.NATIVE)
        return order

    # ---------- hongguo(CENC 解密下载,移植自 hongguo-downloader) ----------
    async def _via_hongguo(
        self,
        episode: Episode,
        url: str,
        target: Path,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> DownloadResult:
        """红果加密直链下载:流式下载 -> spade_a 派生 Key -> CENC-AES-CTR 解密。

        与原 hongguo-downloader executeHongguoDownload 一致:
          1. 下载到 <目标>.enc.tmp(先不直接写目标名,避免暴露半成品)
          2. 403 时补 Referer 重试一次
          3. 有 spade_a 则派生 16 字节 AES Key 并解密;官网兜底直链(明文)直接改名
        """
        import aiohttp

        spade_a = (episode.extra or {}).get("spade_a")
        tmp = target.with_name(target.name + ".enc.tmp")
        headers = {"User-Agent": HONGGUO_UA}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=120)) as r:
                    r.raise_for_status()
            except aiohttp.ClientResponseError as e:
                if e.status != 403:
                    raise
                # 403:很多 CDN 要求带 Referer 才给回
                headers["Referer"] = VIDEO_REFERER
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=120)) as r:
                    r.raise_for_status()

            total = int(r.headers.get("Content-Length") or 0)
            received = 0
            with tmp.open("wb") as f:
                async for chunk in r.content.iter_chunked(256 * 1024):
                    f.write(chunk)
                    received += len(chunk)
                    if on_progress:
                        on_progress(received, total, "downloading")

        if spade_a:
            if on_progress:
                size = tmp.stat().st_size
                on_progress(size, size, "decrypting")
            key = derive_key(spade_a)
            if not key:
                tmp.unlink(missing_ok=True)
                raise RuntimeError("Key 派生失败")
            data = tmp.read_bytes()
            final_buf = decrypt_mp4_buffer(data, key)
            target.write_bytes(final_buf)
            tmp.unlink(missing_ok=True)
        else:
            tmp.rename(target)

        return DownloadResult(True, target, engine=EngineKind.HONGGUO.value)

    # ---------- aria2 ----------
    async def _via_aria2(self, episode: Episode, url: str, target: Path,
                          on_progress: Callable[[int, int, str], None] | None) -> DownloadResult:
        assert self.aria2
        if not self.aria2.is_running():
            ok = self.aria2.start_daemon()
            if not ok:
                raise RuntimeError("aria2c 启动失败")
        gid = self.aria2.add_uri(
            url,
            out=str(target),
            dir_=str(target.parent),
        )
        logger.info(f"[aria2] gid={gid} ep={episode.title}")

        def _on_prog(s: dict):
            if on_progress:
                on_progress(int(s.get("completedLength", 0)),
                            int(s.get("totalLength", 0)),
                            s.get("status", ""))

        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, self.aria2.wait_complete, gid, _on_prog)
        if ok and target.exists():
            return DownloadResult(True, target, engine=EngineKind.ARIA2.value)
        err, msg = self.aria2.is_error(gid)
        raise RuntimeError(msg or "aria2 下载失败")

    # ---------- yt-dlp ----------
    async def _via_ytdlp(self, episode: Episode, url: str, target: Path,
                          on_progress: Callable[[int, int, str], None] | None) -> DownloadResult:
        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError("yt-dlp 未安装")
        outtmpl = str(target.with_suffix("")) + ".%(ext)s"

        def hook(d):
            if on_progress and d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                on_progress(done, total, "downloading")

        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "concurrent_fragment_downloads": self.options.concurrency,
            "progress_hooks": [hook],
        }
        # 分辨率筛选
        if self.options.resolution != "source":
            ydl_opts["format"] = f"best[height<={self.options.resolution[:-1]}]/best"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))
        # yt-dlp 会按输出模板改后缀,找一下
        for ext in (self.options.fmt, "mp4", "mkv", "ts", "webm"):
            p = target.with_suffix(f".{ext}")
            if p.exists():
                return DownloadResult(True, p, engine=EngineKind.YT_DLP.value)
        return DownloadResult(True, target, engine=EngineKind.YT_DLP.value)

    # ---------- native(aiohttp + ffmpeg) ----------
    async def _via_native(self, episode: Episode, url: str, target: Path,
                           on_progress: Callable[[int, int, str], None] | None) -> DownloadResult:
        import aiohttp
        if url.endswith(".m3u8") or "m3u8" in url:
            return await self._native_hls(url, target, on_progress)
        return await self._native_single(url, target, on_progress)

    async def _native_single(self, url: str, target: Path,
                              on_progress: Callable[[int, int, str], None] | None) -> DownloadResult:
        import aiohttp
        # 支持断点续传
        pos = target.stat().st_size if target.exists() else 0
        headers = {"Range": f"bytes={pos}-"} if pos else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0)) + pos
                with target.open("ab" if pos else "wb") as f:
                    written = pos
                    async for chunk in r.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(written, total, "downloading")
        return DownloadResult(True, target, engine=EngineKind.NATIVE.value)

    async def _native_hls(self, url: str, target: Path,
                           on_progress: Callable[[int, int, str], None] | None) -> DownloadResult:
        import aiohttp
        from urllib.parse import urljoin
        ts_dir = target.with_name(target.stem + "_ts")
        ts_dir.mkdir(parents=True, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                m3u8_text = await r.text()
            segs = []
            base = url.rsplit("/", 1)[0] + "/"
            for line in m3u8_text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    segs.append(urljoin(base, line))

            sem = asyncio.Semaphore(self.options.concurrency)
            async def fetch(idx, u):
                async with sem:
                    async with session.get(u) as r2:
                        ts = ts_dir / f"{idx:05d}.ts"
                        ts.write_bytes(await r2.read())
                    if on_progress:
                        # 进度粗略估计
                        done = sum(p.stat().st_size for p in ts_dir.glob("*.ts"))
                        on_progress(done, done, "downloading")

            await asyncio.gather(*(fetch(i, u) for i, u in enumerate(segs)))

        # ffmpeg 合并
        ff = ffmpeg_path()
        if ff is None:
            raise RuntimeError("未找到 ffmpeg(打包内 / 本地 / PATH 都没有)")
        list_file = ts_dir / "_list.txt"
        list_file.write_text("\n".join(f"file '{p.name}'" for p in sorted(ts_dir.glob("*.ts"))))
        subprocess.run(
            [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c", "copy", str(target)],
            check=True, capture_output=True,
        )
        for p in ts_dir.glob("*.ts"):
            p.unlink()
        list_file.unlink()
        ts_dir.rmdir()
        return DownloadResult(True, target, engine=EngineKind.NATIVE.value)

    @staticmethod
    def _safe(s: str) -> str:
        return "".join(c for c in s if c.isalnum() or c in "._- ")