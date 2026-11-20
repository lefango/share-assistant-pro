# -*- coding: utf-8 -*-
r"""
玄天典籍 · 独立预览脚本
运行：python app\ui\xuantian\preview.py

塞入假数据演示所有三页的真实效果。
无需后端，无需配置文件，直接打开窗口。
"""
import os
import sys
import time

# 把项目根加入路径（方便直接 python app\ui\xuantian\preview.py 运行）
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import customtkinter as ctk
try:
    from tkinterdnd2 import TkinterDnD
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

from app.ui.xuantian.view import ShareView

# ──────────────────────────────────────────────────────────
# 玄天典籍主题（和 skin/default/theme.json 结构相同）
# ──────────────────────────────────────────────────────────
THEME = {
    "name":   "xuantian",
    "label":  "玄天典籍",
    "title":  "分享助手",
    "font":   "Microsoft YaHei UI",
    "radius": 4,
    "colors": {
        "bg":          "#0d1119",
        "panel":       "#111820",
        "card":        "#182230",
        "card_hover":  "#1e2d40",
        "border":      "#2a3d50",
        "border_hi":   "#3d5a72",
        "text":        "#dde6f0",
        "text_dim":    "#7a99b4",
        "accent":      "#c9922a",   # 琥珀金
        "accent_hover":"#e3a83a",
        "accent2":     "#4fc3c8",   # 玉青
        "ok":          "#5ecb8a",
        "warn":        "#e9b233",
        "danger":      "#e05a52",
    },
}

# ──────────────────────────────────────────────────────────
# 假数据
# ──────────────────────────────────────────────────────────
FAKE_GROUPS  = ["秘籍珍藏", "符文图鉴", "地图集录"]
FAKE_CUR_GRP = "秘籍珍藏"

FAKE_FILES = [
    {"name": "太极剑法.pdf",        "size_text": "12.3 MB",  "time_text": "今天 09:14",   "is_dir": False},
    {"name": "八卦阵图册",           "size_text": "文件夹",   "time_text": "昨天 18:30",   "is_dir": True},
    {"name": "青龙偃月刀.blend",     "size_text": "238.7 MB", "time_text": "3 天前",        "is_dir": False},
    {"name": "修仙须知.txt",         "size_text": "4.1 KB",   "time_text": "2026-11-01",   "is_dir": False},
    {"name": "丹药配方大全.xlsx",    "size_text": "2.8 MB",   "time_text": "2026-10-28",   "is_dir": False},
    {"name": "渡劫雷法.mp4",         "size_text": "1.4 GB",   "time_text": "2026-10-15",   "is_dir": False},
    {"name": "灵气探测仪固件.bin",   "size_text": "356 KB",   "time_text": "2026-10-10",   "is_dir": False},
    {"name": "宗门章程（修订版）.docx","size_text": "880 KB",  "time_text": "2026-09-20",   "is_dir": False},
]

FAKE_RECEIVED = [
    {"name": "徒弟作业_第一关.zip",  "size_text": "45.2 MB",  "time_text": "今天 10:03"},
    {"name": "功法体悟.txt",          "size_text": "12 KB",    "time_text": "昨天 22:17"},
    {"name": "宗门活动照片.zip",      "size_text": "312 MB",   "time_text": "3 天前"},
]

FAKE_SHARE_URL   = "https://xn--fiq228c.example.com/share/abc123"
FAKE_RECEIVE_URL = "https://xn--fiq228c.example.com/receive/abc123"


# ──────────────────────────────────────────────────────────
# 回调（预览用假实现，只打印到控制台）
# ──────────────────────────────────────────────────────────
def _make_on(view_ref: list) -> dict:
    """返回 on 字典；view_ref[0] 在 view 创建后填入。"""
    def _log(action, *args):
        print(f"[回调] {action}", args if args else "")

    return {
        "share":        lambda: (_log("开始分享"),
                                 view_ref[0].set_state("running", ""),
                                 view_ref[0].set_links(FAKE_SHARE_URL, FAKE_RECEIVE_URL),
                                 view_ref[0].toast("分享已开启")),
        "stop":         lambda: (_log("停止分享"),
                                 view_ref[0].set_state("stopped", ""),
                                 view_ref[0].toast("分享已停止", False)),
        "refresh":      lambda: (_log("换链接"),
                                 view_ref[0].toast("链接已更新")),
        "pick_sources": lambda: _log("选择分享范围"),
        "open_path":    lambda p: _log("打开路径", p),
        "delete_path":  lambda p: (_log("删除文件", p),
                                   view_ref[0].toast(f"已删除：{p}", False)),
        "new_group":    lambda: _log("新建分组"),
        "switch_group": lambda n: (_log("切换分组", n),
                                   view_ref[0].set_groups(FAKE_GROUPS, n)),
        "set_password": lambda pw: (_log("设置密码", pw),
                                    view_ref[0].toast("密码已应用")),
        "set_ttl":      lambda s: _log("设置有效期", s, "秒"),
        "set_limit":    lambda s: (_log("设置接收上限", s),
                                   view_ref[0].toast("接收上限已保存")),
        "set_receive":  lambda b: (_log("接收区开关", b),
                                   view_ref[0].set_receive_open(b)),
        "choose_dir":   lambda: _log("选择接收目录"),
        "copy":         lambda url: (_log("复制", url),
                                     view_ref[0].toast("已复制到剪贴板")),
        "qr":           lambda url: (_log("二维码", url),
                                     view_ref[0].show_qr(url)),
        "save_settings": lambda: (_log("保存设置"),
                                  view_ref[0].toast("设置已保存")),
    }


# ──────────────────────────────────────────────────────────
# 截图工具（用于交付截图）
# ──────────────────────────────────────────────────────────
def _screenshot(root, name: str) -> None:
    try:
        import subprocess
        # 用 PIL ImageGrab 截取窗口
        from PIL import ImageGrab
        root.update()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        w = root.winfo_width()
        h = root.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        out_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, name)
        img.save(path)
        print(f"[截图] 已保存：{path}")
    except Exception as exc:
        print(f"[截图] 失败：{exc}")


# ──────────────────────────────────────────────────────────
# 主窗口
# ──────────────────────────────────────────────────────────
def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    if _HAS_DND:
        root = TkinterDnD.Tk()
        # TkinterDnD.Tk 不是 CTk，手动设置外观
        root.configure(bg=THEME["colors"]["bg"])
    else:
        root = ctk.CTk()
        root.configure(fg_color=THEME["colors"]["bg"])

    root.title("分享助手 Pro · 玄天典籍 · 预览")
    root.geometry("1280x820")
    root.minsize(1080, 680)

    view_ref: list = [None]
    on = _make_on(view_ref)

    view = ShareView(root, THEME, on)
    view.pack(fill="both", expand=True)
    view_ref[0] = view

    # 填入假数据
    view.set_state("idle", "")
    view.set_groups(FAKE_GROUPS, FAKE_CUR_GRP)
    view.set_files(FAKE_FILES)
    view.set_received(FAKE_RECEIVED)
    view.set_receive_open(True)
    view.set_quota("本次已接收 357 MB / 不限量")
    view.set_remaining(-1)
    view._recv_dir_var.set("D:\\收件箱\\玄天典籍")
    view._file_path_lbl.configure(text="D:\\分享助手\\文件库\\秘籍珍藏")

    # 自动截图辅助（延迟执行，让窗口先渲染出来）
    def _auto_snap():
        # 文件库页
        view.show_page("files")
        root.update()
        _screenshot(root, "01_文件库.png")

        # 接收区页
        view.show_page("receive")
        root.update()
        _screenshot(root, "02_接收区.png")

        # 设置页
        view.show_page("settings")
        root.update()
        _screenshot(root, "03_设置.png")

        # 还原到文件库页
        view.show_page("files")
        print("[预览] 自动截图完成，可关闭窗口或继续手动操作。")

    root.after(800, _auto_snap)
    root.mainloop()


if __name__ == "__main__":
    main()
