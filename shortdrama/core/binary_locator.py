"""二进制路径定位 - 找 aria2c / ffmpeg 的可执行位置。

打包后(单文件 .exe):
    sys._MEIPASS 指向 PyInstaller 解压临时目录
    → bin/aria2c.exe / bin/ffmpeg.exe

源码运行时:
    优先 assets/bin/(本地下载的)
    fallback 到系统 PATH(用户自己装到 PATH 的)

也支持 dev/调试:开发时把二进制放到 assets/bin/ 就直接用,不用污染系统 PATH。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


# 项目根 = shortdrama/core/binary_locator.py → 父目录的父目录的父目录
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_BIN = REPO_ROOT / "assets" / "bin"


def _bundled(name: str) -> Path | None:
    """PyInstaller 打包后的临时目录(sys._MEIPASS)。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass) / "bin" / name
        if p.exists():
            return p
    return None


def _local(name: str) -> Path | None:
    """本地开发:assets/bin/。"""
    p = LOCAL_BIN / name
    if p.exists():
        return p
    return None


def resolve_binary(name: str, *, fallback_to_path: bool = True) -> str | None:
    """按优先级查找二进制。

    Args:
        name: 完整可执行文件名,如 "aria2c.exe" / "ffmpeg.exe"(Windows)
              或 "aria2c" / "ffmpeg"(POSIX)
        fallback_to_path: 找不到本地时是否走系统 PATH

    Returns:
        完整路径字符串(给 subprocess 用)或 PATH 里的可执行文件名,
        完全找不到时返回 None。
    """
    # 1. 打包后的临时目录(单文件 .exe 启动时解压)
    p = _bundled(name)
    if p:
        return str(p)
    # 2. 本地 assets/bin(开发用)
    p = _local(name)
    if p:
        return str(p)
    # 3. 系统 PATH
    if fallback_to_path:
        which = shutil.which(name)
        if which:
            return which
    return None


def _win_name(plain: str) -> str:
    return f"{plain}.exe" if os.name == "nt" else plain


def aria2_path() -> str | None:
    """aria2c 可执行路径(跨平台后缀)。"""
    return resolve_binary(_win_name("aria2c"))


def ffmpeg_path() -> str | None:
    """ffmpeg 可执行路径(跨平台后缀)。"""
    return resolve_binary(_win_name("ffmpeg"))


def is_installed(binary_name: str) -> bool:
    """兼容旧 API:检查二进制是否可用(传入 "aria2c" / "ffmpeg" 不带 .exe)。"""
    return resolve_binary(_win_name(binary_name)) is not None