"""aria2 JSON-RPC 客户端。

aria2c 是命令行下载工具,支持多线程、断点续传、HLS/M3U8、磁力链等。
我们用 JSON-RPC 控制它(aria2c --enable-rpc 启动后监听 6800)。

二进制路径查找:binary_locator(优先打包临时目录 → 本地 assets/bin → 系统 PATH)。
不需要 aria2 时,DownloadEngine 会自动回落到自研引擎。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import requests
from loguru import logger

from .binary_locator import aria2_path


class Aria2Client:
    """aria2c 控制封装。
    用法:
        cli = Aria2Client()
        cli.start_daemon()                  # 自动拉起 aria2c
        gid = cli.add_uri(url, out="x.mp4") # 加任务,返回 gid
        while not cli.is_complete(gid):     # 轮询状态
            s = cli.tell_status(gid)
            ...
    """

    DEFAULT_RPC_PORT = 6800
    DEFAULT_RPC_SECRET = ""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_RPC_PORT, secret: str = DEFAULT_RPC_SECRET):
        self.host = host
        self.port = port
        self.secret = secret
        self.rpc_url = f"http://{host}:{port}/jsonrpc"
        self._proc: subprocess.Popen | None = None

    # ---------- 检测与启动 ----------
    @staticmethod
    def is_installed() -> bool:
        """检查 aria2c 是否可用(打包内 / 本地 assets/bin / 系统 PATH 任何一处)。"""
        return aria2_path() is not None

    def is_running(self) -> bool:
        try:
            r = requests.post(self.rpc_url, json={
                "jsonrpc": "2.0", "id": "1", "method": "aria2.getVersion",
                "params": [f"token:{self.secret}"] if self.secret else [],
            }, timeout=2)
            return r.ok
        except Exception:
            return False

    def start_daemon(self, downloads_dir: str = "./downloads") -> bool:
        """拉起一个 aria2c 后台进程(我们管理的,不要重复启)。"""
        if not self.is_installed():
            logger.warning("未找到 aria2c(打包 / 本地 / PATH 都没有)")
            return False
        if self.is_running():
            return True
        Path(downloads_dir).mkdir(parents=True, exist_ok=True)
        cmd = [
            aria2_path(),
            "--enable-rpc=true",
            f"--rpc-listen-port={self.port}",
            f"--rpc-listen-all=false",
            f"--rpc-allow-origin-all=true",
            f"--dir={downloads_dir}",
            "--auto-file-renaming=false",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--summary-interval=1",
            "--console-log-level=warn",
            "--daemon=true",
        ]
        if self.secret:
            cmd.append(f"--rpc-secret={self.secret}")
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            logger.error("找不到 aria2c")
            return False
        # 等 daemon 起来
        for _ in range(20):
            if self.is_running():
                logger.info(f"aria2c 启动成功 -> {self.rpc_url} (binary={aria2_path()})")
                return True
            time.sleep(0.2)
        return False

    # ---------- 任务管理 ----------
    def _call(self, method: str, params: list | None = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(int(time.time() * 1000)),
            "method": method,
            "params": ([f"token:{self.secret}"] if self.secret else []) + (params or []),
        }
        r = requests.post(self.rpc_url, json=payload, timeout=10)
        r.raise_for_status()
        return r.json().get("result", {})

    def add_uri(self, url: str, out: str, dir_: str | None = None,
                header: list[str] | None = None,
                on_progress: Callable[[dict], None] | None = None) -> str:
        """加下载任务。header 是 ['User-Agent: ...', 'Referer: ...'] 这种。"""
        options = {"out": out}
        if dir_:
            options["dir"] = dir_
        if header:
            options["header"] = header
        gid = self._call("aria2.addUri", [[url], options])["gid"]
        return gid

    def tell_status(self, gid: str) -> dict:
        keys = ["status", "totalLength", "completedLength", "downloadSpeed",
                "errorMessage", "dir", "files", "bittorrent"]
        return self._call("aria2.tellStatus", [gid, keys])

    def remove(self, gid: str) -> bool:
        try:
            return self._call("aria2.removeDownloadResult", [gid]) == "OK"
        except Exception:
            return False

    def pause(self, gid: str) -> None:
        self._call("aria2.pause", [gid])

    def resume(self, gid: str) -> None:
        self._call("aria2.unpause", [gid])

    def is_complete(self, gid: str) -> bool:
        return self.tell_status(gid).get("status") == "complete"

    def is_error(self, gid: str) -> tuple[bool, str]:
        s = self.tell_status(gid)
        return s.get("status") == "error", s.get("errorMessage", "")

    def wait_complete(self, gid: str, on_progress: Callable[[dict], None] | None = None) -> bool:
        """轮询到完成。"""
        while True:
            s = self.tell_status(gid)
            st = s.get("status")
            if on_progress:
                on_progress(s)
            if st == "complete":
                return True
            if st == "error":
                logger.error(f"下载失败: {s.get('errorMessage')}")
                return False
            if st == "removed":
                return False
            time.sleep(1)