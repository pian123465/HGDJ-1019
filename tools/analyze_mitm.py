"""mitmproxy / Charles 抓包分析工具。

把抓到的 .flow / .har / .pcapng 文件丢给它,自动:
    1. 找出短剧平台相关的请求(api.* / search / video / play)
    2. 提取签名 header(常见: sign / X-Sign / X-Bogus / a-bogus)
    3. 导出 JSON 报告,方便逆向

依赖:pip install mitmproxy  (或只装这个脚本也行,纯 Python)

用法:
    python -X utf8 tools/analyze_mitm.py dump.flow > report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- Windows 控制台编码 fix(v0.6)============================================
# 抓包分析经常在 Windows cmd / PowerShell 里跑,stdout 默认 cp1252 或 cp936,
# print 中文会 UnicodeEncodeError 崩掉。统一先切 utf-8,下面 print 也全改 ASCII。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # 老 Python / 非 CPython:跳过(print 全 ASCII,照样安全)
# ==============================================================================

# 短剧相关接口关键词
DOMAIN_PATTERNS = re.compile(
    r"(hongguo|hema|duanju|shortplay|xigua|douyin|bytedance|byteic|"
    r"snssdk|amemv|byteicp)\.",
    re.IGNORECASE,
)

PATH_PATTERNS = re.compile(
    r"(/api/|/v[0-9]+/|/api/v\d+/|/search|/video|/play|/drama|/episode|/detail)",
    re.IGNORECASE,
)

SIGN_HEADERS = {"sign", "x-sign", "x-bogus", "a-bogus", "x-livetime", "x-argus",
                "x-auth-signature", "authorization", "x-token", "x-tt-token"}


def analyze_flow_file(path: Path) -> list[dict]:
    """分析 mitmproxy 的 .flow 文件(JSON Lines 格式)。"""
    results = []
    if not path.exists():
        print(f"[X] file not found: {path}", file=sys.stderr)
        return results

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = _parse_mitm_entry(entry, idx=i)
            if r:
                results.append(r)
    return results


def _parse_mitm_entry(entry: dict, idx: int) -> dict | None:
    """mitmproxy flow entry 的结构:
        {
          "type": "request",
          "request": {"method": ..., "url": ..., "headers": [...]},
          "response": {"status_code": ..., "content": {...}}
        }
    """
    if entry.get("type") not in ("request", "http"):
        return None
    req = entry.get("request") or {}
    url = req.get("url", "")
    if not (DOMAIN_PATTERNS.search(url) or PATH_PATTERNS.search(url)):
        return None
    headers = {h["name"].lower(): h["value"] for h in req.get("headers", [])}
    sig_headers = {k: v for k, v in headers.items() if k in SIGN_HEADERS}
    resp = entry.get("response") or {}
    body_preview = ""
    try:
        c = resp.get("content", {})
        text = c.get("text", "")
        if isinstance(text, str) and len(text) < 500:
            body_preview = text
        elif text:
            body_preview = f"<{c.get('size', len(text))} bytes>"
    except Exception:
        pass
    return {
        "idx": idx,
        "method": req.get("method"),
        "url": url,
        "sign_headers": sig_headers,
        "user_agent": headers.get("user-agent", ""),
        "referer": headers.get("referer", ""),
        "status": resp.get("status_code"),
        "body_preview": body_preview,
    }


def main():
    ap = argparse.ArgumentParser(description="short-drama platform mitm capture analyzer")
    # help / description 也必须是 ASCII:argparse 在 --help 时会把它 print 到 stdout,
    # cp1252 控制台下中文 help 会 UnicodeEncodeError
    ap.add_argument("flow", type=Path, help="mitmproxy dump file (.flow)")
    ap.add_argument("--out", type=Path, default=None, help="write JSON report to this path")
    args = ap.parse_args()

    print(f"[>] reading {args.flow} ...", file=sys.stderr)
    results = analyze_flow_file(args.flow)
    print(f"[>] {len(results)} short-drama related requests hit", file=sys.stderr)

    report = {"summary": {"total_hits": len(results)}, "requests": results}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"[>] written to {args.out}", file=sys.stderr)
    else:
        # 直接落到 stdout 的报告:终端 / 重定向文件在 Windows 上可能是
        # cp1252 或 cp936,写中文会 UnicodeEncodeError。
        # 这里用 ensure_ascii=True 输出纯 ASCII(内容仍是合法 JSON,
        # 中文变成 \uXXXX,反序列化后完全一样);写文件那条路保持 utf-8 不变。
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()