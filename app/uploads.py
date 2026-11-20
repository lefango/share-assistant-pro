# -*- coding: utf-8 -*-
"""分片上传 + 接收总量配额。

分两段由本地模型生成（配额 / 分片），组装后由人验收。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .library import sanitize_name, unique_path

CHUNK_SIZE = 64 * 1024 * 1024   # 64MB


CHUNK_SIZE = 64 * 1024 * 1024   # 64MB


class UploadQuota:
    """一次分享会话的接收总量上限（0 = 不限量）。"""

    def __init__(self, limit_bytes: int) -> None:
        self._limit = max(0, int(limit_bytes or 0))
        self._used = 0
        self._lock = threading.Lock()

    def remaining(self) -> int:
        with self._lock:
            if self._limit == 0:
                return -1
            return max(0, self._limit - self._used)

    def accept(self, size: int) -> bool:
        with self._lock:
            if size <= 0:
                return False
            if self._limit == 0:
                return True
            return self._used + size <= self._limit

    def add(self, size: int) -> None:
        with self._lock:
            if size > 0:
                self._used += size

    def reset(self) -> None:
        with self._lock:
            self._used = 0

    def snapshot(self) -> dict:
        with self._lock:
            if self._limit == 0:
                rem = -1
            else:
                rem = max(0, self._limit - self._used)
            return {
                "limit": int(self._limit),
                "used": int(self._used),
                "remaining": int(rem),
            }


class ChunkStore:
    """把大文件拆成多个请求传过来，最后拼回完整文件。"""

    def __init__(self, temp_dir: str) -> None:
        self.temp_dir = temp_dir
        self._items: dict = {}
        self._lock = threading.Lock()
        os.makedirs(self.temp_dir, exist_ok=True)

    @staticmethod
    def _key(upload_id: str) -> str:
        """upload_id → 内部键：只留安全字符。

        begin 的时候清洗过一次，但 write_chunk / finish 拿原始 id 查表，
        带非法字符的 id 就会 KeyError；这里统一成同一个键，四处都用它。
        全非法字符的 id 用 sha1 派生，保证同一个 id 每次算出来一样。
        """
        raw = upload_id or ""
        cid = re.sub(r"[^0-9a-zA-Z_-]", "", raw)
        if cid:
            return cid
        return "x" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    def begin(self, upload_id: str, file_name: str, total_size: int) -> str:
        cid = self._key(upload_id)
        if not cid:
            cid = uuid.uuid4().hex
        with self._lock:
            if cid in self._items:
                return self._items[cid]["temp"]
            base = os.path.basename(sanitize_name(file_name))
            if not base:
                base = "未命名文件"
            temp = os.path.join(self.temp_dir, cid + ".part")
            with open(temp, "wb"):
                pass
            self._items[cid] = {
                "name": base,
                "total": total_size,
                "temp": temp,
                "got": 0,
                "next_index": 0,
                "created": time.time(),
            }
            return temp

    def write_chunk(self, upload_id: str, index: int, data: bytes) -> None:
        cid = self._key(upload_id)
        with self._lock:
            info = self._items.get(cid)
            if info is None:
                raise KeyError(upload_id)
            if index != info["next_index"]:
                raise ValueError(f"expected index {info['next_index']}, got {index}")
            with open(info["temp"], "ab") as f:
                f.write(data)
            info["got"] += len(data)
            info["next_index"] = index + 1
            if info["got"] > info["total"]:
                raise ValueError("received size exceeds declared total_size")

    def received(self, upload_id: str) -> int:
        cid = self._key(upload_id)
        with self._lock:
            info = self._items.get(cid)
            if info is None:
                raise KeyError(upload_id)
            return info["got"]

    def finish(self, upload_id: str, dest_dir: str) -> tuple[str, int]:
        cid = self._key(upload_id)
        with self._lock:
            info = self._items.get(cid)
            if info is None:
                raise KeyError(upload_id)
            os.makedirs(dest_dir, exist_ok=True)
            dest = unique_path(Path(dest_dir) / info["name"])
            shutil.move(info["temp"], str(dest))
            got = info["got"]
            del self._items[cid]
            return (str(dest), got)

    def abort(self, upload_id: str) -> None:
        cid = self._key(upload_id)
        with self._lock:
            info = self._items.pop(cid, None)
            if info is not None:
                tmp = info["temp"]
                if os.path.exists(tmp):
                    os.remove(tmp)

    def cleanup(self, max_age_seconds: int = 21600) -> int:
        count = 0
        with self._lock:
            now = time.time()
            for cid in list(self._items.keys()):
                info = self._items[cid]
                if now - info["created"] > max_age_seconds:
                    tmp = info["temp"]
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    del self._items[cid]
                    count += 1
        return count
