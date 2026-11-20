# -*- coding: utf-8 -*-
"""会话服务层：本地 HTTP + 隧道 + 有效期 + 统计 + 接收区。

界面只跟这一层打交道，不直接碰 server / tunnel。
一次会话 = 一条链接，同时提供两个入口：
    <链接>/          分享（看文件、下载）
    <链接>/receive   接收区（对面把文件传回来）
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

from .share.options import ShareOptions
from .share.server import ShareServer
from .share.stats import Stats
from .share.tunnel import (STATE_ERROR, STATE_IDLE, STATE_RUNNING,
                           STATE_STARTING, STATE_STOPPED, Tunnel)

IDLE = "idle"
STARTING = "starting"
RUNNING = "running"
ERROR = "error"
STOPPED = "stopped"


class ShareService:
    def __init__(self, stats_path: str, web_dir: str, theme: dict | None = None,
                 on_state: Callable[[str, str], None] | None = None,
                 on_url: Callable[[str], None] | None = None,
                 on_log: Callable[[str], None] | None = None) -> None:
        self.stats = Stats(stats_path)
        self.web_dir = web_dir
        self.theme = theme or {}
        self.on_state = on_state
        self.on_url = on_url
        self.on_log = on_log

        self.server: ShareServer | None = None
        self.tunnel: Tunnel | None = None
        self.options: ShareOptions | None = None
        self.lan_url = ""
        self.lan_mode = False
        self._lock = threading.RLock()
        self._watch = False
        self._watchdog: threading.Thread | None = None
        self._stopping = False
        self._last = (IDLE, "未开始")

    # ------------------------------------------------------------ 状态
    @property
    def running(self) -> bool:
        return bool(self.server and self.server.running)

    @property
    def state(self) -> str:
        if not self.running:
            return IDLE if self._last[0] in (IDLE, STOPPED, ERROR) else self._last[0]
        if self.lan_mode:
            return RUNNING if self.lan_url else STARTING
        return self.tunnel.state if self.tunnel else STARTING

    @property
    def message(self) -> str:
        if not self.running:
            return self._last[1]
        if self.lan_mode:
            return self.lan_url or "正在准备局域网地址…"
        return self.tunnel.message if self.tunnel else "正在建立隧道…"

    @property
    def url(self) -> str:
        if not self.running:
            return ""
        if self.lan_mode:
            return self.lan_url
        return self.tunnel.url if self.tunnel else ""

    @property
    def share_url(self) -> str:
        url = self.url
        return url.rstrip("/") + "/" if url else ""

    @property
    def receive_url(self) -> str:
        url = self.url
        return url.rstrip("/") + "/receive" if url else ""

    @property
    def remaining(self) -> int:
        return self.options.remaining if self.options else -1

    def _emit(self, state: str, message: str) -> None:
        self._last = (state, message)
        if self.on_state:
            try:
                self.on_state(state, message)
            except Exception:
                pass

    def _log(self, line: str) -> None:
        if self.on_log:
            try:
                self.on_log(line)
            except Exception:
                pass

    # ------------------------------------------------------------ 启停
    def start(self, sources: list[tuple[str, str]], *, title: str = "我的分享",
              password: str = "", ttl_seconds: int = 0,
              allow_download: bool = True, allow_upload: bool = True,
              receive_dir: str = "", receive_limit: int = 0, lan: bool = False,
              fresh_link: bool = True) -> bool:
        with self._lock:
            if self.running:
                self.apply(password=password, ttl=ttl_seconds,
                           allow_download=allow_download, allow_upload=allow_upload,
                           receive_dir=receive_dir, sources=sources)
                return True
            self._stopping = False
            self.lan_mode = lan
            try:
                options = ShareOptions(
                    sources=list(sources or []), title=title,
                    password=password, ttl_seconds=ttl_seconds,
                    allow_upload=allow_upload, upload_dir=receive_dir,
                    receive_limit=receive_limit,
                    allow_download=allow_download,
                ).normalized()
                if not options.sources:
                    self._emit(ERROR, "没有可分享的文件夹")
                    return False
                if not options.upload_dir:
                    options.upload_dir = receive_dir
                self.options = options
                self.server = ShareServer(options, self.stats, self.web_dir,
                                          theme=self.theme,
                                          on_event=lambda lv, msg: self._log(f"[{lv}] {msg}"))
                self.server.start(lan=lan)
                self.lan_url = (f"http://{self.server.lan_ip()}:{self.server.port}/"
                                if lan else "")
            except Exception as exc:
                self._emit(ERROR, f"启动本地服务失败：{exc}")
                self.server = None
                return False

            if lan:
                self._emit(RUNNING, self.lan_url)
                if self.on_url:
                    self.on_url(self.lan_url)
            else:
                self._new_tunnel()

            self._watch = True
            if not self._watchdog or not self._watchdog.is_alive():
                self._watchdog = threading.Thread(target=self._expire_loop,
                                                  name="share-expire", daemon=True)
                self._watchdog.start()
            return True

    def _new_tunnel(self) -> bool:
        self.tunnel = Tunnel(on_state=self._on_tunnel_state,
                             on_url=self._on_tunnel_url, on_log=self._log)
        if not self.tunnel.available:
            self._emit(ERROR, "找不到 cloudflared.exe（bin 目录），可改用局域网模式")
            return False
        self._emit(STARTING, "正在建立隧道…")
        return self.tunnel.start(self.server.local_url())

    def _on_tunnel_state(self, state: str, message: str) -> None:
        if self._stopping or not self.server:
            return
        self._emit(state, message)

    def _on_tunnel_url(self, url: str) -> None:
        if self.on_url:
            try:
                self.on_url(url)
            except Exception:
                pass

    def stop(self, reason: str = "") -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._watch = False
            if self.tunnel:
                try:
                    self.tunnel.stop()
                except Exception:
                    pass
                self.tunnel = None
            if self.server:
                try:
                    self.server.stop()
                except Exception:
                    pass
                self.server = None
            self.lan_url = ""
            self.options = None
            try:
                self.stats.save()
            except Exception:
                pass
            self._stopping = False
        self._emit(STOPPED, reason or "已停止")

    def refresh_link(self) -> bool:
        """换一条新链接：只重启隧道，本地服务与已上传内容不动。"""
        with self._lock:
            if not self.running or not self.server:
                return False
            if self.lan_mode:
                return False
            if self.tunnel:
                try:
                    self.tunnel.stop()
                except Exception:
                    pass
            self._emit(STARTING, "正在更换新链接…")
            return self._new_tunnel()

    def restart(self, **kwargs) -> bool:
        self.stop(reason="正在重启…")
        time.sleep(0.2)
        return self.start(**kwargs)

    # ------------------------------------------------------------ 运行时改参数
    def apply(self, *, password: str | None = None, ttl: int | None = None,
              allow_download: bool | None = None, allow_upload: bool | None = None,
              receive_dir: str | None = None,
              sources: list[tuple[str, str]] | None = None) -> None:
        opts = self.options
        if opts is None:
            return
        with self._lock:
            if password is not None:
                opts.password = str(password)
                # 换密码后旧 Cookie 立即失效
                if self.server:
                    import secrets
                    self.server.secret = secrets.token_bytes(32)
                    self.server.token = secrets.token_urlsafe(12)
                    opts.token = self.server.token
            if ttl is not None:
                opts.ttl_seconds = max(0, int(ttl))
                opts.started_at = time.time()
            if allow_download is not None:
                opts.allow_download = bool(allow_download)
            if allow_upload is not None:
                opts.allow_upload = bool(allow_upload)
            if receive_dir:
                opts.upload_dir = os.path.abspath(receive_dir)
                if self.server and self.server.upload_api:
                    self.server.upload_api.receive_dir = opts.upload_dir

    def set_receive_open(self, opened: bool) -> None:
        self.apply(allow_upload=bool(opened))

    # ------------------------------------------------------------ 有效期
    def _expire_loop(self) -> None:
        while self._watch:
            time.sleep(1)
            try:
                opts = self.options
                if opts and opts.expired():
                    self.stop(reason="分享已到期，已自动停止")
                    return
            except Exception:
                continue

    # ------------------------------------------------------------ 收件
    def received_files(self, limit: int = 300) -> list[dict]:
        folder = (self.options.upload_dir if self.options else "") or ""
        if not folder or not os.path.isdir(folder):
            return []
        items: list[dict] = []
        try:
            for entry in os.scandir(folder):
                if not entry.is_file():
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                items.append({"name": entry.name, "path": entry.path,
                              "size": stat.st_size, "mtime": stat.st_mtime})
        except OSError:
            return []
        items.sort(key=lambda item: item["mtime"], reverse=True)
        return items[:limit]

    # ------------------------------------------------------------ 统计
    def snapshot(self) -> dict:
        try:
            return self.stats.snapshot()
        except Exception:
            return {}

    def reset_stats(self) -> None:
        try:
            self.stats.reset()
        except Exception:
            pass
