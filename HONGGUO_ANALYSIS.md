# hongguo-downloader 1.1.0 完整逆向分析报告

> 分析对象:hongguo-downloader-1.1.0-Setup.exe(红果短剧下载器 1.1.0)
> 分析方法:解包 NSIS 安装程序 → 解出 app.asar(Electron) → 通读全部 JavaScript 源码
> 许可证:GPL-3.0(原项目 package.json 声明,移植代码已保留协议声明)
> 配套产物:移植版 `shortdrama-hongguo-port`(红果内核并入 shortdrama,保留其苹果风 UI)

---

## 1. 应用概况

| 项 | 内容 |
|---|---|
| 名称 | 红果短剧下载器(hongguo-downloader) |
| 版本 | 1.1.0 |
| 形态 | Windows x64 桌面应用,NSIS 安装包(**Setup.exe**) |
| 技术栈 | **Electron + Vite + React**(渲染层)+ 原生 Node 主进程 |
| 打包 | 安装包内 `$PLUGINSDIR/app-64.7z` → `resources/app.asar` 即全部源码 |
| 许可证 | GPL-3.0 |
| 附带二进制 | ffmpeg / ffprobe / ffplay(用于合流、转码、探测) |
| 主要功能 | 搜索/浏览红果短剧 → 解析全集与播放直链 → **下载 CENC 加密的 MP4 并解密** → 在线播放 → HEVC 兼容转码 → ffmpeg 合并合集 |

**为什么用 Electron**:视频站解析类工具天然需要"网页嗅探 + 网络请求 + 本地文件读写 + 播放器"四件事,Electron 一套全包(Chromium 网络栈 + Node fs + `<video>` 标签),并且渲染层可以做成 Web 风格,比 Qt 上手快。代价是包体大(约 116MB)。

**为什么用 NSIS**:安装器小巧、支持 7z 压缩插件(`nsis7z.dll` 在 `$PLUGINSDIR` 里),可以把 Electron 的几百 MB 压成 ~116MB 安装包;`app-64.7z` 里再带 ffmpeg 全家桶。

---

## 2. 源码清单与模块职责

解包 `app.asar` 后:

```
app.asar/
├── main.js                    # Electron 主进程(约 2800 行):窗口 / IPC / 下载队列 / 合并 / 在线播放 / 转码 / 持久化
├── src/
│   ├── native/
│   │   └── hongguo.js         # ★ 平台核心:官方 API + 官网数据源 + spade_a 密钥派生 + CENC 解密 + MP4 去保护
│   └── store.js               # JSON 持久化(设置 / 任务 / 剧集档案)
├── dist-react/                # Vite 构建产物(React 渲染层)
│   ├── index.html
│   └── assets/index-DpLStu0H.js   # 全部 UI 逻辑(搜索/浏览/播放/任务/设置页)
├── node_modules/              # 依赖(仅 axios)
└── package.json               # name=hongguo-downloader,version=1.1.0,license=GPL-3.0
```

主进程职责划分(`main.js` 内的函数按功能分组):

### 2.1 窗口与应用生命周期
- `createWindow` / `app.whenReady` / `launchApp`:创建 1000×700 窗口,带原生标题栏,`contextIsolation:false`(直接把 IPC bridge 挂 window 上,省 preload 序列化)。
- `isDev` / `launchApp`:开发态连 `http://localhost:5173`,生产态加载 `dist-react/index.html`。

### 2.2 下载流水线(核心)
- `enqueueEpisodes`(IPC `download-single-episode` / `download-series`):**从 UI 收"剧集 + 目标目录 + 并发数"**,写入 series registry,然后:
- `pumpQueue`:立即返回的调度器,维护最大并发(默认 3)。
  - 代码里注释了原因:**早期版本用 `await executeDownload(...)` 串行等待,并发永远等于 1**;改成"不等结果直接 return、任务完成回调再调 pump"后并发才真正生效。
- `executeDownload`(IPC `execute-download`):单集下载,流程:
  1. `fetchPlayUrl` 拿播放直链(API 优先,官网兜底)
  2. 有 `spade_a` → `deriveKey` 派生 16 字节 AES Key
  3. 流式下载到 `<目标>.enc.tmp`(先写临时文件,不暴露半成品)
  4. 403 时带 `Referer: https://novelquickapp.com/` 重试一次
  5. 解密成明文 MP4 → 改名成正式文件
  6. 已存在且 >100KB 则跳过(断点续传/去重)
- `downloadEpisode` / `downloadImage` / `saveCover` / `generateCoverArt`:下载封面图,存到系列缓存目录。

### 2.3 合并与转码(依赖 ffmpeg)
- `mergeEpisodes` / `executeMerge`:把已下载的各集用 **ffmpeg concat demuxer** 合并成一部完整剧(`-f concat -safe 0 -i list.txt -c copy`);合并前抽样探测编码是否一致,并检查磁盘空间。
- `transcodeEpisodes` / `executeTranscode` / `buildTranscodeArgs` / `probeCodec` / `isCompatibleCodec`:
  - 目的:HEVC(H.265)在浏览器 `<video>` 里兼容性差,**转成 H.264**。
  - 编码器探测顺序:nvenc → qsv → amd(amf)→ mf(Media Foundation)→ libx264(软编兜底)。
  - `isCompatibleCodec` 用 ffprobe 判断当前文件是不是已经兼容,是则跳过,省一次转码。

### 2.4 在线播放(Electron 特性)
- `setupStreamProtocol`:**注册自定义协议 `video://`**。
  - CENC 密文没法直接喂 `<video>`,所以解密后在内存缓存里存明文,通过 `video://` scheme 自定义流提供,支持 Range 断点(播放器拖动)。
  - 本地文件也走 `video://`,是为了避开 dev 模式下 `file://` 的访问限制。
- `playSeries` / `playRemoteEpsiode` / `playLocalEpisode`:根据集号在任务/缓存里找文件,没有就触发在线下载并播放。

### 2.5 持久化(`src/store.js` + main 里对应函数)
- 三份 JSON 文件:
  - `settings.json`:下载目录、并发数、合并设置、代理、兼容转码开关等;
  - `tasks.json`:任务列表(剧集 → 状态/进度/目标路径);
  - `series.json`:剧集档案(元数据 + 分集清单),用于重启后恢复、防重复解析。
- `saveSettings` 每次都 `JSON.stringify(..., null, 2)` 整体覆盖(小数据量,简单可靠)。

### 2.6 其它
- `probeProxy` / `changeProxy`:代理设置(axios 读环境变量)。
- `extractArchive` / `isArchiveFile` / `_supportsZip/_supports7z/_supportsRar`:支持把"红果 App 缓存导出的压缩包"解包成可下载的剧集(社区用户常用玩法)。
- `fetchTasks` / `deleteTask` / `clearDoneTasks` / `reportTask`:任务查询与清理。

---

## 3. 渲染层 UI(React)

`dist-react/assets/index-DpLStu0H.js`(压缩后 ~218KB),页面:

| 页面 | 功能 |
|---|---|
| 搜索(Search) | 关键词 → `resolveSeriesId` + 列表,含官网嗅探结果 |
| 浏览(Browse) | 官网分类/标签页翻页浏览 |
| 播放(Player) | `<video>` + `video://` 流,拖动/倍速/进度条 |
| 任务(Tasks) | 表格:剧集、进度、状态、操作(下载/播放/合并/转码/删除) |
| 设置(Settings) | 下载目录、并发、代理、HEVC 兼容开关、缓存清理 |

UI 与主进程通过挂在 `window` 上的 IPC bridge 通信(`contextIsolation:false` 所以无需 preload)。

---

## 4. 红果平台协议(核心逆向成果)

### 4.1 双数据源设计(为什么这么写)

```
用户输入(剧 ID / 分享链接 / 关键词)
        │
        ├─① 官方 App 接口(api5-normal-sinfonlineb.fqnovel.com)
        │     POST /novel/player/multi_video_detail/preload/v1   → 全集分集
        │     POST /novel/player/multi_video_model/preload/v1    → 单集播放直链 + spade_a
        │     特征:固定设备指纹参数即可访问,**无需 X-Bogus 签名**(该版本直连可用)
        │
        └─② 官网网页版(hongguoduanju.com,服务端渲染,无需签名)
              /player/{series_id}        → 分集(vid_list 内嵌在 HTML)
              /player/{sid}/{vid}        → 单集 MP4 直链(main_url 内嵌)
              /search/{keyword}          → 搜索结果
```

**为什么双数据源**:官方 API 返回的是 **CENC 加密直链 + spade_a(密钥载体)**,走官方接口 = 拿最高画质 + 必须解密;官网内嵌的是 **明文 MP4 直链**,无需解密,画质固定(常见 360p)。两条腿走路,官方接口抽风(空响应/限流)时自动降级官网,保证"永远能下"。

### 4.2 官方 API 的固定设备指纹

`COMMON_QUERY` 里一组写死的参数(device_id / iid / aid=8662 / app_name=novelread / version_name=7.1.5.32 / cdid / klink_egdi 等),伪装成番茄小说/红果阅读 Android 客户端。**为什么这么写**:这类字节系内容接口按"设备指纹 + App 版本"做风控,固定一组真实存在的指纹参数,后端就按正常客户端对待;再带 `_rticket`(当前毫秒时间戳)满足"实时性"校验。没有走 X-Bogus 是因为该版本接口恰好不校验请求签名(只校验参数合规),这是原项目实测出来的结论。

### 4.3 选流策略(parseVideoModel)

对返回的 `video_list`(同一集有多种清晰度/编码):

```
评分 = (definition 数值(1080p>720p>480p...), 像素 w*h, -codecRank, bitrate)
取评分最高的一条
```

codecRank:h265/h264/avc1/hvc1 = 0(最优先,本身就是兼容编码),`bytevc1`(字节自研编码)= 1,其它 = 2。
**为什么这么写**:definition 标签优先(用户心智是"1080p 就是最好的"),像素兜底(同是 1080p 但分辨率更高者胜),编码排第三(bytevc1 播不了,所以靠后),最后码率破平。

### 4.4 官网数据源的提取规则(SNIFFER_JS)

原 Electron 版在隐藏 BrowserView 里 `executeJavaScript` 嗅探 DOM:

```js
const SNIFFER_JS = `... [...document.querySelectorAll('a')].map(a => {
  const href = a.getAttribute('href') || '';
  const m = href.match(/series_id=(\\d{6,})/);
  if (!m) return null;
  const title = a.querySelector('img[alt]')?.alt
            || a.querySelector('[class*="title"]')?.textContent
            || a.textContent.trim();
  const cover = a.querySelector('picture source[srcset]')?.srcset.split(' ')[0]
            || a.querySelector('img')?.src || a.querySelector('img')?.dataset.src;
  const episodeCount = parseInt((a.querySelector('[class*="episode"]')?.textContent || '').match(/(\\d+)\\s*集/)?.[1] || '0');
  const tags = [...a.querySelectorAll('[class*="tag-text"]')].map(e => e.textContent.trim()).slice(0, 4);
  ...
})`
```

移植版等价改为 **HTTP 拉 HTML + 正则提取**(`platforms/hongguo.py::_extract_cards`),规则一一对应:剧名取 `img[alt]` → `[class*=title]` → 块文本;封面取 `picture>source[srcset]` → `img[src]` → `img[data-src]`;集数取 `[class*=episode]` 里的"N 集";标签取 `[class*=tag-text]` 前 4 个。

---

## 5. 加解密详解(AES-128 这一层)

红果的剧集视频是 **CENC(Common Encryption,ISO/IEC 23001-7)加密的 MP4**,方案 `cenc`/`cec1`,算法 **AES-128-CTR**。播放密钥不直接给,而是由播放接口返回的 **`spade_a` 字段**(一段混淆过的 Base64)派生。整个解密分三步:

### 5.1 第 1 步:avBase64 解码(FFmpeg 兼容 Base64)

`spade_a` 用的不是标准 Base64 语义,而是 **FFmpeg `av_base64_decode` 的容错变体**:

- 遇到非 base64 字符(如 `=`、换行)不报错,把当前 4 字符组里已收集的字符"部分解码"(3 字符→2 字节、2 字符→1 字节)后**立即停止**;
- 不要求长度是 4 的倍数。

**为什么这么写**:服务端故意用这种"非标准"编码,增加直接用标准 Base64 解码的难度;同时容忍 `=` 结尾(标准编码器产物)也能解。

### 5.2 第 2 步:spade_a → 16 字节 AES Key(deriveKey)

对解码后的 `buf`,算法:

```
L = len(buf)
key0 = buf[0] ^ buf[1] ^ buf[2]          # 第 1 字节 = 前 3 字节异或,自校验
x27  = key0 - 0x30
w22  = L - key0 + 0x2f                   # key blob 的长度
校验:x27 >= 2 且 2 <= w22 <= L-1,否则失败
x21  = buf[1 : 1+w22]                    # 取出 key blob

# —— 滚动去混淆循环 ——
w11 = 0x55; w12 = 0xFA; w10 = 0xEB
for i in 0..len(x21)-1:
    pc  = popcount(i)                    # i 的二进制里 1 的个数
    w14 = (i 为偶数) ? w12 : w11         # 当前寄存器
    更新:w11(奇数位)/ w12(偶数位)= 当前原始字节
    x21[i] = (w10 - pc + (w14 ^ x21[i])) & 0xFF

# —— 从解混淆后的 blob 里抠 key ——
c0 = x21[0]                              # 必须是十六进制字符
hval = c0 - '0' 或 c0 - 'a' + 10
w9  = w22 - hval                         # key 十六进制串长度(含 1 字节偏移)
strA = x21[1 : 1+w9-1]                   # 恰好 32 个字符
AES Key = bytes.fromhex(strA)            # 16 字节
```

**为什么这么写**:
1. **key0 用异或自校验**:服务端能验证"你解出来的长度字段对得上",结构不对直接返回失败,挡掉瞎试的;
2. **w11/w12 双寄存器交替**:去混淆不是简单逐字节 XOR,而是"上一字节明文/密文决定下一字节的解码状态"(滚动依赖),手工静态分析很难一眼看穿;`popcount(i)` 又把下标信息混进异或值,进一步增加非线性;
3. **x21[0] 是十六进制标记字符**:第一位明文实际编码了"key 串长度偏移",密钥本体不固定长度存放,防搜索"32 位 hex 字符串"直接定位。

一句话:**它不是强加密,是"防随手提取"的混淆**——真正的安全边界是 CENC 那层,spade_a 这层只是为了不让 key 以明文形式躺在包里。

### 5.3 第 3 步:CENC-AES-CTR 解密(decryptSample)

CENC 的 AES-CTR 密钥流生成规则:

```
对第 k 个 16 字节块:
    counter_block = nonce[0:8] || big-endian-64(k)     # 8 字节 nonce + 8 字节计数器
    keystream_block = AES-128-ECB(key, counter_block)
    plain_block     = cipher_block XOR keystream_block
nonce 来自 MP4 的 senc box:每个 sample 一个 8 字节 IV
```

实现要点:
- 用 AES-128-**ECB** 对 `nonce||BE64(k)` 逐块加密 = CTR 密钥流(等价于 AES-CTR 只加密计数器部分);
- 每集/每 sample 独立 nonce,避免相同明文+相同密钥产生相同密钥流(CTR 复用 nonce 的经典坑);
- 长度不是 16 倍数的尾部,截断密钥流再异或。

### 5.4 MP4 去保护(rebuildMoov / decryptMp4Buffer)

解密密文后文件还不能直接放,因为 moov 里全是保护信息,必须重建:

```
1. 解析 box 树(递归,支持 64 位大 size / size=0 到文件尾)
2. 对每个 track(stbl):
   - stsz  → 每个 sample 的大小
   - stco  → chunk 的文件偏移
   - stsc  → 每个 chunk 装几个 sample(分段表)
   - senc  → 每个 sample 的 8 字节 nonce
   由 chunk 偏移 + 逐 sample 大小,推出每个 sample 的绝对偏移,逐个解密
3. 重建 moov:
   - 删掉保护元数据:senc / saio / saiz / sgpd / sbgp
   - stsd 里 sample entry 从 encv → hvc1、enca → mp4a(78/28 字节头部),
     并删除 sinf(保护信息)子 box
   - moov 变小了,mdat 里的 chunk 偏移(stco)整体减去 delta
4. 按顶层 box 重新拼装(ftyp + 新 moov + mdat)
```

**为什么这么写**:CENC 加密的文件在普通播放器里会"找不到可解码的轨道",因为 stsd 声明的是 `encv`(加密视频)且带 `sinf`;去掉保护箱、把类型改回标准 `hvc1`/`mp4a`、修正偏移后,就是一个普通可播 MP4。stco 的 delta 调整是**最关键也最容易漏的一步**——moov 短了,所有 chunk 偏移都要整体前移,否则音画全乱。

---

## 6. 为什么这么写(设计意图总结)

| 设计 | 意图 |
|---|---|
| 双数据源(API + 官网) | 官方接口挂掉也能下;官网直链还免去解密 |
| 固定设备指纹 + `_rticket` | 让后端把请求当真实客户端,绕过风控 |
| spade_a 混淆(异或自校验 + 滚动寄存器 + popcount + 长度标记) | 防止 key 被静态提取,挡"拿来即用" |
| CENC-AES-CTR + moov 重建 | 官方 DRM 的最小正确实现(不是破解,是拿服务端下发的 key 解密自己下的文件) |
| 下载先写 `.enc.tmp` 再改名 | 崩溃/中断不留下损坏的"成品",重启可续 |
| 队列 pumpQueue 不等 await | 让并发真正生效(早期 await 版本并发恒为 1) |
| 403 补 Referer 重试 | CDN 对无 Referer 请求直接拒绝,带上官方 App 的 Referer 才放行 |
| 选流按"清晰度标签>像素>编码>码率" | 兼顾"用户要的高画质"与"播放器能播"(bytevc1 靠后) |
| ffmpeg 合并用 concat + `-safe 0` + UTF-8 列表 | 中文路径/文件名安全;先探测编码一致避免合出花屏 |
| 转码编码器按 nvenc→qsv→amf→mf→libx264 探测 | GPU 加速优先,软编兜底,兼容任何机器 |
| 在线播放自定义 `video://` 协议 + Range | 解密结果不落盘直接流给 `<video>`,拖动靠 Range;同时绕开 dev 模式 file:// 限制 |
| contextIsolation:false | 省 preload 桥,IPC 直接挂 window(个人工具,风险可接受) |

---

## 7. 移植到 shortdrama 的映射(v0.6-hongguo)

### 7.1 移植原则
- **UI 保留 shortdrama 的苹果风**:`apple_style.py` 一字未动;页面布局(搜索/链接/任务/设置)与全部样式不变。
- **下载器内核原样移植**:加密/协议代码与 JS 逐行对应(命名保留原意),GPL-3.0 声明保留。

### 7.2 文件映射

| hongguo-downloader 源码 | 移植到 shortdrama | 说明 |
|---|---|---|
| `src/native/hongguo.js`(API + 官网 + 直链) | `core/hongguo_client.py` | apiCall / resolveSeriesId / fetchEpisodeList(含官网兜底) / fetchPlayUrlSingle(含官网兜底) / normalizeVideoUrl / pickJsonString / parseVideoModel(选流) / streamScore |
| `src/native/hongguo.js`(deriveKey / decryptSample / rebuildMoov / decryptMp4Buffer) | `core/hongguo_crypto.py` | avBase64 解码、密钥派生、CENC-AES-CTR 解密、MP4 去保护,全部逐行移植 |
| main.js 的 SNIFFER_JS(官网嗅探) | `platforms/hongguo.py::_extract_cards` | executeJavaScript → HTTP+正则,提取规则一一对应 |
| main.js `enqueueEpisodes` / `pumpQueue` / `executeDownload` | `core/downloader.py` 新增 `EngineKind.HONGGUO` + `_via_hongguo` | 流式下载 → `.enc.tmp` → 403 带 Referer 重试 → deriveKey → 解密 → 改名 |
| main.js `saveSeriesData/saveTasks` 等 | 复用 shortdrama 的 `core/task_store.py`(SQLite) | 任务/进度入库,任务页展示 |
| 渲染层(React UI) | **不移植** | 用户要求保留 shortdrama 的 PyQt6 苹果风 UI |
| 在线播放 `video://` 协议 / HEVC 兼容转码 / ffmpeg 合并 | **未移植(Electron 特性)** | 见 §7.4 |

### 7.3 UI 侧接线(样式不变,只补逻辑)
- `ui.py` 的 `LinkPage` 原本"下载"按钮是个弹窗占位;已接通真实流程:
  解析/搜索 → `platform.get_episodes()` 拉分集 → 勾选/全选 → `DownloadWorker` 线程内 `resolve_url()` 拿直链与 spade_a → `DownloadEngine` 按需走 hongguo 解密引擎 → 进度写入 SQLite 并刷新任务页 → 完成/失败汇总弹窗。
- 搜索页点选某部剧 → 直接跳链接页并自动加载分集(原行为只是预填关键词)。

### 7.4 未移植部分与补法(如需)
| 原功能 | 未移植原因 | 在本项目补法 |
|---|---|---|
| 在线播放(自定义 `video://`) | Electron 专属,Qt 无法注册浏览器协议 | PyQt6 的 QMediaPlayer 播放已解密到本地缓存的文件即可 |
| HEVC → H.264 兼容转码 | 依赖 ffmpeg 探测 + Electron 播放器兼容性 | 本项目自带 ffmpeg,可在下载完成后加一个"转码"选项(参考 buildTranscodeArgs 的 nvenc→qsv→amf→mf→libx264 顺序) |
| ffmpeg 合并全集 | 依赖 ffmpeg | 本项目自带 ffmpeg,可加"合并为合集"按钮(concat demuxer + `-safe 0`) |
| 代理设置 | Electron 会话代理 | 本项目是 aiohttp,可在设置页加 proxy 参数传给 ClientSession |

---

## 8. 移植版验证结果(实测)

| 验证项 | 结果 |
|---|---|
| 单元测试 `test_hongguo_port.py`(avBase64 / deriveKey 往返 / CTR 密钥流 / 合成 CENC MP4 全流程解密 + moov 重建 / HTML 卡片提取 / 纯函数) | **32 项全部通过** |
| 在线:官网搜索"逆袭" | ✅ 返回 10 部真实剧(剧 ID/标题/封面) |
| 在线:分集解析(官方 API 空响应 → 自动降级官网) | ✅ 《逆袭人生》142 集,每集真实 vid;降级逻辑与原 JS 完全一致 |
| 在线:单集直链解析 | ✅ `https://hongguoduanju.com/video/public/{vid}/360p.mp4` |
| 在线:端到端下载 | ✅ 第 1 集 6.6MB,输出 `ftyp` 开头有效 MP4,目录 `save_dir/剧名/001_第1集.mp4` |
| GUI 冒烟(offscreen 启动 MainWindow) | ✅ 平台列表含"红果短剧",链接页正常 |

> 说明:本沙箱网络下官方 API 返回"HTTP 200 但 0 字节"(网关丢弃),因此 **spade_a/CENC 解密路径由合成 CENC MP4 测试覆盖**;官网明文直链路径已全链路实测。在用户网络环境(国内直连)下官方 API 可用时,解密路径会自动走 API 数据源。API 若持续不可用,官网兜底保证功能不挂。

---

## 9. 合规与授权提醒

- hongguo-downloader 为 **GPL-3.0** 开源项目,移植/分发需保留 GPL-3.0 声明(已做)。
- 本工具仅供技术研究与个人学习;各平台视频版权归平台与版权方所有,请勿用于商业传播或侵权用途。
- CENC 解密使用的是**平台播放接口随响应下发的密钥材料(spade_a)**,相当于官方客户端自己解密自己下发的文件;请仅在个人学习范围内使用。
