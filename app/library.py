# -*- coding: utf-8 -*-
"""文件库核心逻辑。

目录约定：
    根目录/                        <- 文件库根
        ├── 分组A/                 <- 每个分组拥有自己的子文件夹
        │     ├── 子文件夹1/       <- 分组内创建的文件夹，落在分组自己的子文件夹里
        │     └── 子文件夹2/
        └── 分组B/
"""
from __future__ import annotations

import ctypes
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

# ---------------------------------------------------------------- 分类表

CATEGORIES: dict[str, str] = {
    # 图片
    ".jpg": "图片", ".jpeg": "图片", ".png": "图片", ".gif": "图片", ".bmp": "图片",
    ".webp": "图片", ".tif": "图片", ".tiff": "图片", ".svg": "图片", ".ico": "图片",
    ".heic": "图片", ".raw": "图片", ".psd": "图片", ".ai": "图片",
    # 视频
    ".mp4": "视频", ".mkv": "视频", ".avi": "视频", ".mov": "视频", ".wmv": "视频",
    ".flv": "视频", ".webm": "视频", ".m4v": "视频", ".mpg": "视频", ".mpeg": "视频",
    ".m2ts": "视频", ".mts": "视频", ".rmvb": "视频",
    # 音频
    ".mp3": "音频", ".wav": "音频", ".flac": "音频", ".aac": "音频", ".ogg": "音频",
    ".m4a": "音频", ".wma": "音频", ".ape": "音频", ".mid": "音频",
    # 文档
    ".pdf": "文档", ".doc": "文档", ".docx": "文档", ".xls": "文档", ".xlsx": "文档",
    ".ppt": "文档", ".pptx": "文档", ".txt": "文档", ".md": "文档", ".rtf": "文档",
    ".csv": "文档", ".epub": "文档", ".mobi": "文档", ".odt": "文档", ".wps": "文档",
    # 压缩包
    ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包", ".tar": "压缩包",
    ".gz": "压缩包", ".bz2": "压缩包", ".xz": "压缩包", ".iso": "压缩包",
    # 程序与安装包
    ".exe": "程序", ".msi": "程序", ".apk": "程序", ".dmg": "程序", ".deb": "程序",
    ".rpm": "程序", ".bat": "程序", ".cmd": "程序", ".ps1": "程序", ".sh": "程序",
    # 代码
    ".py": "代码", ".js": "代码", ".ts": "代码", ".java": "代码", ".c": "代码",
    ".cpp": "代码", ".h": "代码", ".cs": "代码", ".go": "代码", ".rs": "代码",
    ".php": "代码", ".rb": "代码", ".html": "代码", ".css": "代码", ".json": "代码",
    ".xml": "代码", ".yml": "代码", ".yaml": "代码", ".sql": "代码",
    ".torrent": "其他", ".ini": "其他", ".lnk": "其他",
}

DEFAULT_CATEGORY = "其他"

# 分类固定顺序（自动归类时按此顺序建目录）
CATEGORY_ORDER = ["图片", "视频", "音频", "文档", "压缩包", "程序", "代码", "其他"]

CATEGORY_COLOR: dict[str, str] = {
    "图片": "#4f8cff",
    "视频": "#f97362",
    "音频": "#a78bfa",
    "文档": "#3ecf8e",
    "压缩包": "#ffb454",
    "程序": "#22d3ee",
    "代码": "#e879f9",
    "其他": "#8b96a8",
}

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_CHARS = '<>:"/\\|?*'
_UNSAFE_TAIL = " ."


# ---------------------------------------------------------------- 工具

def sanitize_name(name: str) -> str:
    """把用户输入清洗成合法的目录/文件名。"""
    name = (name or "").strip()
    name = "".join("_" if ch in _INVALID_CHARS or ord(ch) < 32 else ch for ch in name)
    name = name.rstrip(_UNSAFE_TAIL).lstrip(" ")
    if not name:
        name = "新建文件夹"
    if name.upper() in _WIN_RESERVED:
        name = "_" + name
    if len(name) > 120:
        name = name[:120].rstrip(_UNSAFE_TAIL)
    return name


def long_path(path: str | os.PathLike) -> str:
    """超长路径加 \\\\?\\ 前缀，避免 Windows 260 字符限制。"""
    p = os.path.abspath(str(path))
    if os.name != "nt":
        return p
    if p.startswith("\\\\?\\"):
        return p
    if len(p) < 240:
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def unique_path(target: Path) -> Path:
    """目标已存在时自动追加 (1)、(2)……"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(1, 10000):
        candidate = target.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
    return target.with_name(f"{stem}_{int(time.time())}{suffix}")


def human_size(num: float) -> str:
    if num < 1024:
        return f"{int(num)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num /= 1024.0
        if num < 1024:
            return f"{num:.1f} {unit}" if num < 100 else f"{num:.0f} {unit}"
    return f"{num:.1f} PB"


def human_time(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "-"


def classify(filename: str) -> str:
    return CATEGORIES.get(Path(filename).suffix.lower(), DEFAULT_CATEGORY)


def is_hidden(name: str) -> bool:
    return name.startswith(".") or name.startswith("~$")


def recycle(paths: Sequence[str]) -> bool:
    """送进 Windows 回收站；失败返回 False 由上层决定是否硬删。"""
    if os.name != "nt" or not paths:
        return False

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    try:
        buf = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = buf
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return result == 0
    except Exception:
        return False


# ---------------------------------------------------------------- 数据模型

@dataclass
class FolderInfo:
    name: str
    path: str
    files: int = 0
    subdirs: int = 0
    size: int = 0
    mtime: float = 0.0
    is_root: bool = False

    @property
    def size_text(self) -> str:
        return human_size(self.size)


@dataclass
class FileInfo:
    name: str
    path: str
    size: int
    mtime: float
    is_dir: bool = False

    @property
    def size_text(self) -> str:
        return "文件夹" if self.is_dir else human_size(self.size)


@dataclass
class PlaceResult:
    moved: list[tuple[str, str]] = field(default_factory=list)   # (src, dst)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (src, reason)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (src, reason)

    @property
    def total(self) -> int:
        return len(self.moved) + len(self.failed) + len(self.skipped)

    @property
    def ok_count(self) -> int:
        return len(self.moved)


# ---------------------------------------------------------------- 文件库

class Library:
    """对根目录下『分组 / 子文件夹 / 文件』的读写封装。除 place 外均为轻量操作。"""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(os.path.expanduser(root))

    # ---------- 根 ----------
    def ensure_root(self) -> str:
        os.makedirs(long_path(self.root), exist_ok=True)
        return self.root

    def group_dir(self, group: str) -> str:
        return os.path.join(self.root, group)

    def folder_dir(self, group: str, folder: str | None = None) -> str:
        base = self.group_dir(group)
        return os.path.join(base, folder) if folder else base

    # ---------- 分组 ----------
    def groups(self) -> list[str]:
        self.ensure_root()
        try:
            names = [
                e.name for e in os.scandir(long_path(self.root))
                if e.is_dir() and not is_hidden(e.name)
            ]
        except Exception:
            return []
        return sorted(names, key=lambda s: s.lower())

    def group_exists(self, name: str) -> bool:
        return os.path.isdir(long_path(self.group_dir(name)))

    def create_group(self, name: str) -> str:
        clean = sanitize_name(name)
        path = self.group_dir(clean)
        if os.path.isdir(long_path(path)):
            raise FileExistsError(f"分组『{clean}』已存在")
        os.makedirs(long_path(path), exist_ok=False)
        return path

    def rename_group(self, old: str, new: str) -> str:
        clean = sanitize_name(new)
        src, dst = self.group_dir(old), self.group_dir(clean)
        if not os.path.isdir(long_path(src)):
            raise FileNotFoundError(f"分组『{old}』不存在")
        if os.path.exists(long_path(dst)):
            raise FileExistsError(f"分组『{clean}』已存在")
        os.rename(long_path(src), long_path(dst))
        return dst

    def delete_group(self, name: str, hard: bool = False) -> bool:
        path = self.group_dir(name)
        if not os.path.exists(long_path(path)):
            return False
        if not hard and recycle([path]):
            return True
        shutil.rmtree(long_path(path), ignore_errors=True)
        return not os.path.exists(long_path(path))

    # ---------- 子文件夹 ----------
    def folders(self, group: str) -> list[FolderInfo]:
        base = self.group_dir(group)
        if not os.path.isdir(long_path(base)):
            return []
        result: list[FolderInfo] = []
        try:
            for entry in os.scandir(long_path(base)):
                if not entry.is_dir() or is_hidden(entry.name):
                    continue
                result.append(self._folder_info(entry.name, entry.path, is_root=False))
        except Exception:
            return []
        result.sort(key=lambda f: f.name.lower())
        return result

    def folder_exists(self, group: str, folder: str) -> bool:
        return os.path.isdir(long_path(self.folder_dir(group, folder)))

    def create_folder(self, group: str, name: str) -> str:
        """在分组自己的子文件夹里创建文件夹。"""
        clean = sanitize_name(name)
        if not self.group_exists(group):
            raise FileNotFoundError(f"分组『{group}』不存在")
        path = os.path.join(self.group_dir(group), clean)
        if os.path.isdir(long_path(path)):
            raise FileExistsError(f"文件夹『{clean}』已存在")
        os.makedirs(long_path(path), exist_ok=False)
        return path

    def rename_folder(self, group: str, old: str, new: str) -> str:
        clean = sanitize_name(new)
        src = self.folder_dir(group, old)
        dst = self.folder_dir(group, clean)
        if not os.path.isdir(long_path(src)):
            raise FileNotFoundError(f"文件夹『{old}』不存在")
        if os.path.exists(long_path(dst)):
            raise FileExistsError(f"文件夹『{clean}』已存在")
        os.rename(long_path(src), long_path(dst))
        return dst

    def delete_folder(self, group: str, folder: str, hard: bool = False) -> bool:
        path = self.folder_dir(group, folder)
        if not os.path.exists(long_path(path)):
            return False
        if not hard and recycle([path]):
            return True
        shutil.rmtree(long_path(path), ignore_errors=True)
        return not os.path.exists(long_path(path))

    def _folder_info(self, name: str, path: str, is_root: bool) -> FolderInfo:
        info = FolderInfo(name=name, path=path, is_root=is_root)
        try:
            info.mtime = os.path.getmtime(long_path(path))
            with os.scandir(long_path(path)) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            info.subdirs += 1
                        else:
                            info.files += 1
                            info.size += entry.stat().st_size
                    except Exception:
                        continue
        except Exception:
            pass
        return info

    def group_root_info(self, group: str) -> FolderInfo:
        """分组自身的子文件夹（组根目录）——只统计直属文件，不含子文件夹内文件。"""
        path = self.group_dir(group)
        return self._folder_info(group, path, is_root=True)

    # ---------- 文件 ----------
    def files(self, directory: str, recursive: bool = False) -> list[FileInfo]:
        if not os.path.isdir(long_path(directory)):
            return []
        out: list[FileInfo] = []
        try:
            if recursive:
                for cur, dirs, names in os.walk(long_path(directory)):
                    dirs[:] = [d for d in dirs if not is_hidden(d)]
                    for n in names:
                        if is_hidden(n):
                            continue
                        p = os.path.join(cur, n)
                        try:
                            st = os.stat(p)
                            out.append(FileInfo(n, p, st.st_size, st.st_mtime))
                        except Exception:
                            continue
            else:
                for entry in os.scandir(long_path(directory)):
                    if is_hidden(entry.name):
                        continue
                    try:
                        if entry.is_dir():
                            out.append(FileInfo(entry.name, entry.path, 0, entry.stat().st_mtime, True))
                        else:
                            st = entry.stat()
                            out.append(FileInfo(entry.name, entry.path, st.st_size, st.st_mtime, False))
                    except Exception:
                        continue
        except Exception:
            return out
        out.sort(key=lambda f: (not f.is_dir, f.name.lower()))
        return out

    def total_size(self, directory: str) -> int:
        total = 0
        try:
            for cur, _dirs, names in os.walk(long_path(directory)):
                for n in names:
                    try:
                        total += os.path.getsize(os.path.join(cur, n))
                    except Exception:
                        continue
        except Exception:
            pass
        return total

    # ---------- 放置文件（拖拽落点） ----------

    def place(
        self,
        sources: Iterable[str],
        dest_dir: str,
        mode: str = "copy",
        auto_classify: bool = False,
        classify_levels: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> PlaceResult:
        """把拖入的路径放进 dest_dir。

        mode='copy' 复制；mode='move' 剪切。
        auto_classify=True 时按扩展名自动建分类子目录（拖到分组根目录时的智能归档）。
        """
        result = PlaceResult()
        src_list = [s for s in sources if s]
        total = len(src_list)
        dest_abs = os.path.abspath(dest_dir)

        try:
            os.makedirs(long_path(dest_abs), exist_ok=True)
        except Exception as exc:
            result.failed.extend((s, f"无法创建目标目录：{exc}") for s in src_list)
            return result

        for index, src in enumerate(src_list, start=1):
            if cancel and cancel():
                result.skipped.extend((s, "已取消") for s in src_list[index - 1:])
                break
            if progress:
                progress(index, total, os.path.basename(src.rstrip("\\/")) or src)

            src_abs = os.path.abspath(src)
            path = Path(src_abs)

            if not path.exists():
                result.failed.append((src, "源路径不存在"))
                continue

            # 自己拖到自己里
            if path.is_dir():
                try:
                    if dest_abs == src_abs or Path(dest_abs).is_relative_to(path):
                        result.skipped.append((src, "不能放入自身内部"))
                        continue
                except Exception:
                    pass
            if os.path.normcase(os.path.dirname(src_abs)) == os.path.normcase(dest_abs):
                result.skipped.append((src, "已在目标文件夹中"))
                continue

            target_dir = dest_abs
            if auto_classify and classify_levels and path.is_file():
                target_dir = os.path.join(dest_abs, classify(path.name))
                try:
                    os.makedirs(long_path(target_dir), exist_ok=True)
                except Exception:
                    target_dir = dest_abs

            dst = unique_path(Path(target_dir) / path.name)
            try:
                if mode == "move":
                    shutil.move(long_path(src_abs), long_path(str(dst)))
                elif path.is_dir():
                    shutil.copytree(long_path(src_abs), long_path(str(dst)))
                else:
                    shutil.copy2(long_path(src_abs), long_path(str(dst)))
                result.moved.append((src_abs, str(dst)))
            except Exception as exc:
                result.failed.append((src, f"{type(exc).__name__}: {exc}"))
        return result

    # ---------- 其它 ----------
    def free_space(self) -> int:
        try:
            return shutil.disk_usage(self.root).free
        except Exception:
            return 0

    def all_groups_stats(self) -> dict[str, int]:
        return {g: len(self.folders(g)) for g in self.groups()}
