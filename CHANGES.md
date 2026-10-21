# v0.6 - 把「cp1252 打印中文崩溃」这一类问题整个封死

> 上一版 v0.5 只修了 `tools/setup_binaries.py` 一个入口。
> v0.6 复盘了 build 日志,发现**同一个坑还有第二个入口(shortdrama.spec)**,
> 而且 v0.5 的部署命令有一个静默失效的写法,可能导致修复根本没进仓库。

---

## 一、日志报错原因(逐行对证)

你给的 `logs_101435673379.zip` 里,失败发生在 `build/6_*.txt` 那一步,
报错原文:

```
2026-10-06T10:18:06Z ##[group]Run python tools/setup_binaries.py
2026-10-06T10:18:06Z Traceback (most recent call last):
2026-10-06T10:18:06Z   File "D:\a\DJUTool\DJUTool\tools\setup_binaries.py", line 197, in <module>
2026-10-06T10:18:06Z     sys.exit(main())
2026-10-06T10:18:06Z   File "D:\a\DJUTool\DJUTool\tools\setup_binaries.py", line 168, in main
2026-10-06T10:18:06Z     print(" 下载 aria2c + ffmpeg 到 assets/bin/")
2026-10-06T10:18:06Z   File "...\Lib\encodings\cp1252.py", line 19, in encode
2026-10-06T10:18:06Z UnicodeEncodeError: 'charmap' codec can't encode characters in position 1-2
2026-10-06T10:18:06Z ##[error]Process completed with exit code 1.
```

**直接原因**:runner 是 `windows-2025-vs2026`(Windows Server 2025),step 默认 shell 是
PowerShell 7,它的 stdout 编码是 **cp1252**。Python 3.11 启动时按环境决定
`sys.stdout.encoding=cp1252`,脚本里第一行 `print(" 下载 aria2c + ffmpeg 到 assets/bin/")`
里的中文没法用 cp1252 表示 → 直接 `UnicodeEncodeError` → 脚本 exit 1 → step 失败 → build 失败。

注意崩溃点在 **`main()` 的第 168 行**,也就是**下载逻辑之前**。所以不是网络、不是
75MB 压缩包、不是权限问题 —— 二进制一个字节都还没动,脚本就死了。

### 关键对证:这份日志跑的是 **v0.5 之前**的代码

| 证据 | 日志里的值 | 你上传的 v0.5 源码 |
|---|---|---|
| `sys.exit(main())` 行号 | 197 | **387** |
| 第 168 行内容 | `print(" 下载 aria2c + ffmpeg ...")` | `_download()` 里的重试日志(纯 ASCII) |
| step 名的中文 | `安装依赖`、`下载 aria2c + ffmpeg` | 已改成 `Install dependencies` 等英文 |
| step env 里有没有 `PYTHONIOENCODING` | **没有**(只有 pythonLocation 等 setup-python 自带的) | workflow job 级有 |

也就是说:仓库 `main` 分支当时跑的还是老版本,v0.5 那三个修复(脚本 reconfigure /
ASCII print / workflow env)一个都没生效。CHANGES.md 里对根因的判断是对的,
但**只覆盖了一个入口**。

---

## 二、v0.5 为什么还有可能再挂一次

### 坑 1:`shortdrama.spec` 里还留着中文 print(构建期同一个坑)

```python
# v0.5 shortdrama.spec:54
print(f"[spec] 将打包以下外部二进制到 bin/: {...}")
```

spec 是 PyInstaller **在构建进程里当 Python 执行的**,它同样是构建期输出。
我实测过(把 stdout 强制成 cp1252、并且模拟 `reconfigure` 不可用):

```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 80-90
```

v0.5 里它只是被 workflow 的 `PYTHONIOENCODING: utf-8` 兜住了 —— 一旦那个 env
丢了(手工改 workflow、换 shell、有人在本地 cmd 里跑 `pyinstaller shortdrama.spec`),
构建就会在**同一个位置、同一个异常**死掉。

### 坑 2:v0.5 的部署命令 `cp -r 短剧下载器-一键打包版/* .` 是无效的

`.github/` 和 `.gitignore` 是**隐藏目录/文件**,bash 的 `*` 不匹配它们。
实测:

```
$ cp -r pkg/* dst/ && ls -a dst
.  ..  main.py            <-- .github 和 .gitignore 根本没进去
$ cp -a pkg/. dst/ && ls -a dst
.  ..  .github  .gitignore  main.py     <-- 这样才对
```

所以:**如果你是照 v0.5 的 `cp -r 短剧下载器-一键打包版/* .` 同步的,
那个带 `PYTHONIOENCODING` 的 workflow 根本没进仓库**,下次 Actions 还是会用老 workflow。
这大概率就是「改了还是同样报错」的原因。

---

## 三、v0.6 做了什么

### 1. `shortdrama.spec` ⭐ 同类崩溃点补掉
- 顶部加 `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`(spec 自包含,不 import 项目模块)
- 第 54 行 print 改成纯 ASCII:`[spec] packing external binaries into bin/: [...]`

### 2. 新增 `tools/check_ascii_prints.py` + workflow 第一步(护栏)
AST 扫描构建路径上的脚本(`setup_binaries.py` / `build_icon.py` / `analyze_mitm.py` /
`shortdrama.spec`),只要出现 **非 ASCII 的 print 字面量或 argparse help/description 就直接 fail**。
放在 workflow 的 checkout 之后第一步:早失败、报错清楚,而不是等 PyInstaller 跑一半炸。

> 注释和 docstring 里写中文**不受影响**,只有真正被 print 出来的字面量会被拦。

### 3. workflow 三层保险(`-X utf8` 比 env 更硬)
```yaml
env:                                   # 第 1 层:job 级
  PYTHONIOENCODING: utf-8
  PYTHONUTF8: "1"
...
run: |                                 # 第 2 层:每个 step 开头再设一次
  $env:PYTHONIOENCODING = 'utf-8'
  $env:PYTHONUTF8 = '1'
  python -X utf8 tools/setup_binaries.py   # 第 3 层:命令行参数,env 丢了也有效
```
`Build .exe (PyInstaller)` 那步同样换成 `python -X utf8 -m PyInstaller shortdrama.spec ...`
(spec 里有 print,必须有这个开关)。脚本内部自己也 reconfigure(第四层)。

### 4. `tools/setup_binaries.py`
- 头部加了一行**编码诊断输出**,以后再挂,看日志就知道是不是编码问题:
  ```
  io encoding: stdout=utf-8 stderr=utf-8
  ```
- docstring 里的用法改成 `python -X utf8 tools/setup_binaries.py`

### 5. `tools/build_icon.py` / `tools/analyze_mitm.py`
- 同样的 reconfigure + 全部 print 改 ASCII(`✓` U+2713 在 **cp936 里根本没有码位**,
  中文 Windows 的 cmd 跑 `build_icon.py` 会直接崩)
- `analyze_mitm.py` 打到 stdout 的 JSON 报告改用 `ensure_ascii=True`
  (中文变 `\uXXXX`,内容仍是合法 JSON;Windows 上 `> report.json` 重定向到文件时同样安全)

### 6. `shortdrama/core/link_parser.py`
自测块(`python -m shortdrama.core.link_parser`)会 print 中文测试数据,加 reconfigure + `→` 改 `->`。

### 7. `build.bat` / `build.sh`
所有 python 调用加 `-X utf8`;`pyinstaller xxx.spec` 换成 `python -X utf8 -m PyInstaller xxx.spec`
(控制台脚本没法直接传 `-X`)。

---

## 四、验证(我这边实测过的)

用 `os.name='nt'` + stdout/stderr 强制 cp1252 模拟 runner,两种模式各跑一遍:

| 测试 | v0.5 | v0.6 |
|---|---|---|
| `setup_binaries.py` 常规模式 | exit 0 | exit 0(日志出现 `io encoding: stdout=utf-8`) |
| `setup_binaries.py` 最坏模式(stdout **无法** reconfigure) | exit 0 | **exit 0** |
| `shortdrama.spec` 常规模式 | ✅ | exit 0,10 个二进制全收集到 |
| `shortdrama.spec` 最坏模式 | ❌ **UnicodeEncodeError** | **exit 0** |
| `analyze_mitm.py --help` | ❌ cp1252 下 help 是中文 | exit 0 |
| `build_icon.py` 错误分支 | ❌ `✓` 在 cp936 无码位 | 无编码崩溃 |
| `check_ascii_prints.py` | (不存在)12 处命中 | **0 处,exit 0** |

另外:所有 `.py` + spec 的 `ast.parse` 全通过,workflow YAML 用 js-yaml 解析通过,
`binaries.tar.gz` 内 10 个文件齐全,`.gitignore` 没有误伤 `assets/bin/binaries.tar.gz`。

---

## 五、你该怎么做(注意这一步以前写错过)

```bash
cd path/to/pian123465-DJUTool

# 1) 覆盖 —— 一定要用 pkg/. ,不能用 pkg/*
#    (pkg/* 不含 .github/ 和 .gitignore,workflow 修不到 = 白改)
cp -a 短剧下载器-一键打包版/. .

# 2) 确认 75MB 压缩包没被 .gitignore 挡掉(应该什么都不输出)
git check-ignore -v assets/bin/binaries.tar.gz

# 3) 确认 workflow 真的换成了新的
grep -n "PYTHONIOENCODING" .github/workflows/build-windows.yml

# 4) 提交推送(网页 Upload files 挡 75MB,必须走 git 命令行)
git add -A
git commit -m "v0.6: kill cp1252 UnicodeEncodeError for the whole build path"
git push
```

已经推过 75MB `binaries.tar.gz` 的话,这次**只需要推文本文件**
(用附带的 `shortdrama-v0.6-hotfix-files.zip`,解压到仓库根目录覆盖即可,不用再推 75MB)。

推完去 Actions 手动触发,正常应该是:

| step | 预期 |
|---|---|
| Guard - no non-ASCII print in build scripts | ✅ 一秒过 |
| Extract and check binaries | ✅ `[OK] all binaries ready` |
| Build .exe (PyInstaller) | ✅ 3-8 分钟 |
| Upload artifact | ✅ 拿到 `shortdrama-dl-windows` |

**万一 `Extract and check binaries` 还是挂**:先看那一步日志里的
`io encoding: stdout=xxx` 这一行。`utf-8` 却还报 UnicodeEncodeError,
说明有别的东西在改编码,把那行日志发我;不是 `utf-8` 就是环境被改了,
`python -X utf8` 会直接无视它。

---

## 六、v0.6 改动文件清单

| 文件 | 改动 |
|---|---|
| `shortdrama.spec` ⭐ | 中文 print → ASCII + 顶部 reconfigure |
| `tools/check_ascii_prints.py` ⭐ 新增 | AST 护栏,workflow 第一步执行 |
| `.github/workflows/build-windows.yml` ⭐ | 加护栏 step;所有 python 调用 `-X utf8`;step 级 env;显式 `shell: pwsh` |
| `tools/setup_binaries.py` | 加编码诊断输出;用法注释改 `-X utf8` |
| `tools/build_icon.py` | reconfigure + 4 处 print ASCII 化 |
| `tools/analyze_mitm.py` | reconfigure + print/help ASCII 化 + stdout 报告 `ensure_ascii=True` |
| `shortdrama/core/link_parser.py` | 自测块 reconfigure + `→` → `->` |
| `build.bat` / `build.sh` | python 调用加 `-X utf8`,echo/注释 ASCII 化 |

体积/时间:仓库 75 MB(不变,`binaries.tar.gz` 本次没动),workflow 3-8 分钟,
最终 exe ~200 MB(不变)。
