# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 - 在 Windows 11 上构建 .exe

构建命令:
    pip install pyinstaller
    python -X utf8 -m PyInstaller shortdrama.spec --clean --noconfirm

输出:
    dist/shortdrama-dl.exe  (单文件,自带 Python 运行时)
"""

import os
import sys
from pathlib import Path

# --- Windows runner 编码 fix(v0.6)============================================
# GitHub Actions 的 windows runner 用 PowerShell 7,stdout 默认是 cp1252。
# spec 本身是 Python 脚本,print 任何非 ASCII 字符都会 UnicodeEncodeError
# 直接把整个 PyInstaller 构建搞挂(和 tools/setup_binaries.py 是同一个坑)。
# 这里把 stdout/stderr 强制切 utf-8,errors="replace" 兜底。
# 注意:本 spec 不能 import 项目内模块(构建时 sys.path 未必包含仓库根),
# 所以这里保持自包含。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # 老 Python / 非 CPython:跳过(下面的 print 全是 ASCII,照样安全)
# ==============================================================================


block_cipher = None

# 跨平台定位图标(Windows / Linux / macOS 都能找到)
ICON_PATH = os.path.join('assets', 'icon.ico')
ICON_PATH = ICON_PATH if Path(ICON_PATH).exists() else None

# 添加所有第三方库(避免运行时缺包)
EXCLUDES = [
    "tkinter", "matplotlib", "numpy.tests", "pytest",
    "scipy", "pandas", "PIL.ImageQt",
]

# 资源文件
datas = [
    ("shortdrama/plugins", "shortdrama/plugins"),  # 用户签名插件
]

# 外部二进制(aria2c + ffmpeg,如果 assets/bin/ 下存在则打包进去)
# 注意:
#   - BtbN shared 版 ffmpeg 需要同目录的 .dll(avcodec-63.dll 等),
#     所以这里要把 .exe 和 .dll 都收集起来,统一打到 bin/ 下。
#   - 仓库自带的 binaries.tar.gz(setup_binaries.py 启动时会自动解压)
#     不应该被打包进 PyInstaller(它是压缩包不是可执行文件)。
#   - 临时 zip 残留(_aria2.zip / _ffmpeg.zip / _*.tmp)也跳过。
_bin_dir = os.path.join('assets', 'bin')
binaries = []
if os.path.isdir(_bin_dir):
    for fname in os.listdir(_bin_dir):
        if fname.startswith('_'):  # _aria2.zip / _ffmpeg.zip / _*.tmp
            continue
        if fname.endswith('.tar.gz') or fname.endswith('.zip'):  # 仓库自带的压缩包
            continue
        # Windows:所有 .exe + .dll;POSIX:aria2c / ffmpeg 无后缀
        is_win_binary = os.name == 'nt' and (fname.endswith('.exe') or fname.endswith('.dll'))
        is_posix_binary = os.name != 'nt' and fname in ('aria2c', 'ffmpeg')
        if is_win_binary or is_posix_binary:
            binaries.append((os.path.join(_bin_dir, fname), 'bin'))
    if binaries:
        # [v0.6] 这行原来是中文 print,cp1252 控制台下会 UnicodeEncodeError,
        # 而它是 PyInstaller 构建期第一个 print -> 一崩整个 build 挂掉。
        # 已改成纯 ASCII,不再依赖任何编码设置。
        print(f"[spec] packing external binaries into bin/: {[os.path.basename(b[0]) for b in binaries]}")

# 隐藏导入(动态加载的模块)
hiddenimports = [
    "shortdrama.core.aria2_client",
    "shortdrama.core.base",
    "shortdrama.core.binary_locator",
    "shortdrama.core.downloader",
    "shortdrama.core.link_parser",
    "shortdrama.core.orchestrator",
    "shortdrama.core.share_resolver",
    "shortdrama.core.signature",
    "shortdrama.core.task_store",
    "shortdrama.core.hongguo_client",   # 红果内核移植(v0.6-hongguo)
    "shortdrama.core.hongguo_crypto",   # 红果内核移植(v0.6-hongguo)
    "shortdrama.platforms.hongguo",     # 红果内核移植(v0.6-hongguo)
    "shortdrama.platforms._template",
    "shortdrama.plugins.signatures",
    "shortdrama.apple_style",
    # PyQt6 子模块(防止部分版本 hook 漏抓)
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.sip",
    # yt-dlp 异步支持
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.downloader",
]

a = Analysis(
    ['shortdrama/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='shortdrama-dl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 压缩可执行文件
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # GUI 模式(无黑窗口)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)