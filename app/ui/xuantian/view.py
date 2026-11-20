# -*- coding: utf-8 -*-
"""
玄天典籍 · 界面模块
气质：古籍藏阁深处翻开一本法器图鉴，纸已泛暗金，墨迹是深青。
布局：左侧导航栏 | 中部三页切换 | 右侧常驻分享栏
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 全局常量 —— 所有视觉参数集中在这里，方便调整
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 字号（int，CTkFont 要求）
FS_TITLE   = 16   # 页标题
FS_SECTION = 14   # 分区标题
FS_BODY    = 12   # 正文
FS_SMALL   = 11   # 注释 / 辅助
FS_MICRO   = 10   # 极小（版权、路径等）

# 间距
PAD_OUTER  = 18   # 外边距
PAD_INNER  = 14   # 卡片内边距
PAD_ROW    = 6    # 行间距
PAD_BTN    = 8    # 按钮横向间距

# 形状
R_CAPSULE  = 20   # 胶囊按钮圆角
R_CARD     = 4    # 卡片直角（4px 保留一点收口感）
R_CHIP     = 16   # 分组 chip 胶囊

# 侧栏 / 右栏宽度
W_SIDEBAR  = 192
W_RAIL     = 300

# 卡片左侧书签竖条
BOOKMARK_W = 3

# 玄天典籍配色（以下为默认值，实际运行从 theme["colors"] 读取）
_FALLBACK = {
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
}

# 有效期选项（秒，0 = 不限时）
TTL_OPTIONS = [
    ("不限时",      0),
    ("1 小时",    3600),
    ("6 小时",   21600),
    ("12 小时",  43200),
    ("1 天",     86400),
    ("3 天",    259200),
    ("7 天",    604800),
]
TTL_LABELS = [label for label, _ in TTL_OPTIONS]
TTL_MAP    = dict(TTL_OPTIONS)

# 导航项
NAV_ITEMS = [
    ("files",    "▣  文件库"),
    ("receive",  "⇅  接收区"),
    ("settings", "⊡  设置"),
]

# 文件类型图符（汉字/几何，不用 emoji）
FILE_ICONS = {
    "图片": "◈", "视频": "▷", "音频": "♩",
    "文档": "◫", "压缩包": "◉", "安装包": "◈",
    "其他": "◆", "文件夹": "▤",
}

# 状态显示文本（内部值不给用户看）
STATE_LABEL = {
    "idle":     "待机",
    "starting": "正在连接…",
    "running":  "分享中",
    "error":    "发生错误",
    "stopped":  "已停止",
}
# 状态对应颜色 key
STATE_COLOR = {
    "idle":     "text_dim",
    "starting": "warn",
    "running":  "ok",
    "error":    "danger",
    "stopped":  "text_dim",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _c(theme: dict, key: str) -> str:
    """从 theme["colors"] 安全取色，兜底用内置配色。"""
    return theme.get("colors", {}).get(key, _FALLBACK.get(key, "#ffffff"))


def _ttl_label(seconds: int) -> str:
    for label, val in TTL_OPTIONS:
        if val == seconds:
            return label
    return TTL_LABELS[0]


def _fmt_remain(seconds: int) -> str:
    if seconds < 0:
        return "不限时"
    if seconds == 0:
        return "已到期"
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h} 时 {m:02d} 分"
    if m:
        return f"{m} 分 {s:02d} 秒"
    return f"{s} 秒"


def _short_name(name: str, limit: int = 38) -> str:
    """长文件名中间截断，免得把「打开/删除」挤出可视区。"""
    if len(name) <= limit:
        return name
    head = max(8, limit - 13)
    return name[:head] + "…" + name[-8:]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主视图类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ShareView(ctk.CTkFrame):
    """
    玄天典籍界面主体。

    参数
    ----
    master : Tk / CTk 窗口
    theme  : dict，来自 app.skin.load()，包含 colors / font / radius 等
    on     : dict，回调字典，键见接口契约
    """

    def __init__(self, master, theme: dict, on: dict):
        self._t  = theme
        self._on = on

        bg = _c(theme, "bg")
        super().__init__(master, fg_color=bg, corner_radius=0)

        self._state   = "idle"
        self._message = ""
        self._remain  = -1
        self._groups: list[str]  = []
        self._cur_grp: str       = ""
        self._share_url   = ""
        self._receive_url = ""
        self._is_running  = False
        self._toast_job   = None
        self._toast_lbl   = None

        # 设置页变量（需要在 _build_settings 前初始化）
        self._lib_dir_var    = tk.StringVar()
        self._rec_dir_var    = tk.StringVar()
        self._web_title_var  = tk.StringVar()
        self._def_pw_var     = tk.StringVar()
        self._def_ttl_var    = tk.StringVar(value=TTL_LABELS[0])
        self._auto_start_var = tk.BooleanVar(value=False)
        self._skin_var       = tk.StringVar(value="默认深色")

        self._build()

    # ──────────────────────────────────────────────────
    # 内部：颜色 / 字体快捷方式
    # ──────────────────────────────────────────────────

    def _c(self, key: str) -> str:
        return _c(self._t, key)

    def _font(self, size: int, bold: bool = False) -> ctk.CTkFont:
        family = self._t.get("font", "Microsoft YaHei UI")
        return ctk.CTkFont(family=family, size=int(size),
                           weight="bold" if bold else "normal")

    def _check_scrollbar(self, scroll) -> None:
        """内容没超出可视区就把滚动条藏起来（CTk 默认永远挂一条灰条，很难看）。

        注意：CTkScrollbar 的 grid_remove() 之后 winfo_ismapped() 仍然是 1
        （CTk 内部把它当 canvas window 挂着），所以真正的“隐身”靠把滑块涂成背景色。
        """
        try:
            canvas = scroll._parent_canvas
            bar = scroll._scrollbar
            if getattr(scroll, "_orientation", "vertical") == "horizontal":
                need = scroll.winfo_reqwidth() > canvas.winfo_width()
            else:
                need = scroll.winfo_reqheight() > canvas.winfo_height()
            if need:
                bar.grid()
                bar.configure(button_color=self._c("border"),
                              button_hover_color=self._c("accent"))
            else:
                bar.grid_remove()
                bar._last_geometry_manager_call = None
                bar.configure(button_color=self._c("bg"),
                              button_hover_color=self._c("border"))
        except Exception:
            pass

    def _auto_scrollbar(self, scroll) -> None:
        """内容没超出可视区就把滚动条藏起来（CTk 默认永远挂一条灰条，很难看）。"""
        try:
            if not getattr(scroll, "_auto_bar_bound", False):
                scroll._parent_canvas.bind(
                    "<Configure>", lambda e, s=scroll: self._check_scrollbar(s))
                scroll._auto_bar_bound = True
        except Exception:
            pass
        self.after_idle(lambda s=scroll: self._check_scrollbar(s))
        self.after(250, lambda s=scroll: self._check_scrollbar(s))

    # ──────────────────────────────────────────────────
    # 内部：通用控件工厂
    # ──────────────────────────────────────────────────

    def _card(self, parent, **kw) -> ctk.CTkFrame:
        """带左侧书签竖条的卡片。"""
        outer = ctk.CTkFrame(
            parent,
            fg_color=self._c("card"),
            corner_radius=R_CARD,
            border_width=1,
            border_color=self._c("border"),
            **kw
        )
        return outer

    def _capsule_btn(self, parent, text: str, command,
                     kind: str = "ghost", width: int = 88,
                     height: int = 32) -> ctk.CTkButton:
        """
        kind: "ghost" | "accent" | "accent2" | "danger"
        """
        c = self._c
        styles = {
            "ghost":   dict(fg_color=c("card_hover"), hover_color=c("border_hi"),
                            text_color=c("text"), border_width=0),
            "accent":  dict(fg_color=c("accent"), hover_color=c("accent_hover"),
                            text_color="#0d1119", border_width=0),
            "accent2": dict(fg_color="transparent", hover_color=c("card_hover"),
                            text_color=c("accent2"), border_width=1,
                            border_color=c("accent2")),
            "danger":  dict(fg_color="transparent", hover_color=c("card_hover"),
                            text_color=c("danger"), border_width=1,
                            border_color=c("border")),
        }
        s = styles.get(kind, styles["ghost"])
        return ctk.CTkButton(
            parent, text=text, command=command,
            width=width, height=height,
            corner_radius=R_CAPSULE,
            font=self._font(FS_SMALL),
            **s
        )

    def _entry(self, parent, textvariable=None,
               placeholder: str = "", readonly: bool = False) -> ctk.CTkEntry:
        c = self._c
        e = ctk.CTkEntry(
            parent,
            textvariable=textvariable,
            placeholder_text=placeholder,
            height=34,
            corner_radius=R_CAPSULE,
            font=self._font(FS_BODY),
            fg_color=c("bg"),
            border_color=c("border"),
            border_width=1,
            text_color=c("text"),
            placeholder_text_color=c("text_dim"),
        )
        if readonly:
            e.bind("<Key>", lambda ev: "break")
        return e

    def _section_header(self, parent, title: str,
                        subtitle: str = "") -> ctk.CTkFrame:
        """章节标题行（带书签竖条）。"""
        c = self._c
        row = ctk.CTkFrame(parent, fg_color="transparent")
        # 竖条
        ctk.CTkFrame(
            row,
            width=BOOKMARK_W,
            height=18,
            fg_color=c("accent"),
            corner_radius=1
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            row, text=title,
            font=self._font(FS_SECTION, bold=True),
            text_color=c("text")
        ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                row, text=subtitle,
                font=self._font(FS_MICRO),
                text_color=c("text_dim")
            ).pack(side="left", padx=(8, 0))
        return row

    # ──────────────────────────────────────────────────
    # 骨架布局
    # ──────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # 侧栏
        self.grid_columnconfigure(1, weight=1)   # 主体
        self.grid_columnconfigure(2, weight=0)   # 右栏

        self._build_sidebar()
        self._build_main()
        self._build_rail()

        self.show_page("files")

    # ──────────────────────────────────────────────────
    # 左侧导航栏
    # ──────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        c = self._c
        sb = ctk.CTkFrame(
            self,
            width=W_SIDEBAR,
            corner_radius=0,
            fg_color=c("panel"),
        )
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(2, weight=1)
        sb.grid_columnconfigure(0, weight=1)
        self._sidebar = sb

        # ── 品牌区
        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew",
                   padx=PAD_OUTER, pady=(PAD_OUTER + 4, PAD_INNER))

        # 金色符文圆框
        logo = ctk.CTkFrame(
            brand,
            width=38, height=38,
            corner_radius=R_CARD,
            fg_color=c("card"),
            border_width=1,
            border_color=c("accent"),
        )
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(
            logo, text="典",
            font=self._font(18, bold=True),
            text_color=c("accent"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        info = ctk.CTkFrame(brand, fg_color="transparent")
        info.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(
            info, text="分享助手",
            font=self._font(FS_SECTION, bold=True),
            text_color=c("text"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            info, text="玄天典籍",
            font=self._font(FS_MICRO),
            text_color=c("accent2"),
        ).pack(anchor="w")

        # 分割线
        ctk.CTkFrame(
            sb, height=1, fg_color=c("border"), corner_radius=0
        ).grid(row=0, column=0, sticky="ew",
               padx=PAD_INNER, pady=(72, 0))

        # ── 导航按钮
        nav = ctk.CTkFrame(sb, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew",
                 padx=PAD_INNER // 2, pady=(PAD_INNER, 0))

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for key, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                nav,
                text=label,
                anchor="w",
                height=38,
                corner_radius=R_CARD,
                font=self._font(FS_BODY),
                fg_color="transparent",
                hover_color=c("card"),
                text_color=c("text_dim"),
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", pady=2)
            self._nav_btns[key] = btn

        # ── 底部状态指示
        foot = ctk.CTkFrame(sb, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew",
                  padx=PAD_OUTER, pady=PAD_INNER)

        dot_row = ctk.CTkFrame(foot, fg_color="transparent")
        dot_row.pack(anchor="w")
        self._side_dot = ctk.CTkLabel(
            dot_row, text="◉",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
        )
        self._side_dot.pack(side="left")
        self._side_state = ctk.CTkLabel(
            dot_row, text="待机",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
        )
        self._side_state.pack(side="left", padx=(4, 0))

        self._side_link = ctk.CTkLabel(
            foot, text="",
            font=self._font(FS_MICRO),
            text_color=c("accent2"),
            wraplength=W_SIDEBAR - PAD_OUTER * 2,
            justify="left",
        )
        self._side_link.pack(anchor="w", pady=(4, 0))

    # ──────────────────────────────────────────────────
    # 主体（页面容器）
    # ──────────────────────────────────────────────────

    def _build_main(self) -> None:
        c = self._c
        host = ctk.CTkFrame(self, fg_color=c("bg"), corner_radius=0)
        host.grid(row=0, column=1, sticky="nsew")
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self._host = host

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._pages["files"]    = self._build_files_page(host)
        self._pages["receive"]  = self._build_receive_page(host)
        self._pages["settings"] = self._build_settings_page(host)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew",
                      padx=(PAD_OUTER, PAD_INNER),
                      pady=PAD_OUTER)

    # ──────────────────────────────────────────────────
    # 文件库页
    # ──────────────────────────────────────────────────

    def _build_files_page(self, host) -> ctk.CTkFrame:
        c = self._c
        page = ctk.CTkFrame(host, fg_color=c("bg"), corner_radius=0)
        page.grid_rowconfigure(3, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # 页头
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, PAD_INNER))

        ctk.CTkLabel(
            head, text="文件库",
            font=self._font(FS_TITLE, bold=True),
            text_color=c("text"),
        ).pack(side="left")

        self._file_path_lbl = ctk.CTkLabel(
            head, text="",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
        )
        self._file_path_lbl.pack(side="left", padx=(10, 0))

        self._capsule_btn(
            head, "打开文件夹",
            lambda: self._fire("open_library"),
            "ghost", width=88
        ).pack(side="right")

        # 分组 chip 行
        chip_row = ctk.CTkScrollableFrame(
            page,
            height=46,
            fg_color="transparent",
            orientation="horizontal",
            scrollbar_button_color=c("border"),
            scrollbar_button_hover_color=c("accent"),
        )
        chip_row.grid(row=1, column=0, sticky="ew",
                      pady=(0, PAD_ROW))
        self._chip_row = chip_row

        # 操作栏
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, PAD_ROW))

        self._capsule_btn(
            bar, "导入文件",
            lambda: self._fire("import_files"),
            "accent", width=84
        ).pack(side="left")
        self._capsule_btn(
            bar, "新建分组",
            lambda: self._fire("new_group"),
            "ghost", width=84
        ).pack(side="left", padx=(PAD_BTN, 0))

        self._file_count_lbl = ctk.CTkLabel(
            bar, text="",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        )
        self._file_count_lbl.pack(side="right")

        # 文件列表（可滚动）
        file_scroll = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            scrollbar_button_color=c("border"),
            scrollbar_button_hover_color=c("accent"),
        )
        file_scroll.grid(row=3, column=0, sticky="nsew")
        file_scroll.grid_columnconfigure(0, weight=1)
        self._file_scroll = file_scroll

        # 拖拽落点高亮框（overlay）
        self._drop_overlay = ctk.CTkLabel(
            file_scroll,
            text="拖拽文件到此处",
            font=self._font(FS_SECTION, bold=True),
            text_color=c("accent"),
            fg_color=c("card"),
            corner_radius=R_CARD,
            width=200, height=60,
        )

        # 注册拖拽
        try:
            from tkinterdnd2 import DND_FILES
            file_scroll.drop_target_register(DND_FILES)
            file_scroll.dnd_bind("<<Drop>>", self._on_drop)
            file_scroll.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            file_scroll.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except Exception:
            pass

        # 空状态卡片：浮在文件区正中（放进滚动区里会被内容高度顶到顶部）
        empty = ctk.CTkFrame(page, fg_color=c("card"), corner_radius=R_CARD,
                             border_width=1, border_color=c("border"))
        box = ctk.CTkFrame(empty, fg_color="transparent")
        box.pack(padx=40, pady=28)
        ctk.CTkLabel(box, text="▤", font=self._font(26),
                     text_color=c("border_hi")).pack()
        ctk.CTkLabel(box, text="这里还是空的",
                     font=self._font(FS_SECTION, bold=True),
                     text_color=c("text")).pack(pady=(6, 2))
        ctk.CTkLabel(box, text="把文件拖进窗口，或点上面的「导入文件」",
                     font=self._font(FS_SMALL),
                     text_color=c("text_dim")).pack()
        self._empty_card = empty
        try:
            from tkinterdnd2 import DND_FILES
            empty.drop_target_register(DND_FILES)
            empty.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

        return page

    def _on_drop(self, event) -> None:
        self._drop_overlay.place_forget()
        raw = event.data or ""
        # tkinterdnd2: 多路径用空格分隔，大括号包裹含空格的路径
        import re
        paths = re.findall(r'\{([^}]+)\}|(\S+)', raw)
        result = [a or b for a, b in paths]
        self._fire("drop", [p for p in result if p])

    def _on_drag_enter(self, event) -> None:
        self._drop_overlay.place(relx=0.5, rely=0.5, anchor="center")

    def _on_drag_leave(self, event) -> None:
        self._drop_overlay.place_forget()

    # ──────────────────────────────────────────────────
    # 接收区页
    # ──────────────────────────────────────────────────

    def _build_receive_page(self, host) -> ctk.CTkFrame:
        c = self._c
        page = ctk.CTkFrame(host, fg_color=c("bg"), corner_radius=0)
        page.grid_rowconfigure(4, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # 页头
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, PAD_INNER))
        ctk.CTkLabel(
            head, text="接收区",
            font=self._font(FS_TITLE, bold=True),
            text_color=c("text"),
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text="对方打开接收链接即可把文件传回来",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        ).pack(side="left", padx=(10, 0))

        # ── 卡片1：接收开关
        card1 = self._card(page)
        card1.grid(row=1, column=0, sticky="ew",
                   pady=(0, PAD_ROW * 2))
        inner1 = ctk.CTkFrame(card1, fg_color="transparent")
        inner1.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)

        self._section_header(inner1, "接收开关",
                             "关闭后对方无法访问接收页").pack(anchor="w", pady=(0, 8))

        sw_row = ctk.CTkFrame(inner1, fg_color="transparent")
        sw_row.pack(fill="x")

        self._recv_switch = ctk.CTkSwitch(
            sw_row,
            text="允许别人往我这里传文件",
            font=self._font(FS_BODY),
            text_color=c("text"),
            progress_color=c("accent"),
            button_color=c("accent_hover"),
            button_hover_color=c("accent"),
            command=lambda: self._fire("set_receive",
                                       bool(self._recv_switch.get())),
        )
        self._recv_switch.pack(side="left")

        self._recv_state_lbl = ctk.CTkLabel(
            inner1, text="",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        )
        self._recv_state_lbl.pack(anchor="w", pady=(6, 0))

        # 接收上限
        limit_row = ctk.CTkFrame(inner1, fg_color="transparent")
        limit_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(
            limit_row, text="本次最多接收",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
            width=90, anchor="w",
        ).pack(side="left")
        self._limit_var = tk.StringVar(value="不限")
        limit_e = self._entry(limit_row, self._limit_var, "如 500MB / 2GB / 不限")
        limit_e.pack(side="left", fill="x", expand=True)
        limit_e.bind("<Return>", lambda e: self._apply_limit())
        self._capsule_btn(
            limit_row, "保存",
            self._apply_limit,
            "ghost", width=56
        ).pack(side="left", padx=(PAD_BTN, 0))

        # ── 卡片2：接收链接
        card2 = self._card(page)
        card2.grid(row=2, column=0, sticky="ew",
                   pady=(0, PAD_ROW * 2))
        inner2 = ctk.CTkFrame(card2, fg_color="transparent")
        inner2.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)

        self._section_header(inner2, "接收链接",
                             "对方用这个，不是上面的分享链接").pack(anchor="w", pady=(0, 8))
        link_row = ctk.CTkFrame(inner2, fg_color="transparent")
        link_row.pack(fill="x")
        self._recv_url_var = tk.StringVar(value="")
        self._entry(link_row, self._recv_url_var, readonly=True).pack(
            side="left", fill="x", expand=True)
        self._capsule_btn(
            link_row, "复制",
            lambda: self._fire("copy", self._recv_url_var.get()),
            "ghost", width=56
        ).pack(side="left", padx=(PAD_BTN, 0))
        self._capsule_btn(
            link_row, "二维码",
            lambda: self._fire("qr", self._recv_url_var.get()),
            "accent2", width=64
        ).pack(side="left", padx=(PAD_BTN, 0))
        self._capsule_btn(
            link_row, "换链接",
            lambda: self._fire("refresh"),
            "ghost", width=64
        ).pack(side="left", padx=(PAD_BTN, 0))

        # ── 卡片3：接收目录
        card3 = self._card(page)
        card3.grid(row=3, column=0, sticky="ew",
                   pady=(0, PAD_ROW * 2))
        inner3 = ctk.CTkFrame(card3, fg_color="transparent")
        inner3.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)

        self._section_header(inner3, "文件存放目录").pack(anchor="w", pady=(0, 8))
        dir_row = ctk.CTkFrame(inner3, fg_color="transparent")
        dir_row.pack(fill="x")
        self._recv_dir_var = tk.StringVar(value="")
        self._entry(dir_row, self._recv_dir_var, readonly=True).pack(
            side="left", fill="x", expand=True)
        self._capsule_btn(
            dir_row, "选择",
            lambda: self._fire("choose_dir"),
            "ghost", width=56
        ).pack(side="left", padx=(PAD_BTN, 0))
        self._capsule_btn(
            dir_row, "打开",
            lambda: self._fire("open_path", self._recv_dir_var.get()),
            "ghost", width=56
        ).pack(side="left", padx=(PAD_BTN, 0))

        # ── 卡片4：已收文件列表（可扩展）
        card4 = self._card(page)
        card4.grid(row=4, column=0, sticky="nsew")
        card4.grid_rowconfigure(1, weight=1)
        card4.grid_columnconfigure(0, weight=1)

        head4 = ctk.CTkFrame(card4, fg_color="transparent")
        head4.grid(row=0, column=0, sticky="ew",
                   padx=PAD_INNER, pady=(PAD_INNER, 0))
        self._section_header(head4, "最近收到的文件").pack(side="left", anchor="w")

        self._recv_quota_lbl = ctk.CTkLabel(
            head4, text="",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        )
        self._recv_quota_lbl.pack(side="right")

        recv_scroll = ctk.CTkScrollableFrame(
            card4, fg_color="transparent",
            scrollbar_button_color=c("border"),
            scrollbar_button_hover_color=c("accent"),
        )
        recv_scroll.grid(row=1, column=0, sticky="nsew",
                         padx=PAD_ROW, pady=(PAD_ROW, PAD_INNER))
        recv_scroll.grid_columnconfigure(0, weight=1)
        self._recv_scroll = recv_scroll

        return page

    def _apply_limit(self) -> None:
        self._fire("set_limit", self._limit_var.get())

    # ──────────────────────────────────────────────────
    # 设置页
    # ──────────────────────────────────────────────────

    def _build_settings_page(self, host) -> ctk.CTkFrame:
        c = self._c
        page = ctk.CTkScrollableFrame(
            host, fg_color=c("bg"), corner_radius=0,
            scrollbar_button_color=c("border"),
            scrollbar_button_hover_color=c("accent"),
        )

        ctk.CTkLabel(
            page, text="设置",
            font=self._font(FS_TITLE, bold=True),
            text_color=c("text"),
            anchor="w",
        ).pack(fill="x", pady=(0, PAD_INNER))

        # ── 卡片：目录
        c1 = self._card(page)
        c1.pack(fill="x", pady=(0, PAD_ROW * 2))
        inner1 = ctk.CTkFrame(c1, fg_color="transparent")
        inner1.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)
        self._section_header(inner1, "目录设置").pack(anchor="w", pady=(0, 10))

        self._settings_dir_row(inner1, "文件库目录", self._lib_dir_var)
        self._settings_dir_row(inner1, "接收目录　", self._rec_dir_var)

        # ── 卡片：分享默认值
        c2 = self._card(page)
        c2.pack(fill="x", pady=(0, PAD_ROW * 2))
        inner2 = ctk.CTkFrame(c2, fg_color="transparent")
        inner2.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)
        self._section_header(inner2, "分享默认值").pack(anchor="w", pady=(0, 10))

        for label, var, placeholder in [
            ("网页标题", self._web_title_var, "留空用默认"),
            ("默认密码", self._def_pw_var,   "留空则不需要密码"),
        ]:
            row = ctk.CTkFrame(inner2, fg_color="transparent")
            row.pack(fill="x", pady=PAD_ROW // 2)
            ctk.CTkLabel(
                row, text=label,
                font=self._font(FS_BODY),
                text_color=c("text_dim"),
                width=72, anchor="w",
            ).pack(side="left")
            self._entry(row, var, placeholder).pack(
                side="left", fill="x", expand=True)

        # 有效期下拉
        ttl_row = ctk.CTkFrame(inner2, fg_color="transparent")
        ttl_row.pack(fill="x", pady=PAD_ROW // 2)
        ctk.CTkLabel(
            ttl_row, text="默认有效期",
            font=self._font(FS_BODY),
            text_color=c("text_dim"),
            width=72, anchor="w",
        ).pack(side="left")
        ctk.CTkOptionMenu(
            ttl_row,
            values=TTL_LABELS,
            variable=self._def_ttl_var,
            width=140, height=32,
            corner_radius=R_CAPSULE,
            font=self._font(FS_BODY),
            fg_color=c("card_hover"),
            button_color=c("border_hi"),
            button_hover_color=c("accent"),
            dropdown_fg_color=c("panel"),
            dropdown_hover_color=c("card_hover"),
            text_color=c("text"),
            dropdown_text_color=c("text"),
        ).pack(side="left")

        # 自动分享开关
        auto_row = ctk.CTkFrame(inner2, fg_color="transparent")
        auto_row.pack(fill="x", pady=(PAD_ROW, 0))
        ctk.CTkSwitch(
            auto_row,
            text="启动时自动开始分享（每次生成新链接）",
            variable=self._auto_start_var,
            font=self._font(FS_BODY),
            text_color=c("text"),
            progress_color=c("accent"),
            button_color=c("accent_hover"),
            button_hover_color=c("accent"),
        ).pack(anchor="w")

        # ── 卡片：外观
        c3 = self._card(page)
        c3.pack(fill="x", pady=(0, PAD_ROW * 2))
        inner3 = ctk.CTkFrame(c3, fg_color="transparent")
        inner3.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)
        self._section_header(inner3, "外观 / 界面",
                             "换皮肤后需要重启生效").pack(anchor="w", pady=(0, 10))

        skin_row = ctk.CTkFrame(inner3, fg_color="transparent")
        skin_row.pack(fill="x")
        ctk.CTkLabel(
            skin_row, text="皮肤",
            font=self._font(FS_BODY),
            text_color=c("text_dim"),
            width=72, anchor="w",
        ).pack(side="left")
        ctk.CTkOptionMenu(
            skin_row,
            values=["默认深色", "玄天典籍"],
            variable=self._skin_var,
            width=140, height=32,
            corner_radius=R_CAPSULE,
            font=self._font(FS_BODY),
            fg_color=c("card_hover"),
            button_color=c("border_hi"),
            button_hover_color=c("accent"),
            dropdown_fg_color=c("panel"),
            dropdown_hover_color=c("card_hover"),
            text_color=c("text"),
            dropdown_text_color=c("text"),
        ).pack(side="left")

        # ── 保存按钮
        save_row = ctk.CTkFrame(page, fg_color="transparent")
        save_row.pack(fill="x", pady=(PAD_INNER, 0))
        self._capsule_btn(
            save_row, "保存设置",
            lambda: self._fire("save_settings"),
            "accent", width=108, height=36
        ).pack(side="left")

        ctk.CTkLabel(
            page, text="分享助手 Pro · 玄天典籍界面",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
            anchor="w",
        ).pack(fill="x", pady=(PAD_INNER, 0))

        return page

    def _settings_dir_row(self, parent, label: str,
                          var: tk.StringVar) -> None:
        c = self._c
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=PAD_ROW // 2)
        ctk.CTkLabel(
            row, text=label,
            font=self._font(FS_BODY),
            text_color=c("text_dim"),
            width=72, anchor="w",
        ).pack(side="left")
        self._entry(row, var, readonly=True).pack(
            side="left", fill="x", expand=True)
        self._capsule_btn(
            row, "选择",
            lambda v=var: self._pick_dir(v),
            "ghost", width=56
        ).pack(side="left", padx=(PAD_BTN, 0))

    def _pick_dir(self, var: tk.StringVar) -> None:
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    # ──────────────────────────────────────────────────
    # 右侧分享栏
    # ──────────────────────────────────────────────────

    def _build_rail(self) -> None:
        c = self._c
        rail = ctk.CTkFrame(
            self,
            width=W_RAIL,
            corner_radius=0,
            fg_color=c("panel"),
        )
        rail.grid(row=0, column=2, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        self._rail = rail

        # 顶部状态色带（2px，随状态变色）
        self._rail_band = ctk.CTkFrame(
            rail, height=2, corner_radius=0,
            fg_color=c("text_dim"),
        )
        self._rail_band.grid(row=0, column=0, sticky="ew")

        # 标题
        ctk.CTkLabel(
            rail, text="分享状态",
            font=self._font(FS_SECTION, bold=True),
            text_color=c("text"),
        ).grid(row=1, column=0, sticky="w",
               padx=PAD_OUTER, pady=(PAD_INNER, PAD_ROW))

        # 状态指示卡片
        status_card = self._card(rail)
        status_card.grid(row=2, column=0, sticky="ew",
                         padx=PAD_OUTER, pady=(0, PAD_INNER))
        sc_inner = ctk.CTkFrame(status_card, fg_color="transparent")
        sc_inner.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)
        sc_inner.grid_columnconfigure(1, weight=1)

        self._rail_dot = ctk.CTkLabel(
            sc_inner, text="◉",
            font=self._font(FS_BODY),
            text_color=c("text_dim"),
        )
        self._rail_dot.grid(row=0, column=0)

        self._rail_state = ctk.CTkLabel(
            sc_inner, text="待机",
            font=self._font(FS_BODY, bold=True),
            text_color=c("text"),
        )
        self._rail_state.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self._rail_timer = ctk.CTkLabel(
            sc_inner, text="",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        )
        self._rail_timer.grid(row=0, column=2, sticky="e")

        self._rail_msg = ctk.CTkLabel(
            sc_inner, text="",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
            wraplength=W_RAIL - PAD_OUTER * 2 - PAD_INNER * 2,
            justify="left",
            anchor="w",
        )
        self._rail_msg.grid(row=1, column=0, columnspan=3,
                            sticky="ew", pady=(4, 0))

        # 分割线
        def _div(row_idx):
            ctk.CTkFrame(
                rail, height=1,
                fg_color=c("border"), corner_radius=0,
            ).grid(row=row_idx, column=0, sticky="ew",
                   padx=PAD_OUTER, pady=PAD_ROW)

        _div(3)

        # 分享链接区
        ctk.CTkLabel(
            rail, text="分享链接（给对方下载）",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        ).grid(row=4, column=0, sticky="w",
               padx=PAD_OUTER, pady=(0, 4))

        self._share_url_var = tk.StringVar(value="")
        self._entry(
            rail, self._share_url_var, "分享链接将在此显示", readonly=True
        ).grid(row=5, column=0, sticky="ew",
               padx=PAD_OUTER, pady=(0, 6))

        link_btns = ctk.CTkFrame(rail, fg_color="transparent")
        link_btns.grid(row=6, column=0, sticky="ew",
                       padx=PAD_OUTER, pady=(0, 0))
        self._capsule_btn(
            link_btns, "复制链接",
            lambda: self._fire("copy", self._share_url_var.get()),
            "ghost", width=76
        ).pack(side="left")
        self._capsule_btn(
            link_btns, "二维码",
            lambda: self._fire("qr", self._share_url_var.get()),
            "accent2", width=64
        ).pack(side="left", padx=(PAD_BTN, 0))
        self._capsule_btn(
            link_btns, "换链接",
            lambda: self._fire("refresh"),
            "ghost", width=64
        ).pack(side="left", padx=(PAD_BTN, 0))

        _div(7)

        # 密码
        ctk.CTkLabel(
            rail, text="访问密码",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        ).grid(row=8, column=0, sticky="w",
               padx=PAD_OUTER, pady=(0, 4))
        pw_row = ctk.CTkFrame(rail, fg_color="transparent")
        pw_row.grid(row=9, column=0, sticky="ew",
                    padx=PAD_OUTER, pady=(0, 0))
        self._pw_var = tk.StringVar(value="")
        self._entry(pw_row, self._pw_var, "留空则不需要密码").pack(
            side="left", fill="x", expand=True)
        self._capsule_btn(
            pw_row, "应用",
            lambda: self._fire("set_password", self._pw_var.get()),
            "ghost", width=52
        ).pack(side="left", padx=(PAD_BTN, 0))

        # 有效期
        ctk.CTkLabel(
            rail, text="链接有效期",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        ).grid(row=10, column=0, sticky="w",
               padx=PAD_OUTER, pady=(PAD_INNER, 4))
        self._ttl_var = tk.StringVar(value=TTL_LABELS[0])
        ctk.CTkOptionMenu(
            rail,
            values=TTL_LABELS,
            variable=self._ttl_var,
            command=lambda lbl: self._fire(
                "set_ttl", TTL_MAP.get(lbl, 0)),
            height=32,
            corner_radius=R_CAPSULE,
            font=self._font(FS_BODY),
            fg_color=c("card_hover"),
            button_color=c("border_hi"),
            button_hover_color=c("accent"),
            dropdown_fg_color=c("panel"),
            dropdown_hover_color=c("card_hover"),
            text_color=c("text"),
            dropdown_text_color=c("text"),
        ).grid(row=11, column=0, sticky="ew",
               padx=PAD_OUTER, pady=(0, 0))

        # 允许下载开关
        self._dl_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            rail,
            text="允许对方下载原文件",
            variable=self._dl_var,
            font=self._font(FS_BODY),
            text_color=c("text"),
            progress_color=c("accent"),
            button_color=c("accent_hover"),
            button_hover_color=c("accent"),
        ).grid(row=12, column=0, sticky="w",
               padx=PAD_OUTER, pady=PAD_INNER)

        # 大主按钮
        self._main_btn = ctk.CTkButton(
            rail,
            text="开始分享",
            height=44,
            corner_radius=R_CAPSULE,
            font=self._font(FS_SECTION, bold=True),
            fg_color=c("accent"),
            hover_color=c("accent_hover"),
            text_color="#0d1119",
            command=self._toggle_share,
        )
        self._main_btn.grid(row=13, column=0, sticky="ew",
                            padx=PAD_OUTER, pady=(0, PAD_ROW))

        self._capsule_btn(
            rail, "选择分享范围",
            lambda: self._fire("pick_sources"),
            "accent2", width=140, height=32
        ).grid(row=14, column=0, sticky="ew",
               padx=PAD_OUTER, pady=(0, PAD_ROW))

        ctk.CTkLabel(
            rail,
            text="链接是临时的，关掉程序就失效。",
            font=self._font(FS_MICRO),
            text_color=c("text_dim"),
        ).grid(row=15, column=0, sticky="w",
               padx=PAD_OUTER, pady=(0, PAD_INNER))

    def _toggle_share(self) -> None:
        if self._is_running:
            self._fire("stop")
        else:
            self._fire("share")

    # ──────────────────────────────────────────────────
    # 页面切换
    # ──────────────────────────────────────────────────

    def show_page(self, key: str) -> None:
        c = self._c
        for name, page in self._pages.items():
            if name == key:
                page.grid()
                page.tkraise()
            else:
                page.grid_remove()

        for name, btn in self._nav_btns.items():
            active = name == key
            btn.configure(
                fg_color=c("card") if active else "transparent",
                text_color=c("accent") if active else c("text_dim"),
                font=self._font(FS_BODY, bold=active),
            )

        # 设置页不显示右栏
        if key == "settings":
            self._rail.grid_remove()
            self._auto_scrollbar(self._pages["settings"])
            self.after_idle(lambda: self._fit_scroll_width(self._pages["settings"]))
        else:
            self._rail.grid()

    def _fit_scroll_width(self, scroll) -> None:
        """把可滚动页的内层拉到可视宽度（CTk 只在 canvas <Configure> 时拉一次，
        页面藏起来再显示时会漏掉，卡片就缩成一条）。"""
        try:
            canvas = scroll._parent_canvas
            scroll.update_idletasks()
            canvas.itemconfigure(scroll._create_window_id, width=canvas.winfo_width())
        except Exception:
            pass

    # ──────────────────────────────────────────────────
    # 数据入口（外部调用）
    # ──────────────────────────────────────────────────

    def set_state(self, state: str, message: str = "") -> None:
        self._state   = state
        self._message = message
        self._is_running = (state == "running")

        c = self._c
        color_key = STATE_COLOR.get(state, "text_dim")
        color     = c(color_key)
        label     = STATE_LABEL.get(state, "未知")

        self._rail_dot.configure(text_color=color)
        self._rail_state.configure(text=label)
        self._rail_band.configure(fg_color=color)
        self._side_dot.configure(text_color=color)
        self._side_state.configure(text=label)

        if message:
            self._rail_msg.configure(text=message)
        else:
            self._rail_msg.configure(text="")

        if self._is_running:
            self._main_btn.configure(
                text="停止分享",
                fg_color=c("danger"),
                hover_color="#c94040",
                text_color="#ffffff",
            )
        else:
            self._main_btn.configure(
                text="开始分享",
                fg_color=c("accent"),
                hover_color=c("accent_hover"),
                text_color="#0d1119",
            )

    def set_links(self, share_url: str, receive_url: str) -> None:
        self._share_url   = share_url
        self._receive_url = receive_url
        self._share_url_var.set(share_url)
        self._recv_url_var.set(receive_url)
        # 侧栏显示短链（去掉协议头）
        short = share_url.replace("https://", "").replace("http://", "")
        self._side_link.configure(text=short[:36] + ("…" if len(short) > 36 else ""))

    def set_remaining(self, seconds: int) -> None:
        self._remain = seconds
        self._rail_timer.configure(text=_fmt_remain(seconds))

    def set_groups(self, names: list, current: str) -> None:
        self._groups  = names
        self._cur_grp = current
        self._render_chips()

    def _render_chips(self) -> None:
        c = self._c
        for child in self._chip_row.winfo_children():
            child.destroy()

        if not self._groups:
            ctk.CTkLabel(
                self._chip_row,
                text="还没有分组，",
                font=self._font(FS_SMALL),
                text_color=c("text_dim"),
            ).pack(side="left", padx=(0, 4))

        for name in self._groups:
            active = name == self._cur_grp
            ctk.CTkButton(
                self._chip_row,
                text=f"▤ {name}",
                height=30,
                corner_radius=R_CHIP,
                font=self._font(FS_SMALL),
                fg_color=c("accent") if active else c("card"),
                hover_color=c("accent_hover") if active else c("card_hover"),
                text_color="#0d1119" if active else c("text"),
                border_width=0 if active else 1,
                border_color=c("border"),
                command=lambda n=name: self._fire("switch_group", n),
            ).pack(side="left", padx=(0, PAD_BTN))

        # 新建按钮
        ctk.CTkButton(
            self._chip_row,
            text="＋ 新建",
            height=30,
            corner_radius=R_CHIP,
            font=self._font(FS_SMALL),
            fg_color="transparent",
            hover_color=c("card_hover"),
            text_color=c("accent2"),
            border_width=1,
            border_color=c("accent2"),
            command=lambda: self._fire("new_group"),
        ).pack(side="left")
        self._auto_scrollbar(self._chip_row)

    def set_files(self, items: list) -> None:
        c = self._c
        for child in self._file_scroll.winfo_children():
            child.destroy()

        if not items:
            self._empty_card.place(relx=0.5, rely=0.52, anchor="center")
            self._file_count_lbl.configure(text="暂无文件")
            self._auto_scrollbar(self._file_scroll)
            return

        try:
            self._empty_card.place_forget()
        except Exception:
            pass

        for idx, item in enumerate(items):
            name      = item.get("name", "未知文件")
            size_text = item.get("size_text", "")
            time_text = item.get("time_text", "")
            is_dir    = item.get("is_dir", False)
            icon      = FILE_ICONS.get("文件夹" if is_dir else "其他", "◆")

            row = ctk.CTkFrame(
                self._file_scroll,
                fg_color=c("card"),
                corner_radius=R_CARD,
                border_width=1,
                border_color=c("border"),
            )
            row.grid(row=idx, column=0, sticky="ew",
                     pady=2, padx=1)
            row.grid_columnconfigure(2, weight=1)

            # 左书签竖条
            ctk.CTkFrame(
                row,
                width=BOOKMARK_W, height=36,
                fg_color=c("accent2"),
                corner_radius=0,
            ).grid(row=0, column=0, rowspan=2,
                   padx=(0, PAD_ROW), pady=0, sticky="ns")

            # 图标
            ctk.CTkLabel(
                row, text=icon,
                font=self._font(FS_SECTION),
                text_color=c("accent2"),
            ).grid(row=0, column=1, rowspan=2,
                   padx=(PAD_ROW, PAD_ROW), pady=4)

            # 名称 + 元信息
            info_box = ctk.CTkFrame(row, fg_color="transparent")
            info_box.grid(row=0, column=2, columnspan=2,
                          sticky="ew", padx=(0, PAD_INNER),
                          pady=(6, 0))
            ctk.CTkLabel(
                info_box, text=_short_name(name),
                font=self._font(FS_BODY),
                text_color=c("text"),
                anchor="w",
            ).pack(anchor="w")
            meta = (size_text + "  ·  " + time_text).strip("  ·  ")
            ctk.CTkLabel(
                info_box, text=meta,
                font=self._font(FS_MICRO),
                text_color=c("text_dim"),
                anchor="w",
            ).pack(anchor="w")

            # 操作按钮
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.grid(row=0, column=4, rowspan=2,
                     padx=(0, PAD_INNER), pady=4)
            self._capsule_btn(
                act, "打开",
                lambda p=item.get("path") or name: self._fire("open_path", p),
                "ghost", width=52, height=28
            ).pack(side="left", padx=(0, 4))
            self._capsule_btn(
                act, "删除",
                lambda p=item.get("path") or name: self._fire("delete_path", p),
                "danger", width=52, height=28
            ).pack(side="left")

        self._file_count_lbl.configure(text=f"共 {len(items)} 项")
        self._auto_scrollbar(self._file_scroll)

    def set_received(self, items: list) -> None:
        c = self._c
        for child in self._recv_scroll.winfo_children():
            child.destroy()

        if not items:
            ctk.CTkLabel(
                self._recv_scroll,
                text="还没有人传文件过来",
                font=self._font(FS_BODY),
                text_color=c("text_dim"),
            ).grid(row=0, column=0, pady=40)
            self._auto_scrollbar(self._recv_scroll)
            return

        for idx, item in enumerate(items):
            name      = item.get("name", "未知")
            size_text = item.get("size_text", "")
            time_text = item.get("time_text", "")

            row = ctk.CTkFrame(
                self._recv_scroll,
                fg_color=c("card"),
                corner_radius=R_CARD,
                border_width=1,
                border_color=c("border"),
            )
            row.grid(row=idx, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row, text=_short_name(name),
                font=self._font(FS_BODY),
                text_color=c("text"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew",
                   padx=PAD_INNER, pady=(PAD_ROW, 0))
            ctk.CTkLabel(
                row,
                text=f"{size_text}  ·  {time_text}",
                font=self._font(FS_MICRO),
                text_color=c("text_dim"),
                anchor="w",
            ).grid(row=1, column=0, sticky="ew",
                   padx=PAD_INNER, pady=(0, PAD_ROW))
            self._capsule_btn(
                row, "打开",
                lambda p=item.get("path") or name: self._fire("open_path", p),
                "ghost", width=52, height=26
            ).grid(row=0, column=1, rowspan=2,
                   padx=(0, PAD_INNER))
        self._auto_scrollbar(self._recv_scroll)

    def set_receive_open(self, opened: bool) -> None:
        if opened:
            self._recv_switch.select()
        else:
            self._recv_switch.deselect()
        self._recv_state_lbl.configure(
            text="接收区已开启" if opened else "接收区已关闭，对方访问会看到提示")

    def set_quota(self, text: str) -> None:
        self._recv_quota_lbl.configure(text=text)

    # ──────────────────────────────────────────────────
    # Toast 提示
    # ──────────────────────────────────────────────────

    def toast(self, text: str, ok: bool = True) -> None:
        c = self._c
        if self._toast_lbl is not None:
            try:
                self._toast_lbl.destroy()
            except Exception:
                pass
        if self._toast_job is not None:
            try:
                self.after_cancel(self._toast_job)
            except Exception:
                pass

        prefix = "✦ " if ok else "⚠ "
        self._toast_lbl = ctk.CTkLabel(
            self,
            text=prefix + text,
            font=self._font(FS_BODY),
            text_color="#0d1119" if ok else "#ffffff",
            fg_color=c("ok") if ok else c("danger"),
            corner_radius=R_CAPSULE,
            height=32,
            padx=16,
        )
        self._toast_lbl.place(relx=0.5, rely=0.96, anchor="center")
        self._toast_job = self.after(2400, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast_lbl is not None:
            try:
                self._toast_lbl.destroy()
            except Exception:
                pass
            self._toast_lbl = None
        self._toast_job = None

    # ──────────────────────────────────────────────────
    # 二维码弹窗
    # ──────────────────────────────────────────────────

    def show_qr(self, url: str) -> None:
        if not url:
            self.toast("还没有链接", False)
            return
        try:
            import qrcode
            from PIL import Image as PilImage
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color=self._c("text"),
                                back_color=self._c("card"))
            pil_img = img.convert("RGB")
        except Exception:
            self.toast("二维码库不可用", False)
            return

        c = self._c
        win = ctk.CTkToplevel(self)
        win.title("扫码打开")
        win.geometry("360x480")
        win.configure(fg_color=c("bg"))
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        ctk.CTkLabel(
            win, text="扫码打开链接",
            font=self._font(FS_SECTION, bold=True),
            text_color=c("accent"),
        ).pack(pady=(PAD_OUTER, PAD_ROW))

        ctk.CTkLabel(
            win, text="对方扫码即可访问",
            font=self._font(FS_SMALL),
            text_color=c("text_dim"),
        ).pack(pady=(0, PAD_INNER))

        # 金色边框包裹二维码
        qr_frame = ctk.CTkFrame(
            win, fg_color=c("card"),
            corner_radius=R_CARD,
            border_width=1,
            border_color=c("accent"),
        )
        qr_frame.pack(padx=PAD_OUTER)

        ctk_img = ctk.CTkImage(
            light_image=pil_img,
            dark_image=pil_img,
            size=(260, 260),
        )
        ctk.CTkLabel(
            qr_frame, text="", image=ctk_img,
            width=260, height=260,
        ).pack(padx=10, pady=10)

        # 链接文本
        link_e = self._entry(win, placeholder="")
        link_e.pack(fill="x", padx=PAD_OUTER, pady=PAD_INNER)
        link_e.insert(0, url)
        link_e.configure(state="disabled")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack()
        self._capsule_btn(
            btn_row, "复制链接",
            lambda: (self.winfo_toplevel().clipboard_clear(),
                     self.winfo_toplevel().clipboard_append(url),
                     self.toast("已复制链接")),
            "accent", width=100
        ).pack(side="left", padx=PAD_BTN)
        self._capsule_btn(
            btn_row, "关闭",
            win.destroy,
            "ghost", width=72
        ).pack(side="left")

    # ──────────────────────────────────────────────────
    # 回调分发
    # ──────────────────────────────────────────────────

    def _fire(self, key: str, *args) -> None:
        fn = self._on.get(key)
        if callable(fn):
            try:
                if args:
                    fn(*args)
                else:
                    fn()
            except Exception as exc:
                self.toast(f"操作出错：{exc}", False)
