# -*- coding: utf-8 -*-
"""皮肤：一套 JSON 同时驱动「桌面界面」和「网页界面」。

换 UI / 换配色时只改 skin/<名字>/theme.json（或加一个目录），
桌面端和对面打开的网页会一起变 —— 这就是后面换皮的接口。
"""
from __future__ import annotations

import json
import os

from . import paths

DEFAULT_THEME = {
    "name": "default",
    "label": "默认深色",
    "title": "分享助手",
    "font": "Microsoft YaHei UI",
    "radius": 14,
    "colors": {
        "bg": "#0f1115",
        "panel": "#151922",
        "card": "#1a202b",
        "card_hover": "#222a38",
        "border": "#28303d",
        "border_hi": "#36415a",
        "text": "#e9eef7",
        "text_dim": "#93a0b4",
        "accent": "#4f8cff",
        "accent_hover": "#6ba0ff",
        "accent2": "#8b5cf6",
        "ok": "#3ecf8e",
        "warn": "#f5a524",
        "danger": "#f45b69",
    },
}

# 网页 CSS 变量 ← 皮肤字段
_WEB_MAP = {
    "--bg": "bg",
    "--accent": "accent",
    "--accent-2": "accent2",
    "--fg": "text",
    "--sub": "text_dim",
    "--danger": "danger",
    "--warn": "warn",
}


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def available() -> list[str]:
    root = paths.skin_dir()
    if not os.path.isdir(root):
        return ["default"]
    names = [name for name in os.listdir(root)
             if os.path.isfile(os.path.join(root, name, "theme.json"))]
    return sorted(names) or ["default"]


def load(name: str = "default") -> dict:
    path = os.path.join(paths.skin_dir(), name, "theme.json")
    theme = json.loads(json.dumps(DEFAULT_THEME))
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                theme = _merge(theme, json.load(fh))
        except Exception:
            pass
    theme.setdefault("colors", {})
    theme["colors"] = _merge(DEFAULT_THEME["colors"], theme["colors"])
    theme["name"] = name
    return theme


def color(theme: dict, key: str) -> str:
    return theme.get("colors", {}).get(key, DEFAULT_THEME["colors"].get(key, "#ffffff"))


def web_style(theme: dict) -> str:
    """给网页用的 :root 覆盖块。"""
    lines = []
    for var, key in _WEB_MAP.items():
        lines.append(f"{var}:{color(theme, key)}")
    lines.append(f"--r:{int(theme.get('radius') or 14)}px")
    return "<style>:root{" + ";".join(lines) + "}</style>"


def inject(html: str, theme: dict) -> str:
    """把皮肤、标题注入网页。占位符可省，没有就插在 </head> 前。"""
    style = web_style(theme)
    title = str(theme.get("title") or "分享助手")
    if "<!--SKIN-->" in html:
        html = html.replace("<!--SKIN-->", style)
    else:
        html = html.replace("</head>", style + "\n</head>", 1)
    html = html.replace("<!--APP_TITLE-->", title)
    return html
