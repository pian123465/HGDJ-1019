"""[v0.6] Build-time guard: build scripts must not print non-ASCII text.

Why this exists
---------------
GitHub Actions' windows runner runs PowerShell 7, whose stdout is cp1252.
Any Python script in the *build path* that prints a non-ASCII character
(CJK text, emoji, "✓", "→" ...) dies with

    File "...\\encodings\\cp1252.py", line 19, in encode
    UnicodeEncodeError: 'charmap' codec can't encode characters in position ...

and takes the whole build down. That is exactly how build #8 died
(tools/setup_binaries.py line 168).

The scripts already call sys.stdout.reconfigure() + print pure ASCII, so this
check is the third layer: it fails the build *early and clearly* if somebody
adds a Chinese print() back, instead of letting it blow up 40 lines into a
half-finished PyInstaller run.

Usage:
    python -X utf8 tools/check_ascii_prints.py            # check the whole repo
    python -X utf8 tools/check_ascii_prints.py path/...   # check specific paths

Exit code: 0 = clean, 1 = offending prints found.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 只查构建路径上的脚本:这些文件会在 CI / build.bat 里被执行。
# 业务代码 (shortdrama/**) 不查 —— 打包后是 GUI 程序,console=False,
# sys.stdout 是 None,print 是空操作,不受 cp1252 影响。
BUILD_PATH_FILES = (
    "tools/setup_binaries.py",
    "tools/build_icon.py",
    "tools/analyze_mitm.py",
    "shortdrama.spec",
)


def _non_ascii_chars(text: str) -> str:
    return "".join(sorted({c for c in text if ord(c) > 127}))


def check_file(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(行号, 命中的非 ASCII 字符, 上下文)]。"""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [(-1, f"<syntax error: {e}>", "")]

    findings: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    bad = _non_ascii_chars(sub.value)
                    if bad:
                        ctx = sub.value.replace("\n", "\\n")[:48]
                        findings.append((sub.lineno, bad, ctx))
    # argparse 的 help/description 最终也会被 print 到 stdout,一起查
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_argument":
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            bad = _non_ascii_chars(sub.value)
                            if bad:
                                ctx = sub.value[:48]
                                findings.append((sub.lineno, bad, ctx))
    return findings


def main() -> int:
    if len(sys.argv) > 1:
        targets = [Path(a) for a in sys.argv[1:]]
    else:
        targets = [REPO_ROOT / rel for rel in BUILD_PATH_FILES]

    total = 0
    for path in targets:
        if not path.exists():
            print(f"[SKIP] not found: {path}")
            continue
        findings = check_file(path)
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        if findings:
            total += len(findings)
            print(f"[X] {rel}")
            for lineno, bad, ctx in findings:
                shown = bad.encode("unicode_escape").decode("ascii")
                print(f"      line {lineno}: non-ASCII {shown}  in  {ctx!r}")
        else:
            print(f"[OK] {rel}")

    print()
    if total:
        print(f"[X] {total} non-ASCII print/add_argument found in build-path scripts.")
        print("    On the windows runner stdout is cp1252 -> UnicodeEncodeError -> build dies.")
        print("    Fix: use ASCII text ([OK]/[X]/[WARN]/[PKG] prefixes), or drop the")
        print("         message entirely. Comments/docstrings in Chinese are fine.")
        return 1
    print("[OK] build-path scripts are ASCII-safe for cp1252 stdout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
