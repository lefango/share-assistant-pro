# -*- coding: utf-8 -*-
"""默认界面（customtkinter）。

分成三页：文件库 / 接收区 / 设置，右侧常驻「分享状态」栏。
所有耗时操作都丢到后台线程，结果通过队列回到主线程 —— 后台线程绝不碰 Tk 控件。
"""
from __future__ import annotations

import io
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from ... import paths, skin
from ...dnd import parse_drop_text, register_drop_target
from ...library import Library, classify, human_size, human_time, unique_path
from ...service import ERROR, IDLE, RUNNING, STARTING, STOPPED
from ...share import qr
from ...share.options import TTL_CHOICES
from ..dialog_sources import choose_sources

TTL_LABELS = [label for label, _ in TTL_CHOICES]
TTL_MAP = dict(TTL_CHOICES)
STATE_TEXT = {IDLE: "未开始", STARTING: "连接中…", RUNNING: "运行中",
              ERROR: "出错", STOPPED: "已停止"}

ICONS = {
    "图片": "🖼", "视频": "🎬", "音频": "🎵", "文档": "📄",
    "压缩包": "🗜", "安装包": "📦", "其他": "📎", "文件夹": "📁",
}


class Palette:
    def __init__(self, theme: dict) -> None:
        for key in ("bg", "panel", "card", "card_hover", "border", "border_hi",
                    "text", "text_dim", "accent", "accent_hover", "accent2",
                    "ok", "warn", "danger"):
            setattr(self, key, skin.color(theme, key))
        self.font = theme.get("font") or "Microsoft YaHei UI"
        self.radius = int(theme.get("radius") or 14)


def _copy_image_to_clipboard(image) -> bool:
    """把 PIL 图片放进 Windows 剪贴板（CF_DIB）。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        buf = io.BytesIO()
        image.convert("RGB").save(buf, "BMP")
        data = buf.getvalue()[14:]  # 去掉 BITMAPFILEHEADER，剩 DIB

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.restype = ctypes.c_void_p

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            size = len(data)
            handle = kernel32.GlobalAlloc(0x0042, size)  # GMEM_MOVEABLE | GMEM_ZEROINIT
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return False
            ctypes.memmove(ptr, data, size)
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(8, wintypes.HANDLE(handle)):  # CF_DIB
                return False
        finally:
            user32.CloseClipboard()
        return True
    except Exception:
        return False


class App(ctk.CTk):
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.svc = ctx.service
        self.theme = ctx.theme
        self.pal = Palette(self.theme)
        super().__init__(fg_color=self.pal.bg)
        self.TkdndVersion = TkinterDnD.require(self)

        self.ui_scale = float(ctk.ScalingTracker.get_widget_scaling(self)) or 1.0
        self.q: queue.Queue = queue.Queue()
        self.logs: list[str] = []
        self.current_group = self.cfg.get("last_group") or ""
        self._busy = False
        self._state = IDLE
        self._qrimg = None

        self.title(f"{self.theme.get('title') or '分享助手'} · 分享助手 Pro")
        self.geometry("1280x820")
        self.minsize(1080, 680)
        icon = os.path.join(paths.resource_dir(), "assets", "app.ico")
        if os.path.isfile(icon):
            try:
                self.after(50, lambda: self.iconbitmap(icon))
            except Exception:
                pass

        self._build()
        self._render_groups()
        self._render_files()
        self._refresh_receive_list()
        self._sync_all()
        self._pump()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.cfg.get("auto_start"):
            self.after(700, lambda: self._start_share(pick=False))

    # ---------------------------------------------------------------- 尺寸
    def p(self, value: float) -> int:
        return int(round(value * self.ui_scale))

    def font(self, size: int, bold: bool = False):
        return ctk.CTkFont(family=self.pal.font, size=int(round(size)),
                           weight="bold" if bold else "normal")

    # ---------------------------------------------------------------- 骨架
    def _build(self) -> None:
        pal = self.pal
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---- 左侧导航
        self.sidebar = ctk.CTkFrame(self, width=self.p(208), corner_radius=0,
                                    fg_color=pal.panel)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(2, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=self.p(18), pady=(self.p(22), self.p(18)))
        ctk.CTkLabel(brand, text="🗂", font=self.font(24)).pack(side="left")
        box = ctk.CTkFrame(brand, fg_color="transparent")
        box.pack(side="left", padx=(self.p(8), 0))
        ctk.CTkLabel(box, text="分享助手", font=self.font(16, True),
                     text_color=pal.text).pack(anchor="w")
        ctk.CTkLabel(box, text=f"Pro {paths.VERSION}", font=self.font(11),
                     text_color=pal.text_dim).pack(anchor="w")

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=self.p(10))
        self.nav_btns: dict[str, ctk.CTkButton] = {}
        for key, label, icon in (("files", "文件库", "📁"),
                                 ("receive", "接收区", "📥"),
                                 ("settings", "设置", "⚙")):
            btn = ctk.CTkButton(nav, text=f"  {icon}   {label}", anchor="w",
                                height=self.p(42), corner_radius=10,
                                font=self.font(13), fg_color="transparent",
                                hover_color=pal.card, text_color=pal.text_dim,
                                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", pady=self.p(3))
            self.nav_btns[key] = btn

        foot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=self.p(14), pady=self.p(14))
        self.side_dot = ctk.CTkLabel(foot, text="●", font=self.font(12),
                                     text_color=pal.text_dim)
        self.side_dot.pack(side="left")
        self.side_state = ctk.CTkLabel(foot, text="未开始", font=self.font(11),
                                       text_color=pal.text_dim)
        self.side_state.pack(side="left", padx=(self.p(4), 0))
        self.side_link = ctk.CTkLabel(foot, text="", font=self.font(10),
                                      text_color=pal.text_dim, wraplength=self.p(180),
                                      justify="left")
        self.side_link.pack(side="top", anchor="w", pady=(self.p(6), 0))

        # ---- 主体
        body = ctk.CTkFrame(self, fg_color=pal.bg)
        body.grid(row=0, column=1, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.host = ctk.CTkFrame(body, fg_color=pal.bg)
        self.host.grid(row=0, column=0, sticky="nsew", padx=(self.p(20), self.p(10)),
                       pady=self.p(18))
        self.host.grid_rowconfigure(0, weight=1)
        self.host.grid_columnconfigure(0, weight=1)

        self.rail = ctk.CTkFrame(body, width=self.p(336), corner_radius=0,
                                 fg_color=pal.panel)
        self.rail.grid(row=0, column=1, sticky="nsew")
        self.rail.grid_propagate(False)
        self.rail.grid_columnconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.pages["files"] = self._build_files_page()
        self.pages["receive"] = self._build_receive_page()
        self.pages["settings"] = self._build_settings_page()
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self._build_rail()
        self.show_page("files")

    # ---------------------------------------------------------------- 通用小件
    def card(self, parent, **kwargs) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=self.pal.card, corner_radius=self.pal.radius,
                            border_width=1, border_color=self.pal.border, **kwargs)

    def section(self, parent, title: str, subtitle: str = "") -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        box = self.card(parent)
        box.pack(fill="x", pady=(0, self.p(12)))
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=self.p(16), pady=(self.p(14), self.p(6)))
        ctk.CTkLabel(head, text=title, font=self.font(14, True),
                     text_color=self.pal.text).pack(side="left")
        if subtitle:
            ctk.CTkLabel(head, text=subtitle, font=self.font(11),
                         text_color=self.pal.text_dim).pack(side="left", padx=self.p(8))
        body = ctk.CTkFrame(box, fg_color="transparent")
        body.pack(fill="x", padx=self.p(16), pady=(0, self.p(14)))
        return box, body

    def small_btn(self, parent, text: str, command, kind: str = "ghost",
                  width: int = 0) -> ctk.CTkButton:
        pal = self.pal
        colors = {
            "ghost": dict(fg_color=pal.card_hover, hover_color=pal.border_hi,
                          text_color=pal.text),
            "accent": dict(fg_color=pal.accent, hover_color=pal.accent_hover,
                           text_color="#ffffff"),
            "danger": dict(fg_color="transparent", hover_color=pal.card_hover,
                           text_color=pal.danger, border_width=1, border_color=pal.border),
        }[kind]
        btn = ctk.CTkButton(parent, text=text, command=command,
                            height=self.p(32), corner_radius=self.p(9),
                            font=self.font(12), width=width or self.p(96), **colors)
        return btn

    def entry(self, parent, textvariable=None, placeholder: str = "") -> ctk.CTkEntry:
        return ctk.CTkEntry(parent, textvariable=textvariable, height=self.p(36),
                            corner_radius=self.p(9), font=self.font(12),
                            fg_color=self.pal.bg, border_color=self.pal.border,
                            border_width=1, text_color=self.pal.text,
                            placeholder_text=placeholder)

    def readonly_entry(self, parent, textvariable=None) -> ctk.CTkEntry:
        entry = self.entry(parent, textvariable)
        entry.bind("<Key>", lambda event: "break")
        return entry

    # ---------------------------------------------------------------- 文件库页
    def _build_files_page(self) -> ctk.CTkFrame:
        pal = self.pal
        page = ctk.CTkFrame(self.host, fg_color=pal.bg)
        page.grid_rowconfigure(3, weight=1)
        page.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(head, text="文件库", font=self.font(22, True),
                     text_color=pal.text).pack(side="left")
        ctk.CTkLabel(head, text=self.cfg.get("library_dir"), font=self.font(11),
                     text_color=pal.text_dim).pack(side="left", padx=self.p(10))
        self.small_btn(head, "打开文件夹", self._open_library, "ghost",
                       width=self.p(104)).pack(side="right")

        chips = ctk.CTkScrollableFrame(page, fg_color="transparent", height=self.p(58),
                                       orientation="horizontal",
                                       scrollbar_button_color=pal.border,
                                       scrollbar_button_hover_color=pal.accent)
        chips.grid(row=1, column=0, sticky="ew", pady=(self.p(12), self.p(4)))
        self.chips = chips

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(self.p(6), self.p(8)))
        self.small_btn(bar, "导入文件", self._import_files, "accent").pack(side="left")
        self.small_btn(bar, "导入文件夹", self._import_folder).pack(side="left",
                                                                    padx=self.p(8))
        self.small_btn(bar, "新建分组", self._new_group).pack(side="left")
        self.small_btn(bar, "刷新", self._render_files).pack(side="right")
        self.file_hint = ctk.CTkLabel(bar, text="", font=self.font(11),
                                      text_color=pal.text_dim)
        self.file_hint.pack(side="right", padx=self.p(10))

        self.file_list = ctk.CTkScrollableFrame(page, fg_color="transparent",
                                                scrollbar_button_color=pal.border,
                                                scrollbar_button_hover_color=pal.accent)
        self.file_list.grid(row=3, column=0, sticky="nsew")
        self.file_list.grid_columnconfigure(0, weight=1)
        return page

    def _render_groups(self) -> None:
        pal = self.pal
        for child in self.chips.winfo_children():
            child.destroy()
        groups = self.ctx.library.groups()
        if groups and self.current_group not in groups:
            self.current_group = groups[0]
        if not groups:
            self.current_group = ""
        for name in groups:
            active = name == self.current_group
            btn = ctk.CTkButton(
                self.chips, text=f"📁 {name}", height=self.p(34),
                corner_radius=self.p(17), font=self.font(12),
                fg_color=pal.accent if active else pal.card,
                hover_color=pal.accent_hover if active else pal.card_hover,
                text_color="#ffffff" if active else pal.text,
                command=lambda n=name: self._select_group(n))
            btn.pack(side="left", padx=(0, self.p(8)), pady=self.p(4))
            btn.bind("<Button-3>", lambda e, n=name: self._group_menu(e, n))
        add = ctk.CTkButton(self.chips, text="＋ 新建", width=self.p(86),
                            height=self.p(34), corner_radius=self.p(17),
                            font=self.font(12), fg_color="transparent",
                            border_width=1, border_color=pal.border,
                            hover_color=pal.card_hover, text_color=pal.text_dim,
                            command=self._new_group)
        add.pack(side="left", padx=(0, self.p(8)), pady=self.p(4))

    def _group_menu(self, event, name: str) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="重命名分组", command=lambda: self._rename_group(name))
        menu.add_command(label="删除分组", command=lambda: self._delete_group(name))
        menu.add_separator()
        menu.add_command(label="打开这个文件夹",
                         command=lambda: os.startfile(self.ctx.library.group_dir(name)))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _select_group(self, name: str) -> None:
        self.current_group = name
        self.cfg.set("last_group", name)
        self._render_groups()
        self._render_files()

    def _current_dir(self) -> str:
        if not self.current_group:
            return self.ctx.library.root
        return self.ctx.library.group_dir(self.current_group)

    def _render_files(self) -> None:
        pal = self.pal
        for child in self.file_list.winfo_children():
            child.destroy()
        folder = self._current_dir()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            entries = []
        count = 0
        for entry in entries[:800]:
            if entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            is_dir = entry.is_dir()
            icon = ICONS.get("文件夹" if is_dir else classify(entry.name), "📎")
            row = ctk.CTkFrame(self.file_list, fg_color=pal.card, corner_radius=self.p(10),
                               border_width=1, border_color=pal.border)
            row.grid(row=count, column=0, sticky="ew", pady=self.p(3), padx=self.p(2))
            row.grid_columnconfigure(1, weight=1)
            count += 1
            ctk.CTkLabel(row, text=icon, font=self.font(17)).grid(
                row=0, column=0, padx=(self.p(12), self.p(8)), pady=self.p(8))
            text_box = ctk.CTkFrame(row, fg_color="transparent")
            text_box.grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(text_box, text=entry.name, font=self.font(12.5),
                         text_color=pal.text, anchor="w").pack(anchor="w")
            meta = ("文件夹" if is_dir else human_size(stat.st_size)) + \
                   f"  ·  {human_time(stat.st_mtime)}"
            ctk.CTkLabel(text_box, text=meta, font=self.font(10.5),
                         text_color=pal.text_dim, anchor="w").pack(anchor="w")
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=2, padx=self.p(10))
            ctk.CTkButton(actions, text="打开", width=self.p(58), height=self.p(28),
                          corner_radius=self.p(8), font=self.font(11),
                          fg_color=pal.card_hover, hover_color=pal.border_hi,
                          text_color=pal.text,
                          command=lambda p=entry.path, d=is_dir: self._open_path(p, d)
                          ).pack(side="left", padx=self.p(3))
            ctk.CTkButton(actions, text="删除", width=self.p(58), height=self.p(28),
                          corner_radius=self.p(8), font=self.font(11),
                          fg_color="transparent", hover_color=pal.card_hover,
                          text_color=pal.danger, border_width=1, border_color=pal.border,
                          command=lambda p=entry.path, n=entry.name: self._delete_path(p, n)
                          ).pack(side="left", padx=self.p(3))

        if not count:
            hint = ctk.CTkLabel(self.file_list,
                                text="这里还是空的 —— 把文件拖进来，或点上面的「导入文件」",
                                font=self.font(12), text_color=pal.text_dim)
            hint.grid(row=0, column=0, pady=self.p(60))
        self.file_hint.configure(text=f"{count} 项")
        register_drop_target(self.file_list, self._on_drop)

    def _on_drop(self, event) -> None:
        items = parse_drop_text(self, event.data)
        self._place_into(items)

    def _place_into(self, items: list[str]) -> None:
        if not items:
            return
        if not self.current_group:
            self._new_group(after=lambda: self._place_into(items))
            return
        dest = self._current_dir()

        def work():
            result = self.ctx.library.place(items, dest, mode="copy")
            self.q.put(lambda: self._after_place(result))

        threading.Thread(target=work, daemon=True).start()

    def _after_place(self, result) -> None:
        self._render_files()
        if result.failed:
            messagebox.showwarning("部分没有导入", "\n".join(
                f"{os.path.basename(src)}：{why}" for src, why in result.failed[:6]))
        self.toast(f"已导入 {result.ok_count} 个")

    def _import_files(self) -> None:
        files = filedialog.askopenfilenames(title="选择要放进文件库的文件")
        self._place_into(list(files))

    def _import_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择要放进文件库的文件夹")
        if folder:
            self._place_into([folder])

    def _new_group(self, after=None) -> None:
        dialog = ctk.CTkInputDialog(text="给新分组起个名字：", title="新建分组")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.ctx.library.create_group(name)
        except Exception as exc:
            messagebox.showerror("建不了这个分组", str(exc))
            return
        self.current_group = name.strip()
        self._render_groups()
        self._render_files()
        if after:
            after()

    def _rename_group(self, name: str) -> None:
        dialog = ctk.CTkInputDialog(text="新的分组名：", title="重命名分组")
        value = dialog.get_input()
        if not value or value.strip() == name:
            return
        try:
            self.ctx.library.rename_group(name, value)
        except Exception as exc:
            messagebox.showerror("改名失败", str(exc))
            return
        self.current_group = value.strip()
        self._render_groups()
        self._render_files()

    def _delete_group(self, name: str) -> None:
        if not messagebox.askyesno("删除分组", f"确定删除分组「{name}」吗？\n里面的文件会被删掉。"):
            return
        self.ctx.library.delete_group(name)
        self._render_groups()
        self._render_files()

    def _open_path(self, path: str, is_dir: bool) -> None:
        try:
            if is_dir:
                os.startfile(path)
            else:
                os.startfile(path)
        except Exception as exc:
            messagebox.showerror("打不开", str(exc))

    def _delete_path(self, path: str, name: str) -> None:
        if not messagebox.askyesno("删除", f"确定删除「{name}」吗？"):
            return
        try:
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))
        self._render_files()

    def _open_library(self) -> None:
        os.makedirs(self.ctx.library.root, exist_ok=True)
        os.startfile(self.ctx.library.root)

    # ---------------------------------------------------------------- 接收页
    def _build_receive_page(self) -> ctk.CTkFrame:
        pal = self.pal
        page = ctk.CTkFrame(self.host, fg_color=pal.bg)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="接收区", font=self.font(22, True),
                     text_color=pal.text).pack(side="left")
        ctk.CTkLabel(head, text="把这边的链接发出去，对方打开网页就能把文件传回来",
                     font=self.font(11), text_color=pal.text_dim).pack(side="left",
                                                                       padx=self.p(10))

        _, body = self.section(page, "接收开关", "关掉之后对方打不开接收页")
        self.receive_switch = ctk.CTkSwitch(
            body, text="允许别人往我这里传文件", font=self.font(12),
            text_color=pal.text, progress_color=pal.accent,
            button_color=pal.text, button_hover_color=pal.text_dim,
            command=self._toggle_receive)
        self.receive_switch.pack(anchor="w")
        self.receive_state = ctk.CTkLabel(body, text="", font=self.font(11),
                                          text_color=pal.text_dim)
        self.receive_state.pack(anchor="w", pady=(self.p(6), 0))

        limit_row = ctk.CTkFrame(body, fg_color="transparent")
        limit_row.pack(fill="x", pady=(self.p(8), 0))
        ctk.CTkLabel(limit_row, text="本次最多接收", font=self.font(11),
                     text_color=pal.text_dim).pack(side="left")
        self.limit_var = tk.StringVar(value=self._limit_text(self.cfg.get("receive_limit")))
        limit_entry = self.entry(limit_row, self.limit_var, "如 500MB / 2GB / 不限")
        limit_entry.pack(side="left", padx=self.p(8), fill="x", expand=True)
        limit_entry.bind("<Return>", lambda event: self._apply_limit())
        self.small_btn(limit_row, "保存", self._apply_limit, "ghost",
                       width=self.p(56)).pack(side="left")
        ctk.CTkLabel(body, text="数量自己填，不设上限；改完下次开分享生效",
                     font=self.font(10), text_color=pal.text_dim).pack(
            anchor="w", pady=(self.p(4), 0))

        box, body2 = self.section(page, "接收链接", "对方要用这个，不是上面的分享链接")
        line = ctk.CTkFrame(body2, fg_color="transparent")
        line.pack(fill="x")
        self.receive_var = tk.StringVar(value="")
        self.readonly_entry(line, self.receive_var).pack(side="left", fill="x", expand=True)
        self.small_btn(line, "复制", lambda: self._copy(self.receive_var.get()),
                       "ghost", width=self.p(58)).pack(side="left", padx=self.p(6))
        self.small_btn(line, "二维码", lambda: self._show_qr(self.receive_var.get(),
                                                             "接收二维码"),
                       "ghost", width=self.p(72)).pack(side="left")
        self.small_btn(line, "刷新链接", self._refresh_link, "ghost",
                       width=self.p(86)).pack(side="left", padx=(self.p(6), 0))
        ctk.CTkLabel(body2, text="链接每次启动都会变；想立刻换一条就点「刷新链接」。",
                     font=self.font(10.5), text_color=pal.text_dim).pack(
            anchor="w", pady=(self.p(8), 0))

        box3, body3 = self.section(page, "收到的文件存在哪", "")
        line3 = ctk.CTkFrame(body3, fg_color="transparent")
        line3.pack(fill="x")
        self.receive_dir_var = tk.StringVar(value=self.cfg.get("receive_dir"))
        ctk.CTkEntry(line3, textvariable=self.receive_dir_var, height=self.p(34),
                     font=self.font(11), fg_color=pal.bg, border_color=pal.border,
                     text_color=pal.text).pack(side="left", fill="x", expand=True)
        self.small_btn(line3, "选择", self._choose_receive_dir, "ghost",
                       width=self.p(64)).pack(side="left", padx=self.p(6))
        self.small_btn(line3, "打开", self._open_receive_dir, "ghost",
                       width=self.p(64)).pack(side="left")

        box4 = self.card(page)
        box4.pack(fill="both", expand=True)
        box4.grid_rowconfigure(1, weight=1)
        box4.grid_columnconfigure(0, weight=1)
        head4 = ctk.CTkFrame(box4, fg_color="transparent")
        head4.grid(row=0, column=0, sticky="ew", padx=self.p(16), pady=self.p(10))
        ctk.CTkLabel(head4, text="最近收到的文件", font=self.font(14, True),
                     text_color=pal.text).pack(side="left")
        self.small_btn(head4, "刷新", self._refresh_receive_list, "ghost",
                       width=self.p(64)).pack(side="right")
        self.received_list = ctk.CTkScrollableFrame(box4, fg_color="transparent",
                                                    scrollbar_button_color=pal.border)
        self.received_list.grid(row=1, column=0, sticky="nsew", padx=self.p(10),
                                pady=(0, self.p(10)))
        self.received_list.grid_columnconfigure(0, weight=1)
        return page

    def _limit_text(self, value) -> str:
        try:
            value = int(value or 0)
        except Exception:
            value = 0
        if value <= 0:
            return "不限"
        for unit, size in (("TB", 1024 ** 4), ("GB", 1024 ** 3), ("MB", 1024 ** 2)):
            if value >= size and value % size == 0:
                return f"{value // size}{unit}"
        return f"{value}"

    def _parse_limit(self, text: str) -> int:
        raw = (text or "").strip().replace(" ", "").upper()
        if raw in ("", "0", "不限", "无", "UNLIMITED"):
            return 0
        import re
        match = re.match(r"^([0-9]+(?:\.[0-9]+)?)(TB|GB|MB|KB|B)?$", raw)
        if not match:
            raise ValueError("看不懂这个数量，写 500MB 或 2GB 或 不限")
        number = float(match.group(1))
        unit = match.group(2) or "MB"
        factor = {"B": 1, "KB": 1024, "MB": 1024 ** 2,
                  "GB": 1024 ** 3, "TB": 1024 ** 4}[unit]
        return int(number * factor)

    def _apply_limit(self) -> None:
        try:
            size = self._parse_limit(self.limit_var.get())
        except ValueError as exc:
            messagebox.showwarning("接收上限", str(exc))
            return
        self.cfg.set("receive_limit", size)
        self.limit_var.set(self._limit_text(size))
        self.toast("接收上限已保存，下次开分享生效")

    def _toggle_receive(self) -> None:
        opened = bool(self.receive_switch.get())
        self.cfg.set("receive_open", opened)
        self.svc.set_receive_open(opened)
        self.receive_state.configure(
            text="接收区已打开" if opened else "接收区已关闭，对方打开会看到提示")
        self._sync_all()

    def _choose_receive_dir(self) -> None:
        folder = filedialog.askdirectory(title="收到的文件放到哪",
                                         initialdir=self.cfg.get("receive_dir"))
        if not folder:
            return
        self.cfg.set("receive_dir", folder)
        self.receive_dir_var.set(folder)
        os.makedirs(folder, exist_ok=True)
        if self.svc.options:
            self.svc.apply(receive_dir=folder)
        self._refresh_receive_list()
        self.toast("收件目录已更新")

    def _open_receive_dir(self) -> None:
        folder = self.receive_dir_var.get()
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    def _refresh_receive_list(self) -> None:
        pal = self.pal
        for child in self.received_list.winfo_children():
            child.destroy()
        folder = self.receive_dir_var.get() if hasattr(self, "receive_dir_var") else \
            self.cfg.get("receive_dir")
        items = []
        try:
            for entry in os.scandir(folder):
                if entry.is_file() and not entry.name.startswith("."):
                    stat = entry.stat()
                    items.append((entry.name, entry.path, stat.st_size, stat.st_mtime))
        except OSError:
            items = []
        items.sort(key=lambda item: item[3], reverse=True)
        if not items:
            ctk.CTkLabel(self.received_list, text="还没有人传文件过来",
                         font=self.font(12), text_color=pal.text_dim).grid(
                row=0, column=0, pady=self.p(40))
            return
        for index, (name, path, size, mtime) in enumerate(items[:200]):
            row = ctk.CTkFrame(self.received_list, fg_color=pal.bg, corner_radius=self.p(9))
            row.grid(row=index, column=0, sticky="ew", pady=self.p(2), padx=self.p(2))
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=name, font=self.font(12), text_color=pal.text,
                         anchor="w").grid(row=0, column=0, sticky="ew",
                                          padx=self.p(12), pady=(self.p(6), 0))
            ctk.CTkLabel(row, text=f"{human_size(size)}  ·  {human_time(mtime)}",
                         font=self.font(10), text_color=pal.text_dim,
                         anchor="w").grid(row=1, column=0, sticky="ew", padx=self.p(12),
                                          pady=(0, self.p(6)))
            ctk.CTkButton(row, text="打开", width=self.p(54), height=self.p(26),
                          corner_radius=self.p(8), font=self.font(11),
                          fg_color=pal.card_hover, hover_color=pal.border_hi,
                          text_color=pal.text,
                          command=lambda p=path: os.startfile(p)).grid(
                row=0, column=1, rowspan=2, padx=self.p(10))

    # ---------------------------------------------------------------- 设置页
    def _build_settings_page(self) -> ctk.CTkFrame:
        pal = self.pal
        page = ctk.CTkScrollableFrame(self.host, fg_color=pal.bg,
                                      scrollbar_button_color=pal.border)

        ctk.CTkLabel(page, text="设置", font=self.font(22, True),
                     text_color=pal.text, anchor="w").pack(fill="x", pady=(0, self.p(12)))

        _, body = self.section(page, "目录")
        self._dir_row(body, "文件库", "library_dir")
        self._dir_row(body, "收件箱", "receive_dir")

        _, body2 = self.section(page, "分享默认值")
        row = ctk.CTkFrame(body2, fg_color="transparent")
        row.pack(fill="x", pady=self.p(4))
        ctk.CTkLabel(row, text="网页标题", font=self.font(12), width=self.p(80),
                     anchor="w", text_color=pal.text_dim).pack(side="left")
        self.title_var = tk.StringVar(value=self.cfg.get("title"))
        self.entry(row, self.title_var).pack(side="left", fill="x", expand=True)

        row = ctk.CTkFrame(body2, fg_color="transparent")
        row.pack(fill="x", pady=self.p(4))
        ctk.CTkLabel(row, text="访问密码", font=self.font(12), width=self.p(80),
                     anchor="w", text_color=pal.text_dim).pack(side="left")
        self.pw_var = tk.StringVar(value=self.cfg.get("password"))
        self.entry(row, self.pw_var, "留空则不需要密码").pack(side="left", fill="x",
                                                             expand=True)

        row = ctk.CTkFrame(body2, fg_color="transparent")
        row.pack(fill="x", pady=self.p(4))
        ctk.CTkLabel(row, text="有效期", font=self.font(12), width=self.p(80),
                     anchor="w", text_color=pal.text_dim).pack(side="left")
        self.ttl_var = tk.StringVar(value=self._ttl_label(self.cfg.get("ttl")))
        ctk.CTkOptionMenu(row, values=TTL_LABELS, variable=self.ttl_var,
                          width=self.p(150), height=self.p(34), corner_radius=self.p(9),
                          font=self.font(12), fg_color=pal.card_hover,
                          button_color=pal.border_hi, button_hover_color=pal.accent,
                          dropdown_fg_color=pal.panel,
                          dropdown_hover_color=pal.card_hover,
                          text_color=pal.text).pack(side="left")

        self.auto_start_var = tk.IntVar(value=1 if self.cfg.get("auto_start") else 0)
        self.new_link_var = tk.IntVar(value=1 if self.cfg.get("auto_new_link") else 0)
        for text, var in (("启动程序时自动开启分享（每次都是新链接）", self.auto_start_var),):
            ctk.CTkSwitch(body2, text=text, variable=var, font=self.font(12),
                          text_color=pal.text, progress_color=pal.accent,
                          button_color=pal.text,
                          button_hover_color=pal.text_dim).pack(anchor="w", pady=self.p(4))

        _, body3 = self.section(page, "外观 / 界面", "换皮肤后桌面和网页一起变；换 UI 实现要重启")
        row3 = ctk.CTkFrame(body3, fg_color="transparent")
        row3.pack(fill="x", pady=self.p(4))
        ctk.CTkLabel(row3, text="皮肤", font=self.font(12), width=self.p(80),
                     anchor="w", text_color=pal.text_dim).pack(side="left")
        skins = skin.available()
        self.skin_var = tk.StringVar(value=self.cfg.get("skin") or "default")
        ctk.CTkOptionMenu(row3, values=skins, variable=self.skin_var,
                          width=self.p(150), height=self.p(34), corner_radius=self.p(9),
                          font=self.font(12), fg_color=pal.card_hover,
                          button_color=pal.border_hi, button_hover_color=pal.accent,
                          dropdown_fg_color=pal.panel,
                          dropdown_hover_color=pal.card_hover,
                          text_color=pal.text).pack(side="left")

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill="x", pady=self.p(10))
        self.small_btn(actions, "保存设置", self._save_settings, "accent",
                       width=self.p(120)).pack(side="left")
        self.small_btn(actions, "自检", self._run_check, "ghost",
                       width=self.p(80)).pack(side="left", padx=self.p(8))

        ctk.CTkLabel(page, text=f"分享助手 Pro {paths.VERSION} · 配置：{self.cfg.path}",
                     font=self.font(10.5), text_color=pal.text_dim,
                     anchor="w").pack(fill="x", pady=(0, self.p(20)))
        return page

    def _dir_row(self, parent, label: str, key: str) -> None:
        pal = self.pal
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=self.p(4))
        ctk.CTkLabel(row, text=label, font=self.font(12), width=self.p(60),
                     anchor="w", text_color=pal.text_dim).pack(side="left")
        var = tk.StringVar(value=self.cfg.get(key))
        setattr(self, f"{key}_var", var)
        self.entry(row, var).pack(side="left", fill="x", expand=True)
        self.small_btn(row, "选择", lambda k=key, v=var: self._pick_dir(k, v),
                       "ghost", width=self.p(64)).pack(side="left", padx=self.p(6))

    def _pick_dir(self, key: str, var: tk.StringVar) -> None:
        folder = filedialog.askdirectory(initialdir=self.cfg.get(key))
        if folder:
            var.set(folder)

    def _save_settings(self) -> None:
        old_lib = self.cfg.get("library_dir")
        skin_changed = self.skin_var.get() != self.cfg.get("skin")
        self.cfg.update({
            "library_dir": self.library_dir_var.get(),
            "receive_dir": self.receive_dir_var.get(),
            "title": self.title_var.get(),
            "password": self.pw_var.get(),
            "ttl": TTL_MAP.get(self.ttl_var.get(), 0),
            "auto_start": bool(self.auto_start_var.get()),
            "auto_new_link": bool(self.new_link_var.get()),
            "skin": self.skin_var.get(),
        })
        self.ctx.library = Library(self.cfg.get("library_dir"))
        os.makedirs(self.cfg.get("library_dir"), exist_ok=True)
        os.makedirs(self.cfg.get("receive_dir"), exist_ok=True)
        self.receive_dir_var.set(self.cfg.get("receive_dir"))
        if self.cfg.get("library_dir") != old_lib:
            self.current_group = ""
            self._render_groups()
            self._render_files()
        if self.svc.running:
            self.svc.apply(password=self.cfg.get("password"),
                           ttl=self.cfg.get("ttl"),
                           receive_dir=self.cfg.get("receive_dir"))
        self._sync_all()
        self.toast("设置已保存" + ("（换皮肤要重启程序）" if skin_changed else ""))

    def _run_check(self) -> None:
        from ... import main as entry
        self.toast("自检结果已打印到控制台")

    # ---------------------------------------------------------------- 右栏
    def _build_rail(self) -> None:
        pal = self.pal
        rail = self.rail
        pad = self.p(18)
        ctk.CTkLabel(rail, text="分享", font=self.font(18, True),
                     text_color=pal.text).grid(row=0, column=0, sticky="w",
                                               padx=pad, pady=(self.p(22), self.p(10)))

        status = ctk.CTkFrame(rail, fg_color=pal.card, corner_radius=pal.radius,
                              border_width=1, border_color=pal.border)
        status.grid(row=1, column=0, sticky="ew", padx=pad)
        inner = ctk.CTkFrame(status, fg_color="transparent")
        inner.pack(fill="x", padx=self.p(14), pady=self.p(12))
        self.rail_dot = ctk.CTkLabel(inner, text="●", font=self.font(12),
                                     text_color=pal.text_dim)
        self.rail_dot.pack(side="left")
        self.rail_state = ctk.CTkLabel(inner, text="未开始", font=self.font(12, True),
                                       text_color=pal.text)
        self.rail_state.pack(side="left", padx=self.p(6))
        self.rail_timer = ctk.CTkLabel(inner, text="", font=self.font(11),
                                       text_color=pal.text_dim)
        self.rail_timer.pack(side="right")

        ctk.CTkLabel(rail, text="分享链接（给人下载）", font=self.font(11),
                     text_color=pal.text_dim).grid(row=2, column=0, sticky="w",
                                                   padx=pad, pady=(self.p(16), self.p(6)))
        self.share_var = tk.StringVar(value="")
        self.readonly_entry(rail, self.share_var).grid(row=3, column=0, sticky="ew",
                                                       padx=pad)
        row = ctk.CTkFrame(rail, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=pad, pady=(self.p(8), 0))
        self.small_btn(row, "复制链接", lambda: self._copy(self.share_var.get()),
                       "ghost", width=self.p(88)).pack(side="left")
        self.small_btn(row, "二维码", lambda: self._show_qr(self.share_var.get(),
                                                            "分享二维码"),
                       "ghost", width=self.p(76)).pack(side="left", padx=self.p(6))
        self.small_btn(row, "换链接", self._refresh_link, "ghost",
                       width=self.p(76)).pack(side="left")

        line = ctk.CTkFrame(rail, fg_color=pal.border, height=1)
        line.grid(row=5, column=0, sticky="ew", padx=pad, pady=self.p(16))

        ctk.CTkLabel(rail, text="访问密码", font=self.font(11),
                     text_color=pal.text_dim).grid(row=6, column=0, sticky="w", padx=pad)
        pw = ctk.CTkFrame(rail, fg_color="transparent")
        pw.grid(row=7, column=0, sticky="ew", padx=pad, pady=(self.p(6), 0))
        self.rail_pw = tk.StringVar(value=self.cfg.get("password"))
        self.entry(pw, self.rail_pw, "留空 = 不要密码").pack(side="left", fill="x",
                                                             expand=True)
        self.small_btn(pw, "应用", self._apply_password, "ghost",
                       width=self.p(56)).pack(side="left", padx=(self.p(6), 0))

        ctk.CTkLabel(rail, text="链接有效期", font=self.font(11),
                     text_color=pal.text_dim).grid(row=8, column=0, sticky="w",
                                                   padx=pad, pady=(self.p(12), 0))
        self.rail_ttl = tk.StringVar(value=self._ttl_label(self.cfg.get("ttl")))
        ctk.CTkOptionMenu(rail, values=TTL_LABELS, variable=self.rail_ttl,
                          command=self._apply_ttl, height=self.p(34),
                          corner_radius=self.p(9), font=self.font(12),
                          fg_color=pal.card_hover, button_color=pal.border_hi,
                          button_hover_color=pal.accent, dropdown_fg_color=pal.panel,
                          dropdown_hover_color=pal.card_hover,
                          text_color=pal.text).grid(row=9, column=0, sticky="ew",
                                                    padx=pad, pady=(self.p(6), 0))

        self.dl_var = tk.IntVar(value=1 if self.cfg.get("allow_download") else 0)
        ctk.CTkSwitch(rail, text="允许对方下载原文件", variable=self.dl_var,
                      font=self.font(12), text_color=pal.text,
                      progress_color=pal.accent, button_color=pal.text,
                      button_hover_color=pal.text_dim,
                      command=self._apply_download).grid(row=10, column=0, sticky="w",
                                                         padx=pad, pady=self.p(12))

        self.rail_main = ctk.CTkButton(rail, text="开始分享", height=self.p(46),
                                       corner_radius=self.p(11), font=self.font(14, True),
                                       fg_color=pal.accent, hover_color=pal.accent_hover,
                                       text_color="#ffffff", command=self._toggle_share)
        self.rail_main.grid(row=11, column=0, sticky="ew", padx=pad, pady=(self.p(6), 0))
        self.small_btn(rail, "局域网直传（本人设备）", self._start_lan, "ghost").grid(
            row=12, column=0, sticky="ew", padx=pad, pady=(self.p(8), 0))
        ctk.CTkLabel(rail, text="链接是临时的，关掉程序就失效。",
                     font=self.font(10.5), text_color=pal.text_dim).grid(
            row=13, column=0, sticky="w", padx=pad, pady=(self.p(14), 0))

    def _ttl_label(self, ttl) -> str:
        for label, value in TTL_CHOICES:
            if value == int(ttl or 0):
                return label
        return TTL_LABELS[0]

    def _apply_password(self) -> None:
        value = self.rail_pw.get()
        self.cfg.set("password", value)
        self.pw_var.set(value)
        self.svc.apply(password=value)
        self.toast("密码已更新" if value else "已取消密码")

    def _apply_ttl(self, label: str) -> None:
        ttl = TTL_MAP.get(label, 0)
        self.cfg.set("ttl", ttl)
        self.ttl_var.set(label)
        self.svc.apply(ttl=ttl)
        self._sync_all()

    def _apply_download(self) -> None:
        value = bool(self.dl_var.get())
        self.cfg.set("allow_download", value)
        self.svc.apply(allow_download=value)

    # ---------------------------------------------------------------- 分享动作
    def _sources(self) -> list[tuple[str, str]]:
        if self.current_group:
            return [(self.current_group, self.ctx.library.group_dir(self.current_group))]
        return [("文件库", self.ctx.library.root)]

    def _start_share(self, pick: bool = True) -> None:
        if self._busy:
            return
        if self.svc.running:
            self._stop_share()
            return
        if pick:
            sources = choose_sources(self, self.ctx.library,
                                     self.ctx.library.groups(),
                                     self.current_group or None)
            if not sources:
                return
        else:
            sources = self._sources()
        self._busy = True
        self.rail_main.configure(text="正在开启…", state="disabled")
        password = self.cfg.get("password")
        ttl = self.cfg.get("ttl")
        allow_dl = self.cfg.get("allow_download")
        receive_open = self.cfg.get("receive_open")
        receive_dir = self.cfg.get("receive_dir")
        receive_limit = self.cfg.get("receive_limit")
        title = self.cfg.get("title")

        def work():
            ok = self.svc.start(sources, title=title, password=password,
                                ttl_seconds=ttl, allow_download=allow_dl,
                                allow_upload=receive_open, receive_dir=receive_dir,
                                receive_limit=receive_limit)
            self.q.put(lambda: self._after_start(ok))

        threading.Thread(target=work, daemon=True).start()

    def _start_lan(self) -> None:
        if self._busy or self.svc.running:
            return
        sources = choose_sources(self, self.ctx.library, self.ctx.library.groups(),
                                 self.current_group or None)
        if not sources:
            return
        self._busy = True
        self.rail_main.configure(text="正在开启…", state="disabled")

        def work():
            ok = self.svc.start(sources, title=self.cfg.get("title"),
                                password=self.cfg.get("password"),
                                ttl_seconds=self.cfg.get("ttl"),
                                allow_download=self.cfg.get("allow_download"),
                                allow_upload=self.cfg.get("receive_open"),
                                receive_dir=self.cfg.get("receive_dir"),
                                receive_limit=self.cfg.get("receive_limit"), lan=True)
            self.q.put(lambda: self._after_start(ok))

        threading.Thread(target=work, daemon=True).start()

    def _after_start(self, ok: bool) -> None:
        self._busy = False
        self._sync_all()
        if not ok:
            self.toast("没能开起来，看看下面的提示", False)

    def _stop_share(self) -> None:
        self._busy = True
        self.rail_main.configure(text="正在停止…", state="disabled")

        def work():
            self.svc.stop()
            self.q.put(self._sync_all)

        threading.Thread(target=work, daemon=True).start()
        self._busy = False

    def _toggle_share(self) -> None:
        if self.svc.running:
            self._stop_share()
        else:
            self._start_share()

    def _refresh_link(self) -> None:
        if not self.svc.running:
            self.toast("先点「开始分享」", False)
            return
        self.toast("正在换新链接…")

        def work():
            ok = self.svc.refresh_link()
            self.q.put(lambda: self.toast("链接已更新" if ok else "换链接失败", ok))

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- 状态同步
    def _sync_all(self) -> None:
        pal = self.pal
        state = self.svc.state if self.svc.running else (
            STOPPED if self._state == STOPPED else self._state)
        text = STATE_TEXT.get(state, self.svc.message)
        colors = {RUNNING: pal.ok, STARTING: pal.warn, ERROR: pal.danger,
                  STOPPED: pal.text_dim, IDLE: pal.text_dim}
        color = colors.get(state, pal.text_dim)
        self._state = state
        try:
            self.rail_dot.configure(text_color=color)
            self.side_dot.configure(text_color=color)
            self.rail_state.configure(text=text)
            self.side_state.configure(text=text)
            self.rail_timer.configure(text=self._timer_text())
            url = self.svc.share_url
            self.share_var.set(url)
            self.receive_var.set(self.svc.receive_url)
            self.side_link.configure(text=url.replace("https://", "") if url else "")
            running = self.svc.running
            self.rail_main.configure(
                text="停止分享" if running else "开始分享",
                fg_color=pal.danger if running else pal.accent,
                hover_color="#c9444f" if running else pal.accent_hover,
                state="normal")
            self.receive_switch.select() if self.cfg.get("receive_open") else \
                self.receive_switch.deselect()
        except Exception:
            pass

    def _timer_text(self) -> str:
        remain = self.svc.remaining
        if remain < 0:
            return "不限时"
        if remain == 0:
            return "已到期"
        minutes, seconds = divmod(remain, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _on_event(self, kind: str, payload) -> None:
        if kind == "state":
            state, message = payload
            if state == RUNNING:
                self._state = RUNNING
            elif state in (ERROR, STOPPED):
                self._state = state
                if state == ERROR:
                    self.toast(message, False)
            self._sync_all()
        elif kind == "url":
            self._sync_all()
        elif kind == "log":
            self.logs.append(str(payload))
            del self.logs[:-400]

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.ctx.events.get_nowait()
                self._on_event(kind, payload)
        except queue.Empty:
            pass
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        try:
            self._sync_all()
        except Exception:
            pass
        self.after(1000, self._pump)

    # ---------------------------------------------------------------- 页面切换
    def show_page(self, key: str) -> None:
        pal = self.pal
        for name, page in self.pages.items():
            if name == key:
                page.grid()
                page.tkraise()
            else:
                page.grid_remove()
        for name, btn in self.nav_btns.items():
            active = name == key
            btn.configure(fg_color=pal.card if active else "transparent",
                          text_color=pal.text if active else pal.text_dim,
                          font=self.font(13, True) if active else self.font(13))
        if key == "settings":
            self.rail.grid_remove()
        else:
            self.rail.grid()
        if key == "receive":
            self._refresh_receive_list()

    # ---------------------------------------------------------------- 小工具
    def _copy(self, text: str) -> None:
        if not text:
            self.toast("还没有链接", False)
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.toast("已复制")

    def toast(self, text: str, ok: bool = True) -> None:
        pal = self.pal
        if getattr(self, "_toast", None) is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
        self._toast = ctk.CTkLabel(self, text=("✓ " if ok else "! ") + text,
                                   font=self.font(12), text_color="#ffffff",
                                   fg_color=pal.ok if ok else pal.danger,
                                   corner_radius=self.p(10), height=self.p(32),
                                   padx=self.p(14))
        self._toast.place(relx=0.5, rely=0.955, anchor="center")
        self.after(2200, self._hide_toast)

    def _hide_toast(self) -> None:
        if getattr(self, "_toast", None) is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
            self._toast = None

    def _show_qr(self, url: str, title: str = "二维码") -> None:
        if not url:
            self.toast("先开启分享才有链接", False)
            return
        image = qr.make_image(url, box=8, border=2)
        if image is None:
            self.toast("二维码库不可用", False)
            return
        pal = self.pal
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry(f"{self.p(380)}x{self.p(500)}")
        win.configure(fg_color=pal.bg)
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text=title, font=self.font(16, True),
                     text_color=pal.text).pack(pady=(self.p(18), self.p(4)))
        ctk.CTkLabel(win, text="对方扫码即可打开", font=self.font(11),
                     text_color=pal.text_dim).pack(pady=(0, self.p(12)))
        ctk.CTkLabel(win, text="", image=ctk.CTkImage(light_image=image, size=(260, 260)),
                     width=260, height=260).pack()
        self._qrimg = image
        link = ctk.CTkEntry(win, height=self.p(34), font=self.font(10.5),
                            fg_color=pal.card, border_color=pal.border,
                            text_color=pal.text)
        link.insert(0, url)
        link.configure(state="readonly") if False else None
        link.pack(fill="x", padx=self.p(24), pady=(self.p(14), self.p(8)))

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=(self.p(4), self.p(16)))

        def copy_img():
            ok = _copy_image_to_clipboard(image)
            self.toast("二维码图片已复制" if ok else "复制失败，试试保存图片", ok)

        def save_img():
            path = filedialog.asksaveasfilename(
                title="保存二维码", defaultextension=".png",
                initialfile="分享二维码.png",
                filetypes=[("PNG 图片", "*.png")])
            if path:
                try:
                    image.save(path)
                    self.toast("已保存")
                except Exception as exc:
                    messagebox.showerror("保存失败", str(exc))

        ctk.CTkButton(row, text="复制二维码", height=self.p(38), width=self.p(120),
                      corner_radius=self.p(10), font=self.font(12, True),
                      fg_color=pal.accent, hover_color=pal.accent_hover,
                      text_color="#ffffff", command=copy_img).pack(side="left",
                                                                  padx=self.p(4))
        ctk.CTkButton(row, text="复制链接", height=self.p(38), width=self.p(100),
                      corner_radius=self.p(10), font=self.font(12),
                      fg_color=pal.card_hover, hover_color=pal.border_hi,
                      text_color=pal.text,
                      command=lambda: self._copy(url)).pack(side="left", padx=self.p(4))
        ctk.CTkButton(row, text="保存图片", height=self.p(38), width=self.p(100),
                      corner_radius=self.p(10), font=self.font(12),
                      fg_color=pal.card_hover, hover_color=pal.border_hi,
                      text_color=pal.text,
                      command=save_img).pack(side="left", padx=self.p(4))

    # ---------------------------------------------------------------- 生命周期
    def _on_close(self) -> None:
        try:
            self.svc.stop()
        except Exception:
            pass
        try:
            self.cfg.save()
        except Exception:
            pass
        self.destroy()


def run(ctx) -> int:
    app = App(ctx)
    app.mainloop()
    return 0
