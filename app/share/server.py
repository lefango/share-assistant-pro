# -*- coding: utf-8 -*-
"""分享 HTTP 服务。

只监听 127.0.0.1（局域网模式才监听 0.0.0.0），公网访问一律由 cloudflared 隧道转发。

路由：
    GET  /                     网页首页（内嵌 web/index.html）
    GET  /static/<file>        内嵌静态资源
    GET  /api/meta             分享元信息（标题、是否要密码、剩余时间、是否可上传）
    POST /api/login            校验访问密码，签发签名 Cookie
    GET  /api/tree?path=<rel>  目录树 JSON
    GET  /api/upload-target    上传落点信息
    POST /api/upload           接收上传（原始 body + X-File-Name 头）
    GET  /f/<rel>              文件读取/下载（支持 Range 断点续传）
    GET  /zip?path=<rel>       文件夹流式打包下载
    GET  /thumb/<rel>          图片缩略图
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import mimetypes
import os
import posixpath
import re
import secrets
import socket
import tempfile
import threading
import time
import urllib.parse
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .options import ShareOptions
from .stats import Stats
from .upload_api import UploadAPI

try:  # 皮肤注入：网页和桌面界面共用同一套配色
    from .. import skin as _skin
except ImportError:  # pragma: no cover
    _skin = None

try:
    from ..uploads import ChunkStore, UploadQuota
except ImportError:  # pragma: no cover
    ChunkStore = UploadQuota = None

WEB_DIR_CANDIDATES = ("web",)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".avif", ".heic"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
TEXT_EXT = {".txt", ".md", ".log", ".json", ".xml", ".yml", ".yaml", ".ini", ".csv",
            ".py", ".js", ".ts", ".css", ".html", ".htm", ".c", ".cpp", ".h", ".java",
            ".go", ".rs", ".php", ".rb", ".sh", ".bat", ".ps1", ".sql"}

# 已经是压缩格式的文件：打包时直接「存储」即可，再做 DEFLATE 纯属白烧 CPU
# （而且对某些已压缩数据反而会把体积压大）
STORE_EXT = {
    # 压缩包 / 安装包
    ".zip", ".rar", ".7z", ".gz", ".bz2", ".xz", ".lz", ".lzma", ".zst", ".cab",
    ".apk", ".jar", ".ipa", ".aab", ".xapk", ".war",
    # 图片
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic", ".heif", ".jxl",
    # 视频 / 音频
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts", ".flv", ".wmv",
    ".mp3", ".aac", ".ogg", ".opus", ".m4a", ".flac", ".wma", ".ape",
    # 其它已是容器/压缩态的
    ".exe", ".dll", ".msi", ".iso", ".dmg", ".img", ".vmdk", ".pt", ".onnx",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".epub", ".pdf",
}

# 单个上传文件上限（4 GB）
MAX_UPLOAD = 4 * 1024 ** 3

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext == ".pdf":
        return "pdf"
    if ext in TEXT_EXT:
        return "text"
    return "file"


def human_size(num: float) -> str:
    if num < 1024:
        return f"{int(num)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num /= 1024.0
        if num < 1024:
            return f"{num:.1f} {unit}"
    return f"{num:.1f} PB"


def content_disposition(filename: str) -> str:
    """中文文件名安全：ASCII 兜底 + RFC 5987。"""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "download"
    ascii_name = ascii_name.replace('"', "_").replace("\\", "_") or "download"
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


class _StreamWriter:
    """给 zipfile 用的、不可 seek 的输出流（触发 data descriptor，可边压边发）。"""

    def __init__(self, sink: Callable[[bytes], None]) -> None:
        self._sink = sink
        self.bytes = 0

    def write(self, data) -> int:
        if data:
            self._sink(bytes(data))
            self.bytes += len(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _ShareHTTPServer(ThreadingHTTPServer):
    """客户端提前断开（浏览器取消下载、隧道回收连接）是常态，不要刷屏报错。"""

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class ShareServer:
    """一次分享会话对应的本地 HTTP 服务。"""

    def __init__(self, options: ShareOptions, stats: Stats, web_dir: str,
                 on_event: Callable[[str, str], None] | None = None,
                 theme: dict | None = None) -> None:
        self.options = options.normalized()
        self.stats = stats
        self.web_dir = web_dir
        self.on_event = on_event
        self.theme = theme or {}
        # 分享来源（可能多个）。只有一个来源时不加虚拟层级，保持原来的浏览体验。
        self.mounts: list[tuple[str, str]] = [
            (name, os.path.abspath(path)) for name, path in (self.options.sources or [])
        ]
        if not self.mounts:
            root = os.path.abspath(self.options.root)
            self.mounts = [(os.path.basename(root.rstrip("\\/")) or "文件库", root)]
        self.single = len(self.mounts) == 1
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.secret = secrets.token_bytes(32)
        self.token = self.options.token or secrets.token_urlsafe(12)
        self.options.token = self.token
        self.bind_host = "127.0.0.1"
        self.port = 0
        self.started_at = time.time()
        self._thumbs: dict[str, bytes] = {}
        self._thumb_lock = threading.Lock()
        # 分片接收 + 本次接收总量配额
        self.quota = UploadQuota(self.options.receive_limit) if UploadQuota else None
        self.chunks = (ChunkStore(os.path.join(tempfile.gettempdir(), "sharemate-chunks"))
                       if ChunkStore else None)
        self.upload_api = (UploadAPI(self.quota, self.chunks, self.options.upload_dir)
                           if self.quota and self.chunks else None)

    # ---------------- 生命周期 ----------------
    def start(self, lan: bool = False) -> tuple[str, int]:
        self.bind_host = "0.0.0.0" if lan else "127.0.0.1"
        handler = _make_handler(self)
        self._httpd = _ShareHTTPServer((self.bind_host, 0), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="share-http", daemon=True)
        self._thread.start()
        self._emit("info", f"本地服务已启动 {self.bind_host}:{self.port}")
        return self.bind_host, self.port

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        self.stats.save()

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def lan_ip(self) -> str:
        """猜一个本机在局域网里的地址。"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _emit(self, level: str, message: str) -> None:
        if self.on_event:
            try:
                self.on_event(level, message)
            except Exception:
                pass

    # ---------------- URL / 路径 ----------------
    @staticmethod
    def quote_path(rel: str) -> str:
        return "/".join(urllib.parse.quote(part) for part in rel.replace("\\", "/").split("/") if part)

    def url_for(self, rel: str) -> str:
        """文件访问 URL —— 必须带 /f/ 前缀，否则会被当成其它路由。"""
        return "/f/" + self.quote_path(rel)

    def safe_rel(self, raw: str) -> str | None:
        """把请求里的相对路径规范化，越界返回 None。"""
        try:
            raw = urllib.parse.unquote(raw or "")
        except Exception:
            return None
        raw = raw.replace("\\", "/")
        if "\x00" in raw:
            return None
        raw = posixpath.normpath(raw)
        if raw in (".", "/", ""):
            return ""
        raw = raw.lstrip("/")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            return None
        return "/".join(parts)

    def expand(self, rel: str) -> tuple[str, str] | None:
        """虚拟相对路径 → (来源根目录, 该来源内的相对路径)。

        只挂一个来源时，虚拟路径就是来源内的相对路径（没有多余层级）。
        挂了多个来源时，第一段是来源名。
        虚拟根（多来源时的 ""）不是一个真实目录，返回 None。
        """
        rel = (rel or "").strip("/")
        if self.single:
            return self.mounts[0][1], rel
        if not rel:
            return None
        head, _, tail = rel.partition("/")
        for name, base in self.mounts:
            if name == head:
                return base, tail
        return None

    def virtual_of(self, abs_path: str) -> str:
        """真实路径 → 虚拟相对路径（用于拼缩略图/下载链接）。"""
        abs_path = os.path.abspath(abs_path)
        for name, base in self.mounts:
            try:
                if os.path.commonpath([base, abs_path]) == base:
                    rel = os.path.relpath(abs_path, base).replace(os.sep, "/")
                    if rel == ".":
                        rel = ""
                    return f"{name}/{rel}" if (not self.single and rel) else rel
            except ValueError:
                continue
        return ""

    def resolve(self, rel: str, base: str | None = None) -> str | None:
        """虚拟相对路径 → 真实路径，并确保仍在该来源目录之内。"""
        if base is not None:
            root = os.path.abspath(base)
            target_rel = (rel or "").replace("\\", "/")
        else:
            expanded = self.expand(rel)
            if expanded is None:
                return None
            root, target_rel = expanded
            root = os.path.abspath(root)
        target = os.path.abspath(os.path.join(root, target_rel.replace("/", os.sep)))
        try:
            if os.path.commonpath([root, target]) != root:
                return None
        except ValueError:
            return None
        return target

    # ---------------- 目录数据 ----------------
    def scan(self, rel: str) -> dict:
        """列出某个目录（虚拟相对路径）的内容。"""
        rel = (rel or "").strip("/")

        # 多个来源时，虚拟根上先列出这些来源
        if not self.single and rel == "":
            dirs = []
            for name, base in self.mounts:
                stats = self.dir_stats(name)
                dirs.append({
                    "name": name,
                    "path": name,
                    "url": self.url_for(name),
                    "mtime": int(os.path.getmtime(base)) if os.path.isdir(base) else 0,
                    **stats,
                })
            return {"ok": True, "path": "", "dirs": dirs, "files": [],
                    "multi_source": True}

        abs_dir = self.resolve(rel)
        if abs_dir is None or not os.path.isdir(abs_dir):
            return {"ok": False, "error": "目录不存在"}
        dirs, files = [], []
        try:
            with os.scandir(abs_dir) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith(".") or name.startswith("~$"):
                        continue
                    try:
                        st = entry.stat()
                    except Exception:
                        continue
                    child_rel = f"{rel}/{name}" if rel else name
                    if entry.is_dir():
                        dirs.append({
                            "name": name,
                            "path": child_rel,
                            "url": self.url_for(child_rel),
                            "mtime": int(st.st_mtime),
                        })
                    else:
                        kind = kind_of(name)
                        files.append({
                            "name": name,
                            "path": child_rel,
                            "url": self.url_for(child_rel),
                            "size": st.st_size,
                            "size_text": human_size(st.st_size),
                            "mtime": int(st.st_mtime),
                            "kind": kind,
                            "thumb": f"/thumb/{self.quote_path(child_rel)}" if kind == "image" else "",
                        })
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        dirs.sort(key=lambda d: d["name"].lower())
        files.sort(key=lambda f: ((0 if f["kind"] in ("image", "video") else 1), f["name"].lower()))
        return {"ok": True, "path": rel, "dirs": dirs, "files": files}

    def dir_stats(self, virtual_rel: str, depth: int = 2, max_entries: int = 4000) -> dict:
        """给文件夹卡片算缩略图、数量与体积。

        max_entries 是个保险：超大目录不至于把 HTTP 请求拖死。
        """
        abs_dir = self.resolve(virtual_rel)
        if abs_dir is None or not os.path.isdir(abs_dir):
            return {"count": 0, "size": 0, "size_text": human_size(0),
                    "images": [], "videos": []}
        images: list[str] = []
        videos: list[str] = []
        count = 0
        size = 0
        scanned = 0
        enough_media = False
        queue = [(abs_dir, 0)]
        while queue and scanned < max_entries:
            cur, level = queue.pop(0)
            try:
                with os.scandir(cur) as it:
                    for entry in it:
                        if entry.name.startswith("."):
                            continue
                        scanned += 1
                        if entry.is_dir():
                            count += 1
                            if level < depth:
                                queue.append((entry.path, level + 1))
                        else:
                            count += 1
                            try:
                                size += entry.stat().st_size
                            except Exception:
                                pass
                            if not enough_media:
                                kind = kind_of(entry.name)
                                rel = self.virtual_of(entry.path)
                                if kind == "image" and len(images) < 4:
                                    images.append(f"/thumb/{self.quote_path(rel)}")
                                elif kind == "video" and len(videos) < 1:
                                    videos.append(self.url_for(rel))
                                if len(images) >= 4 and len(videos) >= 1:
                                    enough_media = True
                        if scanned >= max_entries:
                            break
            except Exception:
                continue
        return {"count": count, "size": size, "size_text": human_size(size),
                "images": images, "videos": videos}

    # ---------------- 缩略图 ----------------
    def thumbnail(self, abs_path: str) -> bytes | None:
        key = f"{abs_path}|{os.path.getmtime(abs_path) if os.path.exists(abs_path) else 0}"
        with self._thumb_lock:
            hit = self._thumbs.get(key)
        if hit:
            return hit
        try:
            from PIL import Image, ImageOps

            with Image.open(abs_path) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((480, 480))
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=78, optimize=True)
            data = buf.getvalue()
            with self._thumb_lock:
                if len(self._thumbs) > 600:
                    self._thumbs.clear()
                self._thumbs[key] = data
            return data
        except Exception:
            return None


# ====================================================================== 处理器

def _make_handler(server: ShareServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ShareMate/1.0"

        # ---------- 基础工具 ----------
        def log_message(self, fmt, *args):
            pass  # 静音默认访问日志

        @property
        def share(self) -> ShareServer:
            return server

        def client_ip(self) -> str:
            for header in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
                value = self.headers.get(header)
                if value:
                    return value.split(",")[0].strip()
            return self.client_address[0] if self.client_address else "-"

        def user_agent(self) -> str:
            return self.headers.get("User-Agent", "")

        def send_simple(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8",
                        extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD" and body:
                try:
                    self.wfile.write(body)
                except Exception:
                    pass

        def send_json(self, payload: dict, code: int = 200, extra: dict | None = None):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_simple(code, body, "application/json; charset=utf-8", extra)

        # ---------- 鉴权 ----------
        def _cookie_token(self) -> str:
            raw = self.headers.get("Cookie", "")
            for part in raw.split(";"):
                key, _, value = part.strip().partition("=")
                if key == "sm_auth":
                    return value
            return ""

        def authorized(self) -> bool:
            if not server.options.password:
                return True
            expect = hmac.new(server.secret, server.token.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(self._cookie_token(), expect)

        def require_auth(self) -> bool:
            if self.authorized():
                return True
            self.send_json({"ok": False, "need_password": True, "error": "需要访问密码"}, 401)
            return False

        def expired(self) -> bool:
            if server.options.expired():
                self.send_json({"ok": False, "expired": True, "error": "分享已到期"}, 410)
                return True
            return False

        # ---------- 路由 ----------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self._route_get()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as exc:
                try:
                    self.send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
                except Exception:
                    pass

        def do_POST(self):
            try:
                self._route_post()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as exc:
                try:
                    self.send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
                except Exception:
                    pass

        def _route_get(self):
            parsed = urllib.parse.urlsplit(self.path)
            route = parsed.path
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

            # 静态资源与首页不需要密码
            if route in ("/", "/index.html"):
                self.serve_web("index.html")
                server.stats.record_visit(self.client_ip(), self.user_agent())
                return
            if route in ("/receive", "/receive.html"):
                self.serve_web("receive.html")
                server.stats.record_visit(self.client_ip(), self.user_agent())
                return
            if route.startswith("/static/"):
                self.serve_web(route[len("/static/"):])
                return
            if route in ("/favicon.ico", "/manifest.json", "/sw.js", "/icon.svg"):
                self.serve_web(route.lstrip("/"))
                return

            # meta 永远可读：即使已过期，也要让网页能显示"这次分享已结束"
            if route == "/api/meta":
                self.api_meta()
                return

            if self.expired():
                return

            if not self.require_auth():
                server.stats.record_block("auth", self.client_ip(), self.user_agent())
                return

            if route == "/api/tree":
                self.api_tree(query)
            elif route == "/zip":
                self.send_zip(query)
            elif route.startswith("/thumb/"):
                self.send_thumb(route[len("/thumb/"):])
            elif route.startswith("/f/"):
                self.send_file(route[len("/f/"):], download="dl" in query)
            elif route in ("/icon.svg",):
                self.serve_web("icon.svg")
            else:
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")

        def _reject_post(self, payload: dict, code: int) -> None:
            """拒绝一个带 body 的请求时，必须把连接标成短连接。

            我们没读完请求体，keep-alive 复用这条连接会把剩下的 body 当成
            下一个请求，导致串包。直接关闭最稳。
            """
            self.close_connection = True
            self.send_json(payload, code, extra={"Connection": "close"})

        def _route_post(self):
            parsed = urllib.parse.urlsplit(self.path)
            route = parsed.path
            if route == "/api/login":
                self.api_login()
                return
            if self.expired():
                self._reject_post({"ok": False, "expired": True, "error": "分享已到期"}, 410)
                return
            if not self.authorized():
                server.stats.record_block("auth", self.client_ip(), self.user_agent())
                self._reject_post(
                    {"ok": False, "need_password": True, "error": "需要访问密码"}, 401)
                return
            if route == "/api/upload":
                self.api_upload()
            elif route == "/api/upload/begin":
                self.api_chunk_begin()
            elif route == "/api/upload/chunk":
                self.api_chunk_put()
            elif route == "/api/upload/finish":
                self.api_chunk_finish()
            else:
                self.close_connection = True
                self.send_simple(HTTPStatus.NOT_FOUND, b"404", extra={"Connection": "close"})

        # ---------- 静态网页 ----------
        def serve_web(self, name: str):
            name = name.split("?")[0].lstrip("/")
            if not name or ".." in name or "\\" in name:
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return
            path = os.path.join(server.web_dir, name.replace("/", os.sep))
            if not os.path.isfile(path):
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            if path.lower().endswith((".html", ".htm")):
                # 网页也要跟着皮肤变：读出来注入配色再发
                try:
                    with open(path, "rb") as fh:
                        text = fh.read().decode("utf-8", "replace")
                except OSError:
                    self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                    return
                if _skin is not None and server.theme:
                    try:
                        text = _skin.inject(text, server.theme)
                    except Exception:
                        pass
                self.send_simple(200, text.encode("utf-8"), ctype)
                return
            try:
                size = os.path.getsize(path)
            except OSError:
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        # ---------- API ----------
        def api_meta(self):
            opts = server.options
            payload = {
                "ok": True,
                "title": opts.title,
                "need_password": bool(opts.password),
                "authed": self.authorized(),
                "allow_upload": bool(opts.allow_upload),
                "allow_download": bool(opts.allow_download),
                "receive": (server.upload_api.status() if server.upload_api else {}),
                "chunk_size": (96 * 1024 * 1024),
                "expires_in": opts.remaining,
                "note": opts.readonly_note,
                "root_name": os.path.basename(opts.root.rstrip("\\/")) or opts.root,
                "sources": [{"name": name, "path": name if not server.single else ""}
                            for name, _base in server.mounts],
                "multi_source": not server.single,
            }
            extra = {}
            if opts.password and self.authorized():
                expect = hmac.new(server.secret, server.token.encode(), hashlib.sha256).hexdigest()
                extra["Set-Cookie"] = f"sm_auth={expect}; Path=/; HttpOnly; SameSite=Lax"
            self.send_json(payload, extra=extra)

        def api_login(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(length, 4096))
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except Exception:
                data = {}
            given = str(data.get("password") or "")
            expect = server.options.password
            if not expect or hmac.compare_digest(given, expect):
                value = hmac.new(server.secret, server.token.encode(), hashlib.sha256).hexdigest()
                self.send_json({"ok": True}, extra={
                    "Set-Cookie": f"sm_auth={value}; Path=/; HttpOnly; SameSite=Lax",
                })
                server.stats.record_open("登录成功", self.client_ip(), self.user_agent())
            else:
                server.stats.record_block("bad-password", self.client_ip(), self.user_agent())
                self.send_json({"ok": False, "error": "密码不正确"}, 403)

        def api_tree(self, query):
            rel = server.safe_rel((query.get("path") or [""])[0])
            if rel is None:
                server.stats.record_block("traversal", self.client_ip(), self.user_agent())
                self.send_json({"ok": False, "error": "非法路径"}, 400)
                return
            data = server.scan(rel)
            if not data.get("ok"):
                self.send_json(data, 404)
                return

            # 每一级都补上缩略图与统计，卡片墙才好看（根目录多下一层）
            for info in data["dirs"]:
                info.update(server.dir_stats(info["path"],
                                            depth=2 if rel == "" else 1))
                info["url"] = server.url_for(info["path"])

            if rel == "":
                # 根目录再给一份总量，网页顶部的 Hero 要用
                dirs_size = sum(d.get("size", 0) for d in data["dirs"])
                dirs_count = sum(d.get("count", 0) for d in data["dirs"])
                files_size = sum(f["size"] for f in data["files"])
                total_size = dirs_size + files_size
                data["total"] = {
                    "dirs": len(data["dirs"]),
                    "files": dirs_count + len(data["files"]),
                    "size": total_size,
                    "size_text": human_size(total_size),
                }
            data["crumbs"] = self._crumbs(rel)
            data["allow_upload"] = bool(server.options.allow_upload)
            self.send_json(data)

        def _crumbs(self, rel: str) -> list:
            crumbs = [{"name": "根目录", "path": ""}]
            if rel:
                acc = ""
                for seg in rel.split("/"):
                    acc = f"{acc}/{seg}" if acc else seg
                    crumbs.append({"name": seg, "path": acc})
            return crumbs

        # ---------- 文件 ----------
        def send_thumb(self, raw_rel: str):
            rel = server.safe_rel(raw_rel)
            if rel is None:
                self.send_json({"ok": False, "error": "非法路径"}, 400)
                return
            abs_path = server.resolve(rel)
            if abs_path is None or not os.path.isfile(abs_path):
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return
            data = server.thumbnail(abs_path)
            if data is None:
                # 生成失败就退回原图
                self.send_file(raw_rel, download=False)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=600")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def send_file(self, raw_rel: str, download: bool = False):
            rel = server.safe_rel(raw_rel)
            if rel is None or rel == "":
                server.stats.record_block("traversal", self.client_ip(), self.user_agent())
                self.send_simple(HTTPStatus.BAD_REQUEST, b"bad path")
                return
            abs_path = server.resolve(rel)
            if abs_path is None or not os.path.isfile(abs_path):
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return
            if download and not server.options.allow_download:
                self.send_json({"ok": False, "error": "此分享不允许下载"}, 403)
                return

            try:
                size = os.path.getsize(abs_path)
            except OSError:
                self.send_simple(HTTPStatus.NOT_FOUND, b"404")
                return

            ctype = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
            if ctype.startswith("text/") and "charset" not in ctype:
                ctype += "; charset=utf-8"

            start, end = 0, size - 1
            status = 200
            range_header = self.headers.get("Range", "")
            if range_header:
                match = RANGE_RE.match(range_header.strip())
                if match:
                    g1, g2 = match.group(1), match.group(2)
                    if g1 == "" and g2:
                        start = max(0, size - int(g2))
                    elif g1:
                        start = int(g1)
                        if g2:
                            end = min(int(g2), size - 1)
                    if start > end or start >= size:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206

            length = max(0, end - start + 1)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, max-age=300")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if download:
                self.send_header("Content-Disposition",
                                 content_disposition(os.path.basename(abs_path)))
            self.end_headers()

            if download:
                server.stats.record_download(rel, self.client_ip(), self.user_agent(), "file")
            if self.command == "HEAD":
                return

            remaining = length
            with open(abs_path, "rb") as fh:
                fh.seek(start)
                while remaining > 0:
                    chunk = fh.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        # ---------- 打包 ----------
        def send_zip(self, query):
            rel = server.safe_rel((query.get("path") or [""])[0])
            if rel is None:
                self.send_json({"ok": False, "error": "非法路径"}, 400)
                return
            abs_dir = server.resolve(rel)
            if abs_dir is None or not os.path.isdir(abs_dir):
                self.send_json({"ok": False, "error": "目录不存在"}, 404)
                return

            base_name = os.path.basename(abs_dir) or server.options.title
            if self.headers.get("X-Probe") == "1":
                self.send_json({"ok": True, "count": self._count_tree(abs_dir)})
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", content_disposition(f"{base_name}.zip"))
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            server.stats.record_download(rel, self.client_ip(), self.user_agent(), "zip")

            written = {"n": 0}

            def sink(data: bytes) -> None:
                self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
                written["n"] += len(data)

            try:
                writer = _StreamWriter(sink)
                with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                    for cur, dirs, names in os.walk(abs_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        for name in names:
                            if name.startswith("."):
                                continue
                            full = os.path.join(cur, name)
                            arc = os.path.relpath(full, abs_dir).replace(os.sep, "/")
                            ext = os.path.splitext(name)[1].lower()
                            method = (zipfile.ZIP_STORED if ext in STORE_EXT
                                      else zipfile.ZIP_DEFLATED)
                            try:
                                zf.write(full, arc, compress_type=method)
                            except Exception:
                                continue
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                try:
                    self.wfile.write(b"0\r\n\r\n")
                except Exception:
                    pass

        def _count_tree(self, abs_dir: str) -> int:
            total = 0
            for _cur, dirs, names in os.walk(abs_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                total += sum(1 for n in names if not n.startswith("."))
            return total

        # ---------- 上传 ----------
        def _read_json(self, limit: int = 16384) -> dict:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except Exception:
                length = 0
            if length <= 0:
                return {}
            try:
                body = self.rfile.read(min(length, limit))
                data = json.loads(body.decode("utf-8") or "{}")
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        def upload_ready(self) -> bool:
            if not server.options.allow_upload:
                self._reject_post({"ok": False, "error": "此分享未开启接收"}, 403)
                return False
            if server.upload_api is None:
                self._reject_post({"ok": False, "error": "分片模块不可用"}, 501)
                return False
            return True

        def api_chunk_begin(self):
            if not self.upload_ready():
                return
            data = self._read_json()
            try:
                total = int(data.get("total") or 0)
            except Exception:
                total = 0
            result = server.upload_api.begin(str(data.get("name") or ""), total)
            if result.get("ok"):
                self.send_json(result)
            else:
                code = 413 if "remaining" in result else 400
                self.send_json(result, code)

        def api_chunk_put(self):
            if not self.upload_ready():
                return
            upload_id = self.headers.get("X-Upload-Id", "")
            try:
                index = int(self.headers.get("X-Chunk-Index", "-1"))
            except Exception:
                index = -1
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except Exception:
                length = 0
            if length <= 0 or length > 96 * 1024 * 1024:
                self._reject_post({"ok": False, "error": "分片大小不合法"}, 413)
                return
            data = self.rfile.read(length)
            result = server.upload_api.put(upload_id, index, data)
            self.send_json(result, 200 if result.get("ok") else 400)

        def api_chunk_finish(self):
            if not self.upload_ready():
                return
            data = self._read_json()
            result = server.upload_api.finish(str(data.get("upload_id") or ""))
            if result.get("ok"):
                server.stats.record_upload(str(result.get("name") or ""),
                                           int(result.get("size") or 0),
                                           self.client_ip(), self.user_agent())
                self.send_json(result)
            else:
                self.send_json(result, 400)

        def api_upload(self):
            if not server.options.allow_upload:
                self._reject_post({"ok": False, "error": "此分享未开启上传"}, 403)
                return
            raw_name = self.headers.get("X-File-Name", "")
            try:
                name = urllib.parse.unquote(raw_name)
            except Exception:
                name = raw_name
            if not name:
                self._reject_post({"ok": False, "error": "缺少文件名"}, 400)
                return

            from ..library import sanitize_name, unique_path
            from pathlib import Path

            safe = sanitize_name(os.path.basename(name))
            dest_dir = server.options.upload_dir
            os.makedirs(dest_dir, exist_ok=True)
            target = unique_path(Path(dest_dir) / safe)

            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                self.send_json({"ok": False, "error": "空文件"}, 400)
                return
            if length > MAX_UPLOAD:
                self._reject_post(
                    {"ok": False,
                     "error": f"单个文件超过 {MAX_UPLOAD // 1024 ** 3} GB 上限"},
                    413)
                return
            if server.quota is not None and not server.quota.accept(length):
                self._reject_post({"ok": False, "error": "超过本次接收总量",
                                   "remaining": server.quota.remaining()}, 413)
                return

            written = 0
            try:
                with open(target, "wb") as fh:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(512 * 1024, remaining))
                        if not chunk:
                            break
                        fh.write(chunk)
                        remaining -= len(chunk)
                        written += len(chunk)
            except Exception as exc:
                try:
                    os.remove(target)
                except Exception:
                    pass
                self.send_json({"ok": False, "error": f"写入失败：{exc}"}, 500)
                return

            server.stats.record_upload(safe, written, self.client_ip(), self.user_agent())
            if server.quota is not None:
                server.quota.add(written)
            self.send_json({"ok": True, "name": target.name, "size": written,
                            "size_text": human_size(written)})

    return Handler


def start_server(root: str, stats: Stats, web_dir: str, *, title: str = "我的分享",
                 password: str = "", ttl_seconds: int = 0, allow_upload: bool = False,
                 upload_dir: str = "", allow_download: bool = True,
                 lan: bool = False,
                 on_event: Callable[[str, str], None] | None = None) -> ShareServer:
    options = ShareOptions(root=root, title=title, password=password, ttl_seconds=ttl_seconds,
                           allow_upload=allow_upload, upload_dir=upload_dir,
                           allow_download=allow_download)
    server = ShareServer(options, stats, web_dir, on_event)
    server.start(lan=lan)
    return server
