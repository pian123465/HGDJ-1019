# 短剧下载器 v2.0(内核版)

Windows 11 桌面程序,支持多平台短剧搜索、参数化下载、批量断点续传。

> ⚠️ **合规声明**:本项目仅用于技术研究与个人学习。请勿用于商业传播或侵权用途。各平台视频版权归平台与版权方所有。
>
> **红果内核移植自 [hongguo-downloader](https://github.com/hongguo-downloader) 1.1.0(GPL-3.0)**,相关文件(`shortdrama/core/hongguo_client.py`、`shortdrama/core/hongguo_crypto.py`、`shortdrama/platforms/hongguo.py`、`shortdrama/core/downloader.py` 的红果引擎部分)保留 GPL-3.0 协议声明。

## 功能

| 模块 | 状态 | 说明 |
|------|------|------|
| GUI(PyQt6) | ✅ | Windows 原生,苹果风标签页:搜索/任务队列/**链接解析** |
| 模糊搜索 | ✅ | 跨平台并发编排 |
| 参数选择 | ✅ | 格式 / 分辨率 / 并发 / 保存路径 |
| 单集 / 批量下载 | ✅ | 多选或一键全集(已接线:解析直链 → 排队 → 进度入库) |
| **分享链接解析** | ✅ | 自动识别平台 + 重定向跟随 + ID 提取 + 一键下载 |
| **红果平台适配器** | ✅ | 官网搜索/分集/直链解析 + 官方 App API(双数据源兜底),移植自 hongguo-downloader |
| **CENC-AES-CTR 解密** | ✅ | spade_a → AES-128 Key 派生 + MP4 去保护(moov 重建),移植自 hongguo-downloader |
| **aria2 引擎** | ✅ | 多线程分片 + 断点续传(自动启动 daemon) |
| **yt-dlp fallback** | ✅ | m3u8 优先走 yt-dlp |
| **native 引擎** | ✅ | aiohttp + ffmpeg HLS 合并(最后 fallback) |
| **hongguo 引擎** | ✅ | 红果加密直链:流式下载 → 解密 → 输出 mp4 |
| **断点续传** | ✅ | SQLite 持久化任务 + 自动 Range 请求 |
| **签名插件** | ✅ | `plugins/signatures.py` 注册自定义签名器 |
| **抓包分析** | ✅ | `tools/analyze_mitm.py` 自动提签名 header |
| 河马等新平台 | 🛠️ | 参考 `platforms/_template.py` 实现 |

## 技术栈

```
PyQt6        - GUI
aiohttp      - 异步爬虫
cryptography - AES-128(CENC 解密)
yt-dlp       - 通用下载引擎 fallback
aria2c       - 分片/断点续传主力
ffmpeg       - HLS 合流
SQLite       - 任务持久化
mitmproxy    - 抓包(分析工具输入)
```

## 项目结构

```
shortdrama-dl/
├── shortdrama/
│   ├── apple_style.py          # 🍎 苹果风 QSS(浅灰背景 + 卡片 + iOS Blue)
│   ├── core/
│   │   ├── base.py             # 平台抽象基类 + 数据类(含红果扩展字段)
│   │   ├── downloader.py       # 四引擎分发(aria2 / yt-dlp / native / hongguo)
│   │   ├── orchestrator.py     # 跨平台搜索编排
│   │   ├── aria2_client.py     # aria2 JSON-RPC 客户端
│   │   ├── task_store.py       # SQLite 任务持久化
│   │   ├── link_parser.py      # 分享链接解析(短链重定向 + ID 提取)
│   │   ├── share_resolver.py   # 分享文本 → Drama 路由
│   │   ├── signature.py        # 签名插件基类 + 内置示例
│   │   ├── hongguo_client.py   # 🆕 红果协议客户端(官方 API + 官网兜底,移植 hongguo-downloader)
│   │   └── hongguo_crypto.py   # 🆕 CENC-AES-CTR 解密 + MP4 moov 重建(移植 hongguo-downloader)
│   ├── platforms/
│   │   ├── hongguo.py          # 🆕 红果平台完整适配(搜索/分集/直链,移植 hongguo-downloader)
│   │   └── _template.py        # 河马等新平台模板
│   ├── plugins/
│   │   └── signatures.py       # 👈 在这里注册你逆向的签名
│   ├── ui.py                   # PyQt6 主窗口(苹果风,已接线真实下载流程)
│   └── __main__.py
├── tools/
│   └── analyze_mitm.py         # mitmproxy 抓包分析工具
├── test_hongguo_port.py        # 🆕 红果内核移植自测(32 项)
├── .github/workflows/
│   └── build-windows.yml       # GitHub Actions 自动打 .exe
├── shortdrama.spec             # PyInstaller 配置(已含新模块 hiddenimports)
├── installer.iss               # Inno Setup 安装包脚本
├── build.bat                   # Windows 一键构建脚本
├── build.sh                    # Linux/macOS 源码打包
├── requirements.txt
└── README.md
```

## 分享链接解析

打开「🔗 链接解析」标签页,把分享文案粘进去:

```
[红果短剧] 龙王驾到 https://v.douyin.com/abc123/
```

点「🔍 解析链接」,自动完成:

1. 正则抓出 URL
2. HEAD 请求跟随短链重定向 → 真实 URL
4. 路由到对应平台
5. 拉剧集列表 → 多选 / 全选
6. 点下载触发三引擎(aria2 / yt-dlp / native)

支持的短链域名:

| 域名 | 说明 |
|------|------|
| `v.douyin.com` | 抖音短链 → 302 到 iesdouyin |
| `www.iesdouyin.com` | 抖音网页版 |
| `www.douyin.com` | 抖音国际版 |
| `*hongguo*` | 红果短剧(字节) |
| `*hema*` | 河马短剧 |

在 `link_parser.DOMAIN_RULES` 扩展新平台。

## 安装运行(给最终用户)

如果对方拿到的是安装包(`Setup-Shortdrama-0.3.exe`):

1. 双击安装包
2. 选择安装路径(默认 `%ProgramData%\Shortdrama-DL`)
3. 勾选「创建桌面快捷方式」
4. 完成安装,启动

依赖检查(运行前):
- **aria2c**:用于分片/断点续传,推荐装 [aria2 for Windows](https://github.com/aria2/aria2/releases),加 PATH
- **ffmpeg**:用于 HLS 合流,装 [Gyan FFmpeg](https://www.gyan.dev/ffmpeg/builds/)

没有这两个也能跑,只是会 fallback 到原生引擎。

## 安装运行

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装外部工具(自动检测,缺失会有提示)
# - aria2c:https://github.com/aria2/aria2/releases(下 Windows 版,加 PATH)
# - ffmpeg:https://www.gyan.dev/ffmpeg/builds/

# 4. 启动
python -m shortdrama
```

## 工作流:逆向一个新平台

第 1 步:**抓包**
```bash
# 模拟器或真机上跑 mitmproxy,把请求写到 dump.flow
mitmdump -w dump.flow

# 用手机的 WiFi 代理指向 mitmproxy,然后操作短剧 App
# 触发:搜索 → 点进剧 → 点一集播放
```

第 2 步:**分析签名**
```bash
python tools/analyze_mitm.py dump.flow --out report.json
```
会自动找出短剧相关请求,提取 `X-Sign` / `X-Bogus` / `X-Livetime` 等签名 header。

第 3 步:**逆向签名算法**
在 `report.json` 里挑一个搜索接口,打开 `response.body_preview`,看返回 JSON 结构;然后用 IDA / jadx / 反编译 JS 找到生成 `X-Bogus` 的算法,用 Python 重写。

第 4 步:**写签名插件**
编辑 `shortdrama/plugins/signatures.py`:
```python
from shortdrama.core.signature import register, BaseSigner
import time

class HongguoSigner(BaseSigner):
    name = 'hongguo'

    def sign(self, method, url, params, headers):
        ts = int(time.time() * 1000)
        bogus = self._bogus(url, params, headers.get('User-Agent', ''), ts)
        return {'X-Bogus': bogus, 'X-Livetime': str(ts)}

    def _bogus(self, url, params, ua, ts):
        # 这里写逆向算法
        return 'computed_bogus_value'

register(HongguoSigner())
```

第 5 步:**写平台适配器**
`shortdrama/platforms/hongguo.py`:
```python
from .core.base import BasePlatform, Drama, Episode, DownloadOptions
from .core.signature import get_signer

class HongguoPlatform(BasePlatform):
    name = '红果短剧'

    async def search(self, keyword, page=1):
        signer = get_signer('hongguo')
        async with aiohttp.ClientSession() as s:
            url = 'https://api.hongguo.com/api/v2/search'
            params = {'kw': keyword, 'page': page}
            headers = {'User-Agent': '...'}
            if signer:
                headers.update(signer.sign('GET', url, params, headers))
            async with s.get(url, params=params, headers=headers) as r:
                data = await r.json()
                for item in data['data']['list']:
                    yield Drama(
                        platform='hongguo',
                        drama_id=item['id'],
                        title=item['title'],
                        episode_count=item['episode_count'],
                        cover=item['cover'],
                    )
    # 继续实现 get_episodes / resolve_url ...
```

第 6 步:**在 ui.py 注册**
```python
from .platforms.hongguo import HongguoPlatform
self.platforms = [HongguoPlatform(), HemaPlatform()]
```

## 下载引擎选择策略

```
url ─┬─ aria2 装了? ─yes──► aria2(最优,断点续传/分片)
     ├─ aria2 没装 ─►
     │     ├─ m3u8? ─► yt-dlp(处理 HLS 最稳)
     │     └─ mp4?  ─► native(aiohttp)
     └─ 失败自动 fallback 到下一个
```

可以在 UI 里手动指定优先引擎。

## 断点续传

- 任务状态存 SQLite,关掉程序不丢
- 重启后 `on_resume_all` 列出未完成任务
- aria2 原生支持 Range
- native 引擎先 `stat()` 文件已写大小,然后用 `Range: bytes=N-` 续传

## 打包成 .exe / 安装包

### 方式 A:Windows 本地一键打包(推荐)

```cmd
git clone <repo> && cd shortdrama-dl
build.bat
```

会自动:
1. 创建 venv
2. 装依赖 + PyInstaller
3. 生成图标(若装了 ImageMagick)
4. PyInstaller 打包 → `dist\shortdrama-dl.exe`
5. 若装了 Inno Setup Compiler,继续生成安装包

产物:
- `dist\shortdrama-dl.exe` — 单文件可执行(自带 Python 运行时,约 30MB)
- `installer_output\Setup-Shortdrama-0.3.exe` — 安装包(约 25MB,中文向导)

### 方式 B:手动 PyInstaller

```cmd
pip install pyinstaller
pyinstaller shortdrama.spec --clean --noconfirm
```

### 方式 C:制作安装包(在已构建 .exe 之后)

1. 装 [Inno Setup Compiler](https://jrsoftware.org/isdl.php)
2. 用 Inno Setup 打开 `installer.iss` → Build
3. 产出 `installer_output\Setup-Shortdrama-0.3.exe`(安装向导)

## 界面预览(文字版)

```
┌─────────────────────────────────────────┐
│ 📺 短剧下载器 │ 🔍 搜索短剧              │
│              │           跨平台并发搜索... │
├──────────────┴───────────────────────────┤
│ [🔍 搜索] [🔗 链接] [⬇ 任务] [⚙ 设置] │
├─────────────────────────────────────────┤
│                                          │
│ ┌─────────────────────────────────────┐ │
│ │ [封面] 龙王驾到               ›    │ │
│ │        红果短剧 · 80 集              │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ [封面] 总裁夫人               ›    │ │
│ │        河马短剧 · 50 集              │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

设计语言:
- 浅灰背景 `#F5F5F7`
- 白色卡片 + 12px 圆角
- iOS Blue `#007AFF` 主色
- 文本层级:`#1D1D1F` / `#6E6E73` / `#AEAEB2`
- Segoe UI Variable 字体

## 已知坑

| 问题 | 解决 |
|------|------|
| aria2 没装,自动走 fallback | `winget install aria2.aria2` |
| ffmpeg 没装,HLS 合并失败 | `winget install Gyan.FFmpeg` |
| 红果 X-Bogus 算法不定期变 | 需要随平台维护签名器,工具链支持热替换 |
| 加密 HLS(AES-128) | `_parse_m3u8` 当前未处理,需要扩展 key 解析 |
| App SSL Pinning | 抓不到包时,需要 Frida hook 或 JustTrustMe |

## 路线

- [ ] 加密 HLS(AES-128 key)支持
- [ ] yt-dlp extractor 联动(让 ydlp 直接调短剧平台)
- [ ] 下载速度限制(避免占满带宽)
- [ ] 系统托盘 + 后台保活
- [ ] 自动签名算法变更检测(心跳探针)
- [x] 🍎 苹果风格 UI
- [x] 📦 PyInstaller + Inno Setup 打包