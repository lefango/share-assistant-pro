# -*- coding: utf-8 -*-
import os
import customtkinter as ctk


def choose_sources(parent, library, groups: list[str], default: str | None = None):
    """让用户勾选这次分享哪些分组/整个文件库。

    返回 [(显示名, 绝对路径)]；取消返回 None。
    """
    result: list[tuple[str, str]] | None = [None]
    win = ctk.CTkToplevel(parent)
    win.title("这次分享什么")

    w = int(parent.p(460))
    h = int(parent.p(560))
    parent.update_idletasks()
    x = parent.winfo_x() + max(0, (parent.winfo_width() - w) // 2)
    y = parent.winfo_y() + max(0, (parent.winfo_height() - h) // 2)
    # CTk 的 geometry() 会把宽高再乘一次 window scaling，这里先除掉，否则弹窗会大一倍
    try:
        scale = float(ctk.ScalingTracker.get_window_scaling(win)) or 1.0
    except Exception:
        scale = 1.0
    win.geometry(f"{max(1, round(w / scale))}x{max(1, round(h / scale))}+{x}+{y}")
    win.configure(fg_color=parent.pal.bg)
    win.transient(parent)
    win.grab_set()

    def _close():
        result[0] = None
        if win.winfo_exists():
            win.destroy()

    win.protocol("WM_DELETE_WINDOW", _close)

    pad = int(parent.p(16))
    half_pad = int(parent.p(8))
    radius = int(parent.p(8))

    top = ctk.CTkFrame(win, fg_color=parent.pal.bg, corner_radius=0)
    top.pack(side="top", fill="x", padx=pad, pady=(pad, half_pad))
    ctk.CTkLabel(
        top,
        text="这次分享哪些内容",
        font=parent.font(16, bold=True),
        text_color=parent.pal.text,
    ).pack(anchor="w")
    ctk.CTkLabel(
        top,
        text="只发给这次，下次重新选",
        font=parent.font(12),
        text_color=parent.pal.text_dim,
    ).pack(anchor="w", pady=(half_pad, 0))

    bottom = ctk.CTkFrame(win, fg_color=parent.pal.bg, corner_radius=0)
    bottom.pack(side="bottom", fill="x", padx=pad, pady=(half_pad, pad))

    scroll = ctk.CTkScrollableFrame(win, fg_color=parent.pal.bg, corner_radius=0, label_text="")
    scroll.pack(side="top", fill="both", expand=True, padx=pad, pady=(0, half_pad))

    whole_var = ctk.BooleanVar(value=False)
    group_vars = []
    group_boxes = []

    def _set_groups_enabled(enabled: bool):
        state = "normal" if enabled else "disabled"
        for box in group_boxes:
            box.configure(state=state)

    def _on_whole():
        if whole_var.get():
            for var in group_vars:
                var.set(False)
            _set_groups_enabled(False)
        else:
            _set_groups_enabled(True)

    checkbox_kwargs = {
        "font": parent.font(14),
        "text_color": (parent.pal.text, parent.pal.text_dim),
        "fg_color": parent.pal.card,
        "border_color": parent.pal.border,
        "hover_color": parent.pal.card_hover,
        "checkmark_color": parent.pal.accent,
        "corner_radius": radius,
    }

    ctk.CTkCheckBox(
        scroll,
        text="整个文件库",
        variable=whole_var,
        command=_on_whole,
        **checkbox_kwargs,
    ).pack(fill="x", pady=(0, half_pad), anchor="w")

    for i, name in enumerate(groups):
        var = ctk.BooleanVar(value=False)
        group_vars.append(var)

        def _make_command(index: int):
            def _handler():
                if group_vars[index].get() and whole_var.get():
                    whole_var.set(False)
                    _set_groups_enabled(True)
            return _handler

        box = ctk.CTkCheckBox(
            scroll,
            text=f"📁 {name}",
            variable=var,
            command=_make_command(i),
            **checkbox_kwargs,
        )
        box.pack(fill="x", pady=(0, half_pad), anchor="w")
        group_boxes.append(box)

    if groups:
        target = None
        if default is None or default == "":
            target = groups[0]
        elif default in groups:
            target = default
        if target is not None:
            group_vars[groups.index(target)].set(True)
    else:
        whole_var.set(True)

    def _cancel():
        result[0] = None
        if win.winfo_exists():
            win.destroy()

    def _start():
        if whole_var.get():
            result[0] = [("文件库", os.path.abspath(library.root))]
        else:
            selected = []
            for i, name in enumerate(groups):
                if group_vars[i].get():
                    selected.append((name, os.path.abspath(library.group_dir(name))))
            if not selected:
                return
            result[0] = selected
        if win.winfo_exists():
            win.destroy()

    ctk.CTkButton(
        bottom,
        text="取消",
        command=_cancel,
        font=parent.font(13),
        text_color=parent.pal.text,
        fg_color=parent.pal.card,
        hover_color=parent.pal.card_hover,
        corner_radius=radius,
    ).pack(side="left", padx=(0, half_pad))

    ctk.CTkButton(
        bottom,
        text="开始分享",
        command=_start,
        font=parent.font(13),
        text_color="white",
        fg_color=parent.pal.accent,
        hover_color=parent.pal.accent_hover,
        corner_radius=radius,
    ).pack(side="right")

    parent.wait_window(win)
    return result[0]
