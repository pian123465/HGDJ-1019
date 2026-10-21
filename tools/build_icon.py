"""把 SVG 渲染成多尺寸 ICO。

需要:ImageMagick (convert) 或 Inkscape 已安装,本脚本会优先用 convert。

用法:
    python -X utf8 tools/build_icon.py
"""
from pathlib import Path
import subprocess
import sys

# --- Windows 控制台编码 fix(v0.6)============================================
# 双击 cmd / CI 里跑本脚本时,stdout 可能是 cp1252 或 cp936,
# print 中文或 "✓"(U+2713,cp936 里没有这个码位)会 UnicodeEncodeError 崩掉。
# 统一先切 utf-8 + errors="replace",下面所有 print 也都改成纯 ASCII。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # 老 Python / 非 CPython:跳过(print 全 ASCII,照样安全)
# ==============================================================================

HERE = Path(__file__).parent.parent
ASSETS = HERE / "assets"
SVG = ASSETS / "icon.svg"
ICO = ASSETS / "icon.ico"

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_via_convert(svg: Path) -> list[Path]:
    """用 ImageMagick 把 SVG 转成多尺寸 PNG。"""
    out = []
    for sz in SIZES:
        p = ASSETS / f"icon-{sz}.png"
        subprocess.run([
            "convert", "-background", "none", "-density", "384",
            str(svg), "-resize", f"{sz}x{sz}", str(p),
        ], check=True)
        out.append(p)
    return out


def pack_ico(pngs: list[Path], ico: Path):
    """用 ImageMagick 把多张 PNG 打包成 ICO。"""
    subprocess.run(["convert", *[str(p) for p in pngs], str(ico)], check=True)


def render_via_pillow(svg: Path) -> list[Path]:
    """用 cairosvg + PIL 转 PNG,做 fallback。"""
    try:
        import cairosvg
        from io import BytesIO
        from PIL import Image
    except ImportError:
        print("need cairosvg + Pillow", file=sys.stderr)
        raise
    raw = svg.read_bytes()
    out = []
    for sz in SIZES:
        png_bytes = cairosvg.svg2png(bytestring=raw, output_width=sz, output_height=sz)
        p = ASSETS / f"icon-{sz}.png"
        p.write_bytes(png_bytes)
        out.append(p)
    return out


def main():
    if not SVG.exists():
        print(f"[X] svg not found: {SVG}", file=sys.stderr)
        sys.exit(1)

    # 优先 ImageMagick
    try:
        pngs = render_via_convert(SVG)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[WARN] ImageMagick failed, trying cairosvg ...")
        pngs = render_via_pillow(SVG)

    pack_ico(pngs, ICO)
    print(f"[OK] {ICO} ({ICO.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()