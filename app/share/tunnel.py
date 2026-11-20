# -*- coding: utf-8 -*-
"""cloudflared 隧道管理。

参考实现（分享助手-电脑版）的做法：
    cloudflared.exe tunnel --url http://127.0.0.1:<PORT>
再从输出里用正则 https://[a-z0-9-]+\\.trycloudflare\\.com 抓出公网地址。

这里在此基础上加了：状态机、自动重连、日志回调、外置/内嵌两种查找方式。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable

URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
ERR_RE = re.compile(r"(ERR|error|failed|unable to)[^\n]{0,160}", re.IGNORECASE)

STATE_IDLE = "idle"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"


def _no_window() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def find_cloudflared() -> str | None:
    """按 内嵌 → exe 同级 → 同级 bin → 工程目录 → PATH 的顺序找 cloudflared。"""
    roots: list[str] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    # app/share/tunnel.py → 工程根
    roots.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    roots.append(os.getcwd())

    names = ["cloudflared.exe", "cloudflared"]
    seen = set()
    for root in roots:
        for sub in ("", "bin", os.path.join("bin", "cloudflared"), "vendor"):
            folder = os.path.join(root, sub) if sub else root
            key = os.path.normcase(os.path.abspath(folder))
            if key in seen:
                continue
            seen.add(key)
            for name in names:
                candidate = os.path.join(folder, name)
                if os.path.isfile(candidate):
                    return candidate
    return shutil.which("cloudflared")


class Tunnel:
    """一条 quick tunnel。"""

    def __init__(self,
                 on_state: Callable[[str, str], None] | None = None,
                 on_url: Callable[[str], None] | None = None,
                 on_log: Callable[[str], None] | None = None) -> None:
        self.on_state = on_state
        self.on_url = on_url
        self.on_log = on_log
        self.state = STATE_IDLE
        self.message = "未启动"
        self.url = ""
        self.exe = find_cloudflared()
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.RLock()
        self._want_run = False
        self._target = ""
        self._restarts = 0
        self.started_at = 0.0

    # ---------------- 状态 ----------------
    def _set_state(self, state: str, message: str) -> None:
        self.state = state
        self.message = message
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

    @property
    def available(self) -> bool:
        return bool(self.exe and os.path.isfile(self.exe))

    # ---------------- 启动 / 停止 ----------------
    def start(self, local_url: str) -> bool:
        with self._lock:
            if not self.available:
                self._set_state(STATE_ERROR,
                                "找不到 cloudflared.exe，请把它放在程序同目录")
                return False
            if self._proc and self._proc.poll() is None:
                return True
            self._target = local_url
            self._want_run = True
            self._restarts = 0
            return self._spawn()

    def _spawn(self) -> bool:
        if not self._want_run:
            return False
        try:
            args = [self.exe, "tunnel", "--url", self._target, "--no-autoupdate"]
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_no_window(),
                cwd=os.path.dirname(self.exe) or None,
            )
        except Exception as exc:
            self._set_state(STATE_ERROR, f"启动 cloudflared 失败：{exc}")
            return False

        self.started_at = time.time()
        self.url = ""
        self._set_state(STATE_STARTING, "正在建立隧道…")
        self._log(f"tunnel process started pid={self._proc.pid}")
        self._reader = threading.Thread(target=self._read_loop, name="tunnel-read",
                                        daemon=True)
        self._reader.start()
        return True

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        last_url = ""
        try:
            for raw in proc.stdout:
                line = (raw or "").rstrip()
                if not line:
                    continue
                self._log(line[:400])
                match = URL_RE.search(line)
                if match and match.group() != last_url:
                    last_url = match.group()
                    self.url = last_url
                    self._set_state(STATE_RUNNING, last_url)
                    if self.on_url:
                        try:
                            self.on_url(last_url)
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            code = None
            try:
                code = proc.poll()
            except Exception:
                pass
            with self._lock:
                if self._want_run and not self.url:
                    self._set_state(STATE_ERROR,
                                    f"隧道退出（code={code}），可能是网络受限")
                elif self._want_run:
                    self._set_state(STATE_STOPPED, "隧道已断开")
                else:
                    self._set_state(STATE_STOPPED, "已停止")
            if self._want_run:
                self._auto_restart()

    def _auto_restart(self) -> None:
        if not self._want_run:
            return
        if self._restarts >= 5:
            self._set_state(STATE_ERROR, "隧道多次重连失败，可改用局域网模式")
            return
        self._restarts += 1
        delay = min(3 * self._restarts, 15)
        self._set_state(STATE_STARTING, f"{delay} 秒后自动重连（第 {self._restarts} 次）")

        def worker():
            for _ in range(delay * 2):
                time.sleep(0.5)
                if not self._want_run:
                    return
            with self._lock:
                if self._want_run:
                    self._spawn()

        threading.Thread(target=worker, name="tunnel-restart", daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._want_run = False
            proc = self._proc
            self._proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.url = ""
        self._set_state(STATE_STOPPED, "已停止")

    @property
    def running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)
