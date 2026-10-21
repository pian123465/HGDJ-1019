@echo off
REM Windows 11 一键构建脚本
REM Usage: double-click build.bat, wait 3-5 minutes, get dist\shortdrama-dl.exe
REM       (bundles Python runtime + aria2c + ffmpeg, ~200 MB single file)
REM
REM Outputs:
REM   dist\shortdrama-dl.exe                       -- single-file exe (PyInstaller)
REM   installer_output\Setup-Shortdrama-0.3.exe    -- installer (needs Inno Setup)

setlocal enabledelayedexpansion

REM === Windows console encoding fix(v0.6)====================================
REM cmd's default code page is 437/cp936, mixed encoding. Force utf-8 here.
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
REM Every python call below passes `-X utf8`, so it cannot crash on encoding
REM even if chcp / the env vars get lost.
REM ===========================================================================

echo =========================================
echo  Short Drama Downloader - Windows build
echo =========================================

REM 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not installed. Download 3.10+ from https://www.python.org
    echo     Remember to check "Add Python to PATH" during install
    pause
    exit /b 1
)

REM 2. Create venv
if not exist ".venv" (
    echo [1/7] Creating venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] venv creation failed
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate

REM 3. Install deps
echo [2/7] Installing deps...
pip install --upgrade pip -q
if errorlevel 1 (
    echo [X] pip upgrade failed
    pause
    exit /b 1
)
pip install pyinstaller -q
if errorlevel 1 (
    echo [X] install pyinstaller failed
    pause
    exit /b 1
)
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [X] install deps failed
    pause
    exit /b 1
)

REM 4. Check icon
echo [3/7] Checking icon...
if not exist "assets\icon.ico" (
    where convert >nul 2>&1
    if not errorlevel 1 (
        python -X utf8 tools\build_icon.py
    ) else (
        echo [WARN] ImageMagick not found, skipping icon generation.
        echo        Manually place icon at assets\icon.ico
    )
) else (
    echo    icon exists, skip
)

REM 5. Extract / check binaries (bundled in repo, local-first, download on miss)
echo [4/7] Checking aria2c + ffmpeg...
python -X utf8 tools\setup_binaries.py
if errorlevel 1 (
    echo [X] Binary preparation failed. Check assets/bin/binaries.tar.gz integrity
    pause
    exit /b 1
)

REM 6. PyInstaller build
echo [5/7] PyInstaller build (3-5 min)...
python -X utf8 -m PyInstaller shortdrama.spec --clean --noconfirm
if errorlevel 1 (
    echo [X] Build failed
    pause
    exit /b 1
)

REM 7. Optional Inno Setup installer
echo [6/7] Checking Inno Setup...
where iscc >nul 2>&1
if not errorlevel 1 (
    echo [7/7] Building installer...
    iscc installer.iss
    if errorlevel 1 (
        echo [WARN] Inno Setup failed, skipping installer generation
    )
) else (
    echo [INFO] Inno Setup Compiler not installed (https://jrsoftware.org)
    echo        exe ready: dist\shortdrama-dl.exe
    echo        Install Inno Setup then run iscc installer.iss for installer
)

echo.
echo =========================================
echo  Build complete!
echo =========================================
echo  Run:    dist\shortdrama-dl.exe
echo  Size:   ~200 MB (bundles Python + aria2c + ffmpeg)
if exist installer_output\Setup-Shortdrama-0.3.exe (
    echo  Install: installer_output\Setup-Shortdrama-0.3.exe
)
echo =========================================
echo.
pause

endlocal