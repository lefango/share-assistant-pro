# -*- coding: utf-8 -*-
"""玄天典籍界面 · 接入层（run(ctx)）。

view.py 只负责画；这里负责把界面和 ShareService / Config / Library 接起来。
后台线程绝不碰 Tk：所有状态都通过 ctx.events 队列回到主线程。
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from ... import paths
from ...library import Library, human_size, human_time
from ...service import ERROR, IDLE, RUNNING, STARTING, STOPPED
from ..dialog_sources import choose_sources
from .view import TTL_MAP, ShareView

STATE_MAP = {IDLE: "idle", STARTING: "starting", RUNNING: "running",
             ERROR: "error", STOPPED: "stopped"}

LIMIT_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}


def parse_limit(text: str) -> int:
    """『不限』『500MB』『2TB』→ 字节数；解析不了返回 -1。"""
    raw = (text or "").strip().replace(" ", "").upper()
    if raw in ("", "0", "不限", "不限量", "无"):
        return 0
    import re

    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)(TB|GB|MB|KB|B)?$", raw)
    if not match:
        return -1
    number = float(match.group(1))
    unit = match.group(2) or "MB"
    return int(number * LIMIT_UNITS[unit])


def limit_text(value: int) -> str:
    value = int(value or 0)
    if value <= 0:
        return "不限"
    for unit, size in (("TB", LIMIT_UNITS["TB"]), ("GB", LIMIT_UNITS["GB"]),
                       ("MB", LIMIT_UNITS["MB"])):
        if value >= size and value % size == 0:
            return f"{value // size}{unit}"
    return f"{value // LIMIT_UNITS['MB']}MB"


class App(ctk.CTk):
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.svc = ctx.service
        self.theme = ctx.theme
        super().__init__(fg_color=self.theme["colors"]["bg"])
        self.TkdndVersion = TkinterDnD.require(self)

        # choose_sources() 等公共控件按「default 界面」的约定取这两样东西
        from types import SimpleNamespace

        self.pal = SimpleNamespace(**self.theme.get("colors", {}))
        self.ui_scale = float(ctk.ScalingTracker.get_widget_scaling(self)) or 1.0

        self.title(f"{self.theme.get('title') or '分享助手'} · 分享助手 Pro")
        self._fit_to_screen()
        self.minsize(960, 620)
        self._sources: list[tuple[str, str]] | None = None
        self._busy = False
        self._last_state = IDLE
        self._closing = False

        self.view = ShareView(self, self.theme, self._callbacks())
        self.view.pack(fill="both", expand=True)

        # 窗口真正创建出来后缩放系数才是准的，再校一次（防止首帧用错尺寸）
        self.after(150, self._fit_to_screen)

        self._sync_all()
        self._reload()
        self.view.set_remaining(self.svc.remaining)
        self.after(150, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.cfg.get("auto_start"):
            self.after(700, lambda: self._start_share(pick=False))

    # ------------------------------------------------------------ 窗口尺寸
    # 设计尺寸（逻辑单位，跟 view.py 的 W_SIDEBAR=192 / W_RAIL=300 同一套坐标系）
    DESIGN_W, DESIGN_H = 1280, 820
    MIN_W, MIN_H = 960, 620

    def _work_area(self) -> tuple[int, int, int, int]:
        """屏幕可用区域（物理像素，已经扣掉任务栏）。"""
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                          ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _fit_to_screen(self, debug: bool = False) -> None:
        """把窗口摆成「设计尺寸 × 控件缩放」，并夹在屏幕可用区域内。

        坑在这里：CTk 的 geometry() 会把宽高**再乘一次** window scaling
        （x/y 则不乘）。所以这里要传「物理像素 ÷ window scaling」，
        否则 1280×820 会变成 5120×3280，被 Windows 夹小之后右栏就跑到屏幕外了。
        """
        scale = float(ctk.ScalingTracker.get_widget_scaling(self)) or 1.0
        win_scale = float(ctk.ScalingTracker.get_window_scaling(self)) or scale
        left, top, avail_w, avail_h = self._work_area()

        # 目标物理尺寸 = 设计逻辑尺寸 × 控件缩放，再夹到屏幕里
        phys_w = min(int(self.DESIGN_W * scale), max(1, avail_w - 48))
        phys_h = min(int(self.DESIGN_H * scale), max(1, avail_h - 48))

        width = max(1, round(phys_w / win_scale))
        height = max(1, round(phys_h / win_scale))
        x = left + max(0, (avail_w - phys_w) // 2)
        y = top + max(0, (avail_h - phys_h) // 2 - 24)

        self.minsize(min(self.MIN_W, width), min(self.MIN_H, height))
        self.geometry(f"{width}x{height}+{x}+{y}")

        if debug:
            def report() -> None:
                view = getattr(self, "view", None)
                if view is None:
                    return
                print(f"[layout] widget_scale={scale:.2f} window_scale={win_scale:.2f} "
                      f"target={phys_w}x{phys_h} "
                      f"window={self.winfo_width()}x{self.winfo_height()} "
                      f"sidebar={view._sidebar.winfo_width()} "
                      f"main={view._host.winfo_width()} "
                      f"rail={view._rail.winfo_width()} "
                      f"rail_x={view._rail.winfo_x()} "
                      f"rail_visible={bool(view._rail.winfo_ismapped())}")

            self.after(500, report)

    # ------------------------------------------------------------ 回调表
    def p(self, value: float) -> int:
        """逻辑尺寸 → 物理像素（公共弹窗按这个约定要 padding）。"""
        return int(round(value * self.ui_scale))

    def font(self, size: int, bold: bool = False):
        return self.view._font(size, bold)

    def _callbacks(self) -> dict:
        return {
            "share": self._toggle_share,
            "stop": lambda: self._stop_share(),
            "refresh": self._refresh_link,
            "pick_sources": self._pick_sources,
            "import_files": self._import_files,
            "drop": self._drop_paths,
            "open_library": self._open_library,
            "open_path": self._open_path,
            "delete_path": self._delete_path,
            "new_group": self._new_group,
            "switch_group": self._switch_group,
            "set_password": self._set_password,
            "set_ttl": self._set_ttl,
            "set_limit": self._set_limit,
            "set_receive": self._set_receive,
            "choose_dir": self._choose_receive_dir,
            "copy": self._copy,
            "qr": lambda url: self.view.show_qr(url),
            "save_settings": self._save_settings,
        }

    # ------------------------------------------------------------ 分享
    def _toggle_share(self) -> None:
        if self.svc.running:
            self._stop_share()
        else:
            self._start_share(pick=True)

    def _pick_sources(self) -> None:
        groups = self.ctx.library.groups()
        chosen = choose_sources(self, self.ctx.library, groups,
                                self.cfg.get("last_group") or None)
        if chosen:
            self._sources = chosen
            names = "、".join(name for name, _ in chosen[:3])
            self.view.toast(f"这次分享：{names}")

    def _current_sources(self) -> list[tuple[str, str]]:
        if self._sources:
            return self._sources
        group = self.cfg.get("last_group")
        if group and os.path.isdir(self.ctx.library.group_dir(group)):
            return [(group, self.ctx.library.group_dir(group))]
        root = self.ctx.library.root
        return [("文件库", root)]

    def _start_share(self, pick: bool = False) -> None:
        if self._busy or self.svc.running:
            return
        if pick and not self._sources:
            self._pick_sources()
            if not self._sources:
                return
        self._busy = True
        self.view.set_state("starting", "正在建立隧道…")
        sources = self._current_sources()
        cfg = self.cfg

        def work():
            ok = self.svc.start(
                sources, title=cfg.get("title"), password=cfg.get("password"),
                ttl_seconds=cfg.get("ttl"), allow_download=cfg.get("allow_download"),
                allow_upload=cfg.get("receive_open"), receive_dir=cfg.get("receive_dir"),
                receive_limit=cfg.get("receive_limit"))
            self.ctx.events.put(("ui", ("started", ok)))

        threading.Thread(target=work, daemon=True).start()

    def _stop_share(self) -> None:
        self._busy = True

        def work():
            self.svc.stop()
            self.ctx.events.put(("ui", ("stopped", True)))

        threading.Thread(target=work, daemon=True).start()

    def _refresh_link(self) -> None:
        if not self.svc.running:
            self.view.toast("先点「开始分享」", False)
            return
        self.view.toast("正在换新链接…")

        def work():
            ok = self.svc.refresh_link()
            self.ctx.events.put(("ui", ("refreshed", ok)))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 参数
    def _set_password(self, value: str) -> None:
        self.cfg.set("password", value)
        self.svc.apply(password=value)
        self.view.toast("密码已应用" if value else "已取消密码")

    def _set_ttl(self, seconds: int) -> None:
        self.cfg.set("ttl", int(seconds))
        self.svc.apply(ttl=int(seconds))
        self.view.set_remaining(self.svc.remaining)

    def _set_limit(self, text: str) -> None:
        size = parse_limit(text)
        if size < 0:
            self.view.toast("看不懂这个数量，写 500MB / 2GB / 不限", False)
            return
        self.cfg.set("receive_limit", size)
        self.view.set_quota(f"本次上限 {limit_text(size)}")
        self.view.toast("接收上限已保存，下次开分享生效")

    def _set_receive(self, opened: bool) -> None:
        self.cfg.set("receive_open", bool(opened))
        self.svc.set_receive_open(bool(opened))
        self.view.set_receive_open(bool(opened))

    def _choose_receive_dir(self) -> None:
        folder = filedialog.askdirectory(title="收到的文件放到哪",
                                         initialdir=self.cfg.get("receive_dir"))
        if not folder:
            return
        self.cfg.set("receive_dir", folder)
        os.makedirs(folder, exist_ok=True)
        self.svc.apply(receive_dir=folder)
        try:
            self.view._recv_dir_var.set(folder)
            self.view._rec_dir_var.set(folder)
        except Exception:
            pass
        self._refresh_received()
        self.view.toast("接收目录已更新")

    # ------------------------------------------------------------ 文件
    def _open_path(self, path: str) -> None:
        """打开文件/文件夹；传空就打开当前分组目录。"""
        target = path or self._current_dir()
        try:
            os.startfile(target)
        except Exception as exc:
            self.view.toast(f"打不开：{exc}", False)

    def _open_library(self) -> None:
        self._open_path(self._current_dir())

    def _import_files(self) -> None:
        files = filedialog.askopenfilenames(title="选择要放进文件库的文件", parent=self)
        if files:
            self._drop_paths(list(files))

    def _drop_paths(self, paths) -> None:
        """把拖进来 / 选进来的文件复制进当前分组（没有分组就先建一个）。"""
        paths = [p for p in (paths or []) if p]
        if not paths:
            return
        group = self.cfg.get("last_group")
        if not group or not os.path.isdir(self.ctx.library.group_dir(group)):
            self._new_group()
            group = self.cfg.get("last_group")
            if not group:
                return
        dest = self.ctx.library.group_dir(group)
        library = self.ctx.library

        def work():
            result = library.place(paths, dest, mode="copy")
            self.ctx.events.put(("call", lambda: self._after_place(result)))

        threading.Thread(target=work, daemon=True).start()

    def _after_place(self, result) -> None:
        self._reload()
        if result.failed:
            names = "；".join(f"{os.path.basename(src)}：{why}"
                             for src, why in result.failed[:3])
            self.view.toast(f"{len(result.failed)} 个没导入：{names}", False)
        else:
            self.view.toast(f"已导入 {result.ok_count} 个")

    def _delete_path(self, path: str) -> None:
        name = os.path.basename(path.rstrip("\\/"))
        if not messagebox.askyesno("删除", f"确定删除「{name}」吗？", parent=self):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except Exception as exc:
            self.view.toast(f"删除失败：{exc}", False)
        self._reload()

    def _new_group(self) -> None:
        dialog = ctk.CTkInputDialog(text="给新分组起个名字：", title="新建分组")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.ctx.library.create_group(name)
        except Exception as exc:
            messagebox.showerror("建不了这个分组", str(exc), parent=self)
            return
        self.cfg.set("last_group", name.strip())
        self._reload()

    def _switch_group(self, name: str) -> None:
        self.cfg.set("last_group", name)
        self._sources = None
        self._reload()

    def _current_dir(self) -> str:
        group = self.cfg.get("last_group")
        if group and os.path.isdir(self.ctx.library.group_dir(group)):
            return self.ctx.library.group_dir(group)
        return self.ctx.library.root

    def _reload(self) -> None:
        library = self.ctx.library
        groups = library.groups()
        current = self.cfg.get("last_group")
        if groups and current not in groups:
            current = groups[0]
            self.cfg.set("last_group", current)
        folder = self._current_dir()
        items = []
        try:
            entries = sorted(os.scandir(folder),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            entries = []
        for entry in entries[:500]:
            if entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            is_dir = entry.is_dir()
            items.append({
                "name": entry.name,
                "path": entry.path,
                "size_text": "文件夹" if is_dir else human_size(stat.st_size),
                "time_text": human_time(stat.st_mtime),
                "is_dir": is_dir,
            })
        self.view.set_groups(groups, current)
        self.view.set_files(items)
        try:
            self.view._file_path_lbl.configure(text=folder)
            self.view._lib_dir_var.set(library.root)
            self.view._rec_dir_var.set(self.cfg.get("receive_dir"))
        except Exception:
            pass
        self._refresh_received()

    def _refresh_received(self) -> None:
        files = self.svc.received_files() if self.svc.running else []
        if not files:
            folder = self.cfg.get("receive_dir")
            try:
                files = [
                    {"name": e.name, "path": e.path,
                     "size_text": human_size(e.stat().st_size),
                     "time_text": human_time(e.stat().st_mtime)}
                    for e in os.scandir(folder) if e.is_file()
                ][:100]
            except OSError:
                files = []
        self.view.set_received(files)

    # ------------------------------------------------------------ 杂项
    def _copy(self, text: str) -> None:
        if not text:
            self.view.toast("还没有链接", False)
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.view.toast("已复制到剪贴板")

    def _save_settings(self) -> None:
        view = self.view
        old_lib = self.cfg.get("library_dir")
        ttl = TTL_MAP.get(view._def_ttl_var.get(), self.cfg.get("ttl"))
        self.cfg.update({
            "library_dir": view._lib_dir_var.get().strip() or old_lib,
            "receive_dir": view._rec_dir_var.get().strip() or self.cfg.get("receive_dir"),
            "title": view._web_title_var.get().strip() or "我的分享",
            "password": view._def_pw_var.get(),
            "ttl": ttl,
            "auto_start": bool(view._auto_start_var.get()),
        })
        os.makedirs(self.cfg.get("library_dir"), exist_ok=True)
        os.makedirs(self.cfg.get("receive_dir"), exist_ok=True)
        self.ctx.library = Library(self.cfg.get("library_dir"))
        if self.cfg.get("library_dir") != old_lib:
            self.cfg.set("last_group", "")
        self.svc.apply(password=self.cfg.get("password"), ttl=ttl,
                       receive_dir=self.cfg.get("receive_dir"))
        self._reload()
        self.view.toast("设置已保存")

    # ------------------------------------------------------------ 状态
    def _sync_all(self) -> None:
        state = STATE_MAP.get(self.svc.state if self.svc.running else self._last_state, "idle")
        self.view.set_state(state, self.svc.message)
        self.view.set_links(self.svc.share_url, self.svc.receive_url)
        self.view.set_remaining(self.svc.remaining)
        self.view.set_receive_open(self.cfg.get("receive_open"))
        self.view.set_quota(self._quota_text())
        try:
            self.view._limit_var.set(limit_text(self.cfg.get("receive_limit")))
        except Exception:
            pass

    def _quota_text(self) -> str:
        if self.svc.running and self.svc.server and self.svc.server.upload_api:
            info = self.svc.server.upload_api.status()
            quota = info.get("quota") or {}
            if quota.get("limit"):
                used = quota.get("used", 0)
                return f"已接收 {used / 1024 ** 2:.0f}MB / 上限 {quota['limit'] / 1024 ** 2:.0f}MB"
            return "不限量"
        return f"本次上限 {limit_text(self.cfg.get('receive_limit'))}"

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.ctx.events.get_nowait()
                if kind == "state":
                    state, message = payload
                    self._last_state = state
                    self.view.set_state(STATE_MAP.get(state, "idle"), message)
                    if state == ERROR and message:
                        self.view.toast(message, False)
                elif kind == "url":
                    self.view.set_links(self.svc.share_url, self.svc.receive_url)
                elif kind == "call":
                    try:
                        payload()
                    except Exception as exc:
                        self.view.toast(f"操作出错：{exc}", False)
                elif kind == "ui":
                    action, ok = payload
                    self._busy = False
                    if action == "started":
                        if ok:
                            self.view.set_state("running", self.svc.message)
                            self._busy = False
                        else:
                            self.view.set_state("error", self.svc.message or "开启失败")
                    elif action == "stopped":
                        self.view.set_state("stopped", "已停止")
                    elif action == "refreshed":
                        self.view.toast("链接已更新" if ok else "换链接失败", bool(ok))
        except queue.Empty:
            pass

        if not self._closing:
            self.view.set_remaining(self.svc.remaining)
            self.after(600, self._pump)

    def _on_close(self) -> None:
        self._closing = True
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
