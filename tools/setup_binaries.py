"""管理 aria2c + ffmpeg 二进制,放在 assets/bin/。

默认行为:**本地优先**。如果 assets/bin/ 下已经有对应的二进制,直接跳过;
只有缺失时才下载(给"clone 仓库但漏掉 assets/bin/ "的人用)。

仓库里把 10 个二进制打成 `binaries.tar.gz`(75MB,< 100MB 可直接 git push)一起发,
运行时会自动解压到 assets/bin/。Windows runner 一般不用下载外网。

用法:
    python -X utf8 tools/setup_binaries.py                # 解压 tar.gz(如有)+ 缺啥下啥
    python -X utf8 tools/setup_binaries.py --force        # 强制重新下载,忽略本地
    python -X utf8 tools/setup_binaries.py --only-aria2   # 只处理 aria2c
    python -X utf8 tools/setup_binaries.py --only-ffmpeg  # 只处理 ffmpeg
    python -X utf8 tools/setup_binaries.py --status       # 只检查本地,不下载

下载源(都基于 GitHub CDN;Windows runner 访问 BtbN/Gyan 经常不稳):
    aria2c : github.com/aria2/aria2/releases(官方 release zip,GitHub CDN 极稳)
    ffmpeg : github.com/BtbN/FFmpeg-Builds(主,GitHub CDN 极稳)
             + www.gyan.dev/ffmpeg/builds(备,URL 偶尔 503)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import requests


# === Windows PowerShell stdout 兼容性 fix ====================================
# Windows runner 默认 PowerShell 7 (pwsh) 的 stdout 是 cp1252 编码,
# 直接 print 中文/emoji 会触发 UnicodeEncodeError 让脚本崩。
# 这里强制把 stdout/stderr 切到 utf-8。Python 3.7+ 都支持 reconfigure。
#
# 注意:
#   - `errors="replace"` 保证遇到极端编码不上的字符也不会崩,只是显示成 ?
#   - 用 try/except 兜底,防止老 Python 或非 CPython 实现出问题
def _fix_io_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            # Python < 3.7 / 非 CPython,跳过
            pass


_fix_io_encoding()
# ============================================================================


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_ROOT / "assets" / "bin"

# 仓库自带的 binaries 压缩包(75MB,GitHub 单文件 100MB 限制以内)
# 启动时检测到就自动解压,然后删掉压缩包(working tree 干净)
BUNDLE_NAME = "binaries.tar.gz"

# aria2c 官方 Win64 release
# zip 内唯一路径:aria2-1.37.0-win-64bit-build1/aria2c.exe
ARIA2_VERSION = "1.37.0"
ARIA2_URL = (
    f"https://github.com/aria2/aria2/releases/download/release-{ARIA2_VERSION}/"
    f"aria2-{ARIA2_VERSION}-win-64bit-build1.zip"
)

# ffmpeg 主源(BtbN GPL-shared,自带 dll,ffmpeg.exe + avcodec 等,体积约 80MB zip)
# 备源(Gyan essentials,只下 ffmpeg.exe 体积小但 URL 偶尔 503)
#
# 用 shared 版是因为:这套 ffmpeg.exe 自己很小(~540KB),主要代码在 avcodec-63.dll(114MB)
# shared 版本跟 static 版本总大小差不多,但 spec 处理多文件本来就行
FFMPEG_URLS = [
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]

# ffmpeg shared 版需要的 dll 列表(BtbN gpl-shared zip 内路径固定)
# 用 static 版(Gyan essentials)不需要 dll,自动跳过
FFMPEG_REQUIRED_DLLS = (
    "avcodec-63.dll",
    "avformat-63.dll",
    "avutil-61.dll",
    "swscale-10.dll",
    "swresample-7.dll",
    "avfilter-12.dll",
    "avdevice-63.dll",
)


def _maybe_extract_bundle() -> bool:
    """如果 assets/bin/binaries.tar.gz 存在,自动解压到 TARGET_DIR 后删除压缩包。

    返回:是否执行了解压(用于打日志)。
    """
    bundle = TARGET_DIR / BUNDLE_NAME
    if not bundle.exists():
        return False

    print(f"  [PKG] found {BUNDLE_NAME} ({bundle.stat().st_size // 1024 // 1024} MB), extracting...")
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(bundle, "r:gz") as tf:
            tf.extractall(TARGET_DIR)
    except Exception as e:
        # 解压失败,保留压缩包以便排查
        print(f"  [X] extract failed: {e}")
        raise

    # 解压成功就删压缩包(working tree 干净)
    bundle.unlink()
    print(f"  [OK] extract done, removed {BUNDLE_NAME}")
    return True


def _is_already_present() -> dict[str, bool]:
    """检查本地二进制是否齐全。返回 {filename: exists}。"""
    is_win = os.name == "nt"
    expected = {
        "aria2c.exe" if is_win else "aria2c": False,
        "ffmpeg.exe" if is_win else "ffmpeg": False,
    }
    if TARGET_DIR.exists():
        for fname in expected:
            expected[fname] = (TARGET_DIR / fname).exists()
        # shared 版还需要 dll;static 版不需要
        for dll in FFMPEG_REQUIRED_DLLS:
            expected[dll] = (TARGET_DIR / dll).exists()
    return expected


def _download(url: str, dst: Path, chunk: int = 1 << 20, retries: int = 3) -> None:
    """流式下载,带进度 + 重试 + 指数退避。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        print(f"  [OK] {dst.name} exists ({dst.stat().st_size // 1024} KB), skip")
        return

    print(f"  [DL] {url}")
    print(f"    -> {dst}")
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=300, allow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                with dst.open("wb") as f:
                    for chunk_data in r.iter_content(chunk_size=chunk):
                        f.write(chunk_data)
                        done += len(chunk_data)
                        if total:
                            pct = done * 100 // total
                            print(f"    [try {attempt}/{retries}] {pct:3d}%  {done // 1024} / {total // 1024} KB", end="\r")
                if total:
                    print()
                if total and dst.stat().st_size != total:
                    raise RuntimeError(f"size mismatch: expected {total}, got {dst.stat().st_size}")
                return
        except Exception as e:
            last_err = e
            print(f"\n    [!] attempt {attempt}/{retries} failed: {e}")
            if dst.exists():
                dst.unlink()
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed ({retries} retries): {url} -> {last_err}")


def _extract_member(zip_path: Path, member: str, dst: Path) -> None:
    """从 zip 里抽一个指定成员到 dst。"""
    with zipfile.ZipFile(zip_path) as zf:
        if member not in zf.namelist():
            raise FileNotFoundError(f"{zip_path.name} has no member {member!r}")
        with zf.open(member) as src, dst.open("wb") as out:
            shutil.copyfileobj(src, out)
    dst.chmod(0o755 if os.name != "nt" else 0o777)


def fetch_aria2(force: bool = False) -> Path:
    """获取 aria2c 二进制。force=True 时强制重新下载。"""
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    is_win = os.name == "nt"
    fname = "aria2c.exe" if is_win else "aria2c"
    dst = TARGET_DIR / fname

    if dst.exists() and not force:
        print(f"  [OK] {fname} exists ({dst.stat().st_size // 1024} KB), skip")
        return dst

    zip_path = TARGET_DIR / "_aria2.zip"
    try:
        if force and zip_path.exists():
            zip_path.unlink()
        _download(ARIA2_URL, zip_path)
        # aria2 zip 内路径:aria2-1.37.0-win-64bit-build1/aria2c.exe
        member_dir = "win-64bit-build1" if is_win else "linux"
        # 用通配找出 .exe(忽略大小写差异、linux 上没有 .exe 后缀)
        with zipfile.ZipFile(zip_path) as zf:
            candidates = [
                m for m in zf.namelist()
                if member_dir in m and (m.endswith("/aria2c.exe") or m.endswith("/aria2c"))
            ]
            if not candidates:
                raise FileNotFoundError(
                    f"{zip_path.name} has no aria2c under {member_dir}\n"
                    f"first 10 members: {zf.namelist()[:10]}"
                )
            target_member = sorted(candidates, key=len)[0]
        print(f"  [PKG] extracting {target_member} -> {fname}")
        _extract_member(zip_path, target_member, dst)
        print(f"    [OK] {dst} ({dst.stat().st_size // 1024} KB)")
    finally:
        zip_path.unlink(missing_ok=True)
    return dst


def fetch_ffmpeg(force: bool = False) -> list[Path]:
    """获取 ffmpeg 二进制及其依赖 dll(shared 版)。force=True 时强制重新下载。

    返回所有放进去的文件路径列表。
    """
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    is_win = os.name == "nt"
    fname = "ffmpeg.exe" if is_win else "ffmpeg"
    dst = TARGET_DIR / fname

    # 已经有就跳过
    if dst.exists() and not force:
        present = [d for d in [fname] + (list(FFMPEG_REQUIRED_DLLS) if is_win else [])
                   if (TARGET_DIR / d).exists()]
        print(f"  [OK] ffmpeg exists ({dst.stat().st_size // 1024} KB), {len(present)} files ready, skip")
        return [TARGET_DIR / p for p in present]

    zip_path = TARGET_DIR / "_ffmpeg.zip"
    try:
        if force and zip_path.exists():
            zip_path.unlink()
        last_err = None
        for url in FFMPEG_URLS:
            try:
                _download(url, zip_path)
                with zipfile.ZipFile(zip_path) as zf:
                    names = zf.namelist()
                    # BtbN shared: .../bin/ffmpeg.exe + .../bin/avcodec-63.dll 等
                    # Gyan essentials: .../bin/ffmpeg.exe(只 1 个,static,不要 dll)
                    is_btbn_shared = any("bin/avcodec-63.dll" in n for n in names)
                    is_gyan_essentials = "ffmpeg-release-essentials" in url

                    if is_btbn_shared:
                        # 抽出 ffmpeg.exe + ffprobe.exe + 必需 dll
                        target_bin_dir = "bin/"
                        files_to_extract = [fname]
                        if is_win:
                            files_to_extract.append("ffprobe.exe")
                            files_to_extract.extend(FFMPEG_REQUIRED_DLLS)
                        extracted: list[Path] = []
                        for f in files_to_extract:
                            member = None
                            for n in names:
                                if n.endswith(target_bin_dir + f) or n.endswith("/" + f) and target_bin_dir in n:
                                    member = n
                                    break
                            if member is None:
                                # 再放宽:任何含 /bin/ 的成员,文件名匹配
                                for n in names:
                                    if "/bin/" in n and n.rsplit("/", 1)[-1] == f:
                                        member = n
                                        break
                            if member is None:
                                raise FileNotFoundError(
                                    f"{zip_path.name} has no bin/{f}\n"
                                    f"first 10 members: {names[:10]}"
                                )
                            out = TARGET_DIR / f
                            print(f"  [PKG] extracting {member} -> {f}")
                            _extract_member(zip_path, member, out)
                            print(f"    [OK] {out} ({out.stat().st_size // 1024} KB)")
                            extracted.append(out)
                        return extracted

                    elif is_gyan_essentials:
                        # Gyan essentials 是 static 版,只抽 ffmpeg.exe
                        # 路径形如:ffmpeg-7.1-essentials_build/bin/ffmpeg.exe
                        ffmpeg_member = None
                        for n in names:
                            if n.endswith("/bin/ffmpeg.exe") or n.endswith("/bin/ffmpeg"):
                                ffmpeg_member = n
                                break
                        if ffmpeg_member is None:
                            raise FileNotFoundError(
                                f"{zip_path.name} has no bin/ffmpeg.exe\n"
                                f"first 10 members: {names[:10]}"
                            )
                        print(f"  [PKG] extracting {ffmpeg_member} -> {fname} (Gyan static, no dlls needed)")
                        _extract_member(zip_path, ffmpeg_member, dst)
                        print(f"    [OK] {dst} ({dst.stat().st_size // 1024} KB)")
                        return [dst]
                    else:
                        raise RuntimeError(f"unknown ffmpeg zip structure, first 10 members: {names[:10]}")

            except Exception as e:
                last_err = e
                print(f"  [!] this source failed: {e}")
                zip_path.unlink(missing_ok=True)
                # 失败时清掉半成品
                for f in [fname, "ffprobe.exe"] + (list(FFMPEG_REQUIRED_DLLS) if is_win else []):
                    p = TARGET_DIR / f
                    if p.exists():
                        p.unlink()
                continue
        raise RuntimeError(f"all ffmpeg sources failed: {last_err}")
    finally:
        zip_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="manage aria2c + ffmpeg binaries (local-first, download on miss)")
    parser.add_argument("--force", action="store_true", help="force re-download, ignore local")
    parser.add_argument("--only-aria2", action="store_true", help="only handle aria2c")
    parser.add_argument("--only-ffmpeg", action="store_true", help="only handle ffmpeg")
    parser.add_argument("--status", action="store_true", help="only check local binaries, no download")
    args = parser.parse_args()

    print("=========================================")
    print(" check aria2c + ffmpeg binaries")
    print("=========================================")
    print(f"target dir: {TARGET_DIR}")
    print(f"platform:   {os.name} ({sys.platform})")
    print(f"strategy:   {'force-redownload' if args.force else 'local-first, download on miss'}")
    # v0.6:把最终生效的 stdout 编码打进日志。
    # 下次再挂的话,看这一行就知道是编码问题还是别的问题(应该永远是 utf-8;
    # 万一不是,脚本里下面的 print 也全是 ASCII,不会 UnicodeEncodeError)。
    print(f"io encoding: stdout={getattr(sys.stdout, 'encoding', None)} "
          f"stderr={getattr(sys.stderr, 'encoding', None)}")
    print()

    # 先解压仓库自带的 binaries.tar.gz(如存在)
    if not args.force:
        try:
            _maybe_extract_bundle()
        except Exception as e:
            print(f"  [!] extracting bundled binaries.tar.gz failed: {e}")
            print(f"      will try network download (BtbN/Gyan), may be slow or fail")
    print()

    if args.status:
        present = _is_already_present()
        for fname, exists in present.items():
            mark = "[OK]" if exists else "[X]"
            print(f"  {mark} {fname}")
        return 0 if all(present.values()) else 1

    do_aria2 = not args.only_ffmpeg
    do_ffmpeg = not args.only_aria2

    if do_aria2:
        print("> aria2c")
        fetch_aria2(force=args.force)
        print()
    if do_ffmpeg:
        print("> ffmpeg")
        fetch_ffmpeg(force=args.force)
        print()

    print("=========================================")
    print(" status")
    print("=========================================")
    present = _is_already_present()
    for fname, exists in present.items():
        mark = "[OK]" if exists else "[X]"
        size = (TARGET_DIR / fname).stat().st_size // 1024 if exists else 0
        print(f"  {mark} {fname}  ({size} KB)")

    all_ok = all(present[k] for k in [f"aria2c{'.exe' if os.name == 'nt' else ''}",
                                       f"ffmpeg{'.exe' if os.name == 'nt' else ''}"]
                 if k in present)
    if all_ok:
        print("\n[OK] all binaries ready. PyInstaller will pack them into the .exe.")
        return 0
    print("\n[X] some binaries missing, [X] items above need re-download.")
    return 1


if __name__ == "__main__":
    sys.exit(main())