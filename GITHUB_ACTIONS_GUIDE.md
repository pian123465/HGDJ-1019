# GitHub Actions 云构建 .exe — 零基础 5 步上手

> 这套项目作者已经把 GitHub Actions workflow 写好了,你只需要把代码传上去,5 分钟拿到 .exe。**全程在浏览器操作,不需要命令行,不需要 token。**

---

## 步骤 1:登录 GitHub

打开 https://github.com,登录(没账号就注册一个,免费)。

---

## 步骤 2:建一个新仓库

1. 右上角 `+` → **New repository**
2. 填名字,比如 `shortdrama-dl` 或 `drama-downloader`
3. 选 **Public**(私有也行,但 Actions 免费额度一样)
4. ⚠️ **不要勾选** "Add a README file"、"Add .gitignore"、"Choose a license" —— 这些会冲突
5. 点 **Create repository**

---

## 步骤 3:把代码传上去(三种任挑)

### 方式 3A:网页上传(零基础,推荐)

1. 在新建的仓库页面,点 **uploading an existing file**(或者点 **Add file** → **Upload files**)
2. 把整个 `短剧下载器-一键打包版` 文件夹里的所有文件和文件夹拖进去
   - ⚠️ 注意是文件夹**里面的内容**,不是文件夹本身
   - 文件夹结构应该是这样的根目录:
     ```
     .github/workflows/build-windows.yml
     .gitignore
     BUILD_GUIDE.md
     GITHUB_ACTIONS_GUIDE.md  ← 本文件
     README.md
     assets/...
     build.bat
     build.sh
     installer.iss
     requirements.txt
     shortdrama.spec
     shortdrama/...
     tools/...
     ```
3. 拉到页面底部,**Commit changes** 按钮提交

### 方式 3B:命令行 push(熟悉 git 的)

```bash
# 在解压后的短剧下载器-一键打包版/ 目录下
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

### 方式 3C:用 GitHub Desktop(图形化 Git 工具)

1. 下载安装 [GitHub Desktop](https://desktop.github.com/)
2. File → Add local repository → 选解压后的目录
3. 提交 → Publish repository

---

## 步骤 4:触发构建

1. 刷新仓库网页
2. 顶上点 **Actions** 标签
3. 左侧选 **Build Windows .exe**
5. 点右侧 **Run workflow** → 选 **main** 分支 → 绿色 **Run workflow** 按钮

---

## 步骤 5:下载 .exe

1. 等 2-3 分钟,刷新 Actions 页面
2. 看到刚才那次运行显示 ✅ 绿色对勾
3. 点进去,滚到页面最下方
5. **Artifacts** 区 → 点 **shortdrama-dl-windows** 下载(一个 zip)
6. 解压 → 得到 `shortdrama-dl.exe`(约 30MB)
7. **拷贝到任意 Windows 上双击就能跑**,不需要装 Python

---

## 构建失败了?

点进失败的运行 → 看红色 ❌ 那一步的日志 → 一般是这几个问题:

| 报错 | 解决 |
|------|------|
| `ModuleNotFoundError: PyQt6` | requirements.txt 没装好,重新触发一次 |
| `failed to execute script` | 隐藏导入漏了,加 `hiddenimports` 重新触发 |
| `OSError: [Errno 28] No space left` | runner 磁盘满(几乎不可能,免费 14GB) |
| `icon file not found` | icon.ico 没传上去,检查 .gitignore 是否误删了 |

---

## 常见疑问

**Q: Actions 有额度限制吗?**
A: 公开仓库无限免费;私有仓库每月 2000 分钟,打个 30MB 的 .exe 也就 3 分钟,够用。

**Q: 可以每次改代码都自动构建吗?**
A: 当前 workflow 是 `workflow_dispatch`(手动触发),你想自动的话改 `.github/workflows/build-windows.yml`:
```yaml
on:
  push:
    branches: [main]   # ← 加上这一段
  workflow_dispatch:
```
这样每次 git push 都会自动构建,但会消耗免费分钟数,新手建议手动。

**Q: 不想让别人看到我的代码?**
A: 仓库建私有就好。Actions 构建过程和产物只有你能看。

**Q: 我不会 git,但想以后改代码后自动重打 exe?**
A: 用 GitHub Desktop,点点鼠标就能 push,触发新构建。

---

## 跟方式 A 的对比

| 维度 | 方式 A (build.bat) | 方式 B (GitHub Actions) |
|------|---------------------|-------------------------|
| 需要 Windows | ✅ 是 | ❌ 否,云端 Windows |
| 需要装 Python | ✅ 是 | ❌ 否 |
| 需要装 PyInstaller | ✅ 是 | ❌ 否 |
| 耗时 | 3-5 分钟 | 2-3 分钟(网速) |
| 难度 | 极低(双击) | 低(网页 5 步) |
| 可重复构建 | 手动改源码后 | push 即可重打 |

如果你装了 Windows + Python,直接**方式 A**最简单。没装,**方式 B**更省事。