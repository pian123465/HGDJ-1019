#!/usr/bin/env bash
# Linux/macOS 本地开发构建(仅打包源码 zip,真正 .exe 必须在 Windows 上构建)
#
# v0.6:export PYTHONIOENCODING/PYTHONUTF8,保证本机 locale 再怪也不会 UnicodeEncodeError

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

set -e
echo "========================================="
echo " Short Drama Downloader - source packaging"
echo "========================================="

# 清理缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# 打源码 zip(供下载)
zip -rq shortdrama-dl-source.zip . \
    -x "*.pyc" "*__pycache__*" \
    -x ".venv/*" "dist/*" "build/*" \
    -x "*.db" ".git/*" "node_modules/*"

echo
echo "[OK] source zip: shortdrama-dl-source.zip"
echo
echo "To build the .exe on Windows:"
echo "  1. unzip the source on Windows 11"
echo "  2. double-click build.bat"
echo "  3. wait 1-3 min, output dist\\shortdrama-dl.exe"
