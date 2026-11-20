# 分享助手 Pro · Share Assistant Pro

> 把本机文件夹变成一条临时链接：别人能下载，也能把文件传回来。
> Turn any folder on your PC into a temporary link — download and upload back.

[中文](#中文) · [English](#english)

![version](https://img.shields.io/badge/version-3.0.0-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![license](https://img.shields.io/badge/license-MIT-green)

---

## 中文

### 这是什么

一个 Windows 桌面小工具：把本机的文件分组拖进去，点「分享」就得到一条网址；
对方用浏览器打开就能看文件、下载，还能通过「接收区」把文件反向传回你的电脑。

不需要注册账号，不需要公网 IP，不需要路由器端口映射。

### 功能

| 功能 | 说明 |
|---|---|
| 文件库分组 | 想分几类分几类，文件/文件夹直接拖进窗口 |
| 分享链接 | 点分享时勾选「这次要发哪些分组」，每次都是新链接 |
| 接收区 | 同一个网址的 `/receive`，对方打开就能把文件传回来 |
| 访问密码 | 一条链接两个入口共用一个密码，网页端验证 |
| 有效期 | 30 分钟～7 天，到期自动停止 |
| 接收上限 | 本次最多收多少，自由填写（不限 / 500MB / 2TB 都行） |
| 分片上传 | 单文件超过 Cloudflare 100MB 上限会自动切片、续传、拼回 |
| 二维码 | 链接一键出二维码，可复制图片或保存 PNG |
| 换链接 | 手动换一条；每次启动也会自动换新 |
| 局域网直传 | 自己手机 ↔ 电脑互传，不经过任何服务器 |
| 换皮肤 / 换 UI | 一套 `theme.json` 同时驱动桌面和网页；UI 实现可整个替换 |

### 安装

1. 到 [Releases](https://github.com/lefango/share-assistant-pro/releases) 下载 `ShareAssistantPro_Setup_3.0.0.zip`
2. 解压，双击里面的 `分享助手Pro_安装程序.exe`
3. 选安装目录（默认 `C:\Program Files\分享助手Pro`），点「开始安装」
4. 装完自动启动；桌面/开始菜单有快捷方式，控制面板可卸载

> 安装程序是目录版（本机 PyInstaller 单文件在含中文的路径下会报
> `Could not create temporary directory`），所以发的是 zip，解压后再运行。
> 想直接免安装用：把 zip 里的 `_internal` 和 `分享助手Pro.exe` 放一起，双击 exe 即可。

### 用法（三步）

1. **建分组** → 左上「＋新建」，把文件拖进窗口
2. **点分享** → 勾选这次要发的分组 → 等链接出来
3. **发链接** → 复制链接或二维码给对方；要收文件就发「接收链接」

### 自己编译

```bat
pip install customtkinter tkinterdnd2 pillow qrcode pyinstaller
python build.py                     :: 生成 dist\分享助手Pro\
cd installer
python build_installer.py           :: 生成安装包
```

### 目录结构

```
app/            程序主体（config / service / library / share / ui）
app/share/      本地 HTTP 服务、cloudflared 隧道、分片上传、统计
app/ui/         界面实现，app/ui/<名字>/ 里写 run(ctx) 即可替换整套 UI
web/            对方打开的网页：分享页 + 接收页
skin/           皮肤：theme.json 同时作用于桌面与网页
installer/      安装程序
tests/          可重复跑的验收脚本
```

### 已知限制

- 只支持 Windows 10/11
- 隧道用 Cloudflare 免费 quick tunnel，域名每次启动都变，偶尔国内连不上
- 单次请求超过 100MB 会被 Cloudflare 拒绝，程序已自动分片（64MB 一片）

### 许可证

MIT，见 [LICENSE](LICENSE)。

---

## English

### What it is

A small Windows desktop app that turns a local folder into a temporary link.
Open the link in any browser to browse and download files — and use the
**receive page** to push files back to the host.

No account, no public IP, no router port forwarding.

### Features

| Feature | Detail |
|---|---|
| Library groups | Any number of categories; drag files or folders in |
| Share link | Pick which groups to expose; a fresh link every session |
| Receive area | `/receive` on the same link lets the guest upload back |
| Password | One password guards both the share and the receive page |
| Expiry | 30 minutes to 7 days, auto-stops when it expires |
| Receive quota | Free-form byte limit for a session (`unlimited` / `500MB` / `2TB`) |
| Chunked upload | Files above Cloudflare's 100MB request cap are split and reassembled |
| QR code | Render the link as a QR image; copy it or save as PNG |
| Link refresh | Rotate the link manually, and on every app start |
| LAN transfer | Phone ↔ PC on the same Wi-Fi, no server involved |
| Skins / UI | One `theme.json` styles both the app and the web pages; UI is swappable |

### Install

1. Grab `ShareAssistantPro_Setup_3.0.0.zip` from
   [Releases](https://github.com/lefango/share-assistant-pro/releases)
2. Unzip it and run `分享助手Pro_安装程序.exe`
3. Pick a folder (default `C:\Program Files\分享助手Pro`) and click install
4. The app launches automatically; shortcuts and an uninstall entry are created

> The installer is a directory build (single-file PyInstaller fails on this
> machine when the path contains Chinese characters), hence the zip. To skip
> installing, keep `_internal` next to `分享助手Pro.exe` and run the exe.

### Usage

1. **Create a group** — click `＋ New` and drag files in
2. **Share** — pick the groups for this session, wait for the link
3. **Send it** — share the link or QR; send the receive link to collect files

### Build from source

```bat
pip install customtkinter tkinterdnd2 pillow qrcode pyinstaller
python build.py                     :: produces dist\分享助手Pro\
cd installer
python build_installer.py           :: produces the installer
```

### Layout

```
app/            core app (config / service / library / share / ui)
app/share/      local HTTP server, cloudflared tunnel, chunked upload, stats
app/ui/         UI implementations; drop in app/ui/<name>/run(ctx) to replace it
web/            pages the guest sees: share page + receive page
skin/           theme.json drives both the desktop UI and the web pages
installer/      installer
tests/          repeatable acceptance scripts
```

### Limitations

- Windows 10/11 only
- Uses a free Cloudflare quick tunnel: the domain changes on every start and
  may be unreachable in some networks
- Requests over 100MB are rejected by Cloudflare; the app chunks uploads at 64MB

### License

MIT — see [LICENSE](LICENSE).
