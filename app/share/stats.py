# -*- coding: utf-8 -*-
"""下载统计与访问日志。

数据落盘在 %APPDATA%\\分享助手\\stats.json：
    {
      "downloads": {"total": 12, "zip": 3, "file": 9},
      "files": {"图片/猫.jpg": 4},
      "visits": 88,
      "log": [{"t": 1699999999, "ip": "1.2.3.4", "ua": "...", "act": "file", "path": "..."}]
    }
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any

LOG_LIMIT = 2000


class Stats:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {
            "downloads": {"total": 0, "zip": 0, "file": 0},
            "files": {},
            "visits": 0,
            "sessions": 0,
            "log": [],
        }
        self._dirty = 0
        self._load()

    # ---------------- 读写 ----------------
    def _load(self) -> None:
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(self.path, "r", encoding=encoding) as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                    self.data.setdefault("downloads", {"total": 0, "zip": 0, "file": 0})
                    self.data.setdefault("files", {})
                    self.data.setdefault("log", [])
                return
            except FileNotFoundError:
                return
            except Exception:
                continue

    def save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception:
                pass

    def save_if_dirty(self, every: int = 25) -> None:
        with self._lock:
            self._dirty += 1
            if self._dirty >= every:
                self._dirty = 0
                self.save()

    # ---------------- 记录 ----------------
    def _log(self, action: str, path: str, ip: str, ua: str) -> None:
        log = self.data["log"]
        log.append({
            "t": int(time.time()),
            "ip": ip,
            "ua": (ua or "")[:160],
            "act": action,
            "path": path[:300],
        })
        if len(log) > LOG_LIMIT:
            del log[: len(log) - LOG_LIMIT]

    def record_visit(self, ip: str, ua: str) -> None:
        with self._lock:
            self.data["visits"] = int(self.data.get("visits", 0)) + 1
            self._log("visit", "", ip, ua)
        self.save_if_dirty()

    def record_open(self, path: str, ip: str, ua: str) -> None:
        with self._lock:
            self.data["sessions"] = int(self.data.get("sessions", 0)) + 1
            self._log("open", path, ip, ua)
        self.save_if_dirty()

    def record_download(self, path: str, ip: str, ua: str, kind: str = "file") -> None:
        with self._lock:
            downloads = self.data["downloads"]
            downloads["total"] = int(downloads.get("total", 0)) + 1
            downloads[kind] = int(downloads.get(kind, 0)) + 1
            if kind == "file" and path:
                files = self.data["files"]
                files[path] = int(files.get(path, 0)) + 1
            self._log("zip" if kind == "zip" else "file", path, ip, ua)
        self.save_if_dirty()

    def record_upload(self, path: str, size: int, ip: str, ua: str) -> None:
        with self._lock:
            uploads = self.data.setdefault("uploads", {"total": 0, "bytes": 0})
            uploads["total"] = int(uploads.get("total", 0)) + 1
            uploads["bytes"] = int(uploads.get("bytes", 0)) + size
            self._log("upload", path, ip, ua)
        self.save_if_dirty(every=1)

    def record_block(self, reason: str, ip: str, ua: str) -> None:
        with self._lock:
            blocked = self.data.setdefault("blocked", 0)
            self.data["blocked"] = int(blocked) + 1
            self._log("block:" + reason, "", ip, ua)
        self.save_if_dirty()

    # ---------------- 读取 ----------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            downloads = dict(self.data.get("downloads") or {})
            files = dict(self.data.get("files") or {})
            uploads = dict(self.data.get("uploads") or {"total": 0, "bytes": 0})
            log = list(self.data.get("log") or [])[-120:]
            return {
                "downloads": downloads,
                "top_files": sorted(files.items(), key=lambda kv: -kv[1])[:12],
                "visits": int(self.data.get("visits", 0)),
                "sessions": int(self.data.get("sessions", 0)),
                "uploads": uploads,
                "blocked": int(self.data.get("blocked", 0)),
                "log": list(reversed(log)),
            }

    def reset(self) -> None:
        with self._lock:
            self.data = {
                "downloads": {"total": 0, "zip": 0, "file": 0},
                "files": {},
                "visits": 0,
                "sessions": 0,
                "uploads": {"total": 0, "bytes": 0},
                "blocked": 0,
                "log": [],
            }
        self.save()


def recent_log(stats: Stats, limit: int = 40) -> deque:
    snap = stats.snapshot()
    return deque(snap["log"][:limit])
