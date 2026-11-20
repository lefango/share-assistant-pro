# -*- coding: utf-8 -*-
"""配置：带版本号、默认值、原子写入、坏文件自动兜底。

配置文件：%APPDATA%\\分享助手Pro\\config.json
"""
from __future__ import annotations

import json
import os
import tempfile
import threading

from . import paths

CONFIG_VERSION = 3

DEFAULTS: dict = {
    "version": CONFIG_VERSION,
    "library_dir": "",
    "receive_dir": "",
    "last_group": "",
    "title": "我的分享",
    "password": "",
    "ttl": 0,                     # 0 = 不限时
    "allow_download": True,
    "receive_open": True,         # 接收区是否允许别人上传
    "receive_limit": 1024 ** 3,   # 本次最多接收多少字节；0 = 不限
    "auto_start": True,           # 启动程序后自动开启分享
    "auto_new_link": True,        # 每次启动都换一条新链接
    "lan_fallback": True,         # 隧道失败时退回局域网
    "ui": "default",              # 界面实现，后续换 UI 改这里
    "skin": "default",            # 皮肤，同时作用于桌面界面和网页
}


def _read_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


class Config:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.path.join(paths.config_dir(), "config.json")
        self._lock = threading.RLock()
        self._data: dict = dict(DEFAULTS)
        self.load()

    # ---------------- 读写 ----------------
    def load(self) -> dict:
        with self._lock:
            raw = _read_json(self.path)
            merged = dict(DEFAULTS)
            for key, value in raw.items():
                if key in DEFAULTS:
                    merged[key] = value
            merged["version"] = CONFIG_VERSION
            self._data = merged
            self._normalize()
            return self._data

    def _normalize(self) -> None:
        d = self._data
        if not d.get("library_dir"):
            d["library_dir"] = paths.default_library_dir()
        if not d.get("receive_dir"):
            d["receive_dir"] = paths.default_receive_dir()
        try:
            d["ttl"] = max(0, int(d.get("ttl") or 0))
        except Exception:
            d["ttl"] = 0
        try:
            d["receive_limit"] = max(0, int(d.get("receive_limit") or 0))
        except Exception:
            d["receive_limit"] = 0
        d["library_dir"] = os.path.abspath(os.path.expanduser(str(d["library_dir"])))
        d["receive_dir"] = os.path.abspath(os.path.expanduser(str(d["receive_dir"])))
        for key in ("allow_download", "receive_open", "auto_start",
                    "auto_new_link", "lan_fallback"):
            d[key] = bool(d.get(key, DEFAULTS[key]))
        d["password"] = str(d.get("password") or "")
        d["title"] = (str(d.get("title") or "我的分享").strip() or "我的分享")[:60]
        d["ui"] = str(d.get("ui") or "default")
        d["skin"] = str(d.get("skin") or "default")

    def save(self) -> None:
        with self._lock:
            self._normalize()
            data = json.dumps(self._data, ensure_ascii=False, indent=2)
            folder = os.path.dirname(self.path)
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".cfg-", suffix=".tmp", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            except Exception:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                raise

    # ---------------- 访问 ----------------
    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value, save: bool = True) -> None:
        with self._lock:
            self._data[key] = value
            self._normalize()
        if save:
            self.save()

    def update(self, mapping: dict) -> None:
        with self._lock:
            self._data.update(mapping)
            self._normalize()
        self.save()

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    # ---------------- 目录准备 ----------------
    def ensure_dirs(self) -> tuple[str, str]:
        library = paths.ensure_dir(self.get("library_dir"))
        receive = paths.ensure_dir(self.get("receive_dir"))
        return library, receive
