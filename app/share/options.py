# -*- coding: utf-8 -*-
"""分享会话配置。由界面填好后交给 ShareServer。

支持一次分享**多个来源**（sources）：整个文件库、若干分组、若干任意本地文件夹。
网页上只挂一个来源时不加多余层级；挂了多个来源时，首页会先列出这几个来源。
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field


@dataclass
class ShareOptions:
    """一次分享的全部参数。"""

    root: str = ""                  # 主来源目录（兼容旧用法；normalized 后 = sources[0] 的路径）
    sources: list[tuple[str, str]] = field(default_factory=list)   # [(网页上显示的名字, 绝对路径)]
    title: str = "我的分享"          # 网页标题
    password: str = ""              # 空 = 不需要密码
    ttl_seconds: int = 0            # 0 = 不限时
    allow_upload: bool = False      # 是否允许对方上传
    upload_dir: str = ""            # 收件箱目录（allow_upload 时必填）
    receive_limit: int = 0          # 本次最多接收多少字节；0 = 不限
    allow_download: bool = True     # 是否允许下载原文件
    readonly_note: str = ""         # 网页上显示的一句话

    # 运行时
    token: str = ""                 # 本次分享的随机令牌（Cookie 签名用）
    started_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        return self.started_at + self.ttl_seconds if self.ttl_seconds > 0 else 0.0

    @property
    def remaining(self) -> int:
        if self.ttl_seconds <= 0:
            return -1
        return max(0, int(self.expires_at - time.time()))

    def expired(self) -> bool:
        return self.ttl_seconds > 0 and time.time() >= self.expires_at

    # ---------------------------------------------------------------- 归一化
    def normalized(self) -> "ShareOptions":
        self.sources = self._clean_sources()
        if not self.sources and self.root:
            path = os.path.abspath(os.path.expanduser(self.root))
            self.sources = [(_default_name(path), path)]
        if self.sources:
            self.root = self.sources[0][1]
        elif self.root:
            self.root = os.path.abspath(os.path.expanduser(self.root))

        if self.allow_upload:
            if not self.upload_dir:
                self.upload_dir = os.path.join(self.root, "收件箱")
            self.upload_dir = os.path.abspath(self.upload_dir)
        self.title = (self.title or "我的分享").strip()[:60]
        return self

    def _clean_sources(self) -> list[tuple[str, str]]:
        """去重、去无效路径、给重名的来源加父目录后缀。"""
        raw: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in self.sources or []:
            try:
                name, path = item
            except Exception:
                continue
            path = os.path.abspath(os.path.expanduser(str(path or "")))
            if not path or not os.path.isdir(path):
                continue
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            raw.append((str(name or "").strip(), path))

        # 名字去重：同名的补上父目录
        counts: dict[str, int] = {}
        for name, path in raw:
            base = name or _default_name(path)
            counts[base.lower()] = counts.get(base.lower(), 0) + 1

        out: list[tuple[str, str]] = []
        used: set[str] = set()
        for name, path in raw:
            label = (name or _default_name(path))[:40]
            if counts.get(label.lower(), 0) > 1:
                parent = os.path.basename(os.path.dirname(os.path.normpath(path)))
                label = f"{label}（{parent or path}）"[:40]
            base_label, n = label, 2
            while label.lower() in used:
                label = f"{base_label} {n}"
                n += 1
            used.add(label.lower())
            out.append((label, path))
        return out


def _default_name(path: str) -> str:
    norm = os.path.normpath(path)
    name = os.path.basename(norm)
    if name:
        return name
    drive = os.path.splitdrive(norm)[0]
    return f"{drive} 盘" if drive else "文件夹"


def human_left(seconds: int) -> str:
    if seconds < 0:
        return "不限时"
    if seconds == 0:
        return "已结束"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分钟"
    return f"{seconds} 秒"


TTL_CHOICES: list[tuple[str, int]] = [
    ("不限时", 0),
    ("30 分钟", 1800),
    ("1 小时", 3600),
    ("6 小时", 21600),
    ("24 小时", 86400),
    ("7 天", 604800),
]


_SAFE_TITLE = re.compile(r"[^\w\u4e00-\u9fff \-_.]", re.UNICODE)


def clean_title(text: str) -> str:
    return _SAFE_TITLE.sub("", text or "").strip() or "我的分享"
