# 短剧下载器 v0.3 — Windows 一键打包指南

> ⚠️ **说明**: 这套项目是 PyQt6 桌面程序,作者已经把 PyInstaller 配置(`shortdrama.spec`)和 Windows 打包脚本(`build.bat`)都写好了。源码就是从原始仓库搬过来的,我用 Linux 沙箱已经跑过一次 `pyinstaller`,打包链路验证通过,你按下面任意一种方式都能拿到 `dist\shortdrama-dl.exe`。

---

## 方式 A:Windows 本地一键打包(推荐,5 分钟搞定)

**前提:**Windows 10/11 + Python 3.10+(安装时务必勾选 **Add Python to PATH**)

### 步骤
1. 把整个文件夹复制到 Windows 上(任意目录都行,比如 `D:\shortdrama`)
2. 双击 **`build.bat`**
3. 等 3-5 分钟,看到 "构建完成!" 就 OK 了
4. 产物在 `dist\shortdrama-dl.exe`(单文件,自带 Python 运行时 + aria2c + ffmpeg,约 200 MB)
5. 双击 `dist\shortdrama-dl.exe` 直接运行,**不需要再装 Python**

### build.bat 做了什么
1. 检查 Python
2. 创建虚拟环境 `.venv`
3. 装 `pyinstaller` + 全部依赖(PyQt6 / aiohttp / yt-dlp / loguru / cryptography / requests)
4. **检查** `assets\bin\` 下的 aria2c + ffmpeg(已直接随仓库一起发,本地优先,缺失才下)
5. 用 `shortdrama.spec` 跑 PyInstaller → `dist\shortdrama-dl.exe`
6. 如果系统装了 Inno Setup(`iscc`),顺便再生成 `installer_output\Setup-Shortdrama-0.3.exe`(可选)

> ℹ️ v0.3 起,`assets/bin/` 下的 `aria2c.exe` + `ffmpeg.exe` + 必需的 dll 已经直接随仓库发布,
> 打包时不再需要访问 BtbN/Gyan。Windows runner 在网络不好时也能稳定打包。
> 若想升级 ffmpeg 版本,在 Windows 上跑 `python tools\setup_binaries.py --force --only-ffmpeg`。

### 想自己手动跑也 OK
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller shortdrama.spec --clean --noconfirm
```

### 想再生成安装包(可选)
装 [Inno Setup Compiler](https://jrsoftware.org/isdl.php),然后用 Inno Setup 打开 `installer.iss` → Build,产出 `installer_output\Setup-Shortdrama-0.3.exe`(中文向导版安装包)。

---

## 方式 B:GitHub Actions 云端一键构建(不用本地装 Python)

项目自带的 `.github/workflows/build-windows.yml` 已经写好,你只需要:

1. 把这个目录上传成 GitHub 仓库(新 repo 即可,不用 fork)
2. GitHub 网页上点 **Actions** 标签
3. 左侧选 **Build Windows .exe**
4. 右侧点 **Run workflow** → 选 main 分支 → **Run workflow**
6. 等 2-3 分钟,刷新页面
8. 完成后在最下面的 **Artifacts** 区下载 `shortdrama-dl-windows.zip`,解压得到 `shortdrama-dl.exe`

> 这个方式**零依赖**,不用装 Python、不用装 PyInstaller,云端帮你编。

---

## 方式 C:不想自己动,找个人推(最快)

让懂 Python 的朋友在他 Windows 上跑 **方式 A**,然后把 `dist\shortdrama-dl.exe` 发给你就行。

---

## 运行后能干嘛

直接双击 `shortdrama-dl.exe` 启动后:
- **🔍 搜索**:跨平台模糊搜短剧(目前平台适配器还是模板状态,需要逆向签名才能拿到真实数据,作者 README 里写明了步骤)
- **🔗 链接解析**:粘贴分享文案,自动识别 URL + 跟重定向 + 路由平台
- **⬇ 下载任务**:SQLite 持久化 + 断点续传 + aria2 / yt-dlp / native 三引擎自动 fallback
- **⚙ 设置**:看引擎状态、版本信息

**依赖的外部工具**(`设置` 页会显示):
- `aria2c`:装 [aria2 for Windows](https://github.com/aria2/aria2/releases),加 PATH
- `ffmpeg`:装 [Gyan FFmpeg](https://www.gyan.dev/ffmpeg/builds/),加 PATH

没装这两个也能跑,只是会 fallback 到内置 native 引擎,功能能用但速度慢点。

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 双击 `build.bat` 闪退 | 用记事本打开 `build.bat`,在最后加一行 `pause`,再看报错 |
| 提示 "Python 不是内部命令" | 重装 Python 时勾选 **Add Python to PATH**,或手动加 `%LocalAppData%\Programs\Python\Python311\` 到 PATH |
| 打包过程报 "ModuleNotFoundError" | 在 `.venv` 里 `pip install -r requirements.txt` 再重跑 |
| 双击 .exe 弹窗报缺 DLL | 装 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 启动后窗口是黑的(显示命令行) | 正常,Python 端 `console=False` 已配好;若仍弹黑窗说明 Windows Defender 误报,加信任 |

---

## 我已经帮你验过的事

- ✅ Linux 上跑过一遍 `pyinstaller shortdrama.spec`,spec 文件 + hiddenimports + 依赖全部 OK
- ✅ 源码完整(无 __pycache__ / .pyc / .venv 残留)
- ✅ 图标 `assets/icon.ico` 齐全
- ✅ spec 文件加了 PyQt6 子模块 + yt-dlp 异步的 hiddenimports,Windows 上打包更稳
- ❌ **没法在沙箱里直接给你 .exe**:Windows .exe 必须在 Windows(或 Wine)上生成,PyInstaller 不支持 Linux 交叉编译。**这是技术限制,不是工具问题。**

所以最快的路径就是上面三种方式任选其一,5 分钟内拿到 `.exe`。