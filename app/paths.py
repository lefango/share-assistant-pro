# -*- coding: utf-8 -*-
"""运行路径：源码运行与 PyInstaller 打包后 exe 运行都能用。"""
from __future__ import annotations

import os
import sys

APP_NAME = "分享助手Pro"
APP_FOLDER = "分享助手Pro"
VERSION = "3.0.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """程序所在目录（exe 目录 / 源码根目录）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """打包后单文件模式的解包目录，源码模式等于 app_dir。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and os.path.isdir(meipass):
        return meipass
    return app_dir()


def config_dir() -> str:
    base = (os.environ.get("APPDATA")
            or os.environ.get("XDG_CONFIG_HOME")
            or os.path.expanduser("~"))
    path = os.path.join(base, APP_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def data_dir() -> str:
    """用户数据根目录：文档\\分享助手Pro。"""
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    base = docs if os.path.isdir(docs) else home
    path = os.path.join(base, APP_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def default_library_dir() -> str:
    return os.path.join(data_dir(), "文件库")


def default_receive_dir() -> str:
    return os.path.join(data_dir(), "收件箱")


def web_dir() -> str:
    return os.path.join(resource_dir(), "web")


def skin_dir(name: str = "") -> str:
    root = os.path.join(resource_dir(), "skin")
    return os.path.join(root, name) if name else root


def cloudflared_path() -> str:
    """内置 cloudflared 的常规位置。"""
    return os.path.join(resource_dir(), "bin", "cloudflared.exe")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
