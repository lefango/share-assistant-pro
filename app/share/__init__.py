# -*- coding: utf-8 -*-
"""分享子系统：本地 HTTP 服务 + cloudflared 隧道。"""
from .options import ShareOptions, TTL_CHOICES, human_left, clean_title
from .server import ShareServer, start_server
from .stats import Stats
from .tunnel import Tunnel, STATE_ERROR, STATE_IDLE, STATE_RUNNING, STATE_STARTING, STATE_STOPPED
from . import qr

__all__ = [
    "ShareOptions", "ShareServer", "start_server", "Stats", "Tunnel", "qr",
    "TTL_CHOICES", "human_left", "clean_title",
    "STATE_ERROR", "STATE_IDLE", "STATE_RUNNING", "STATE_STARTING", "STATE_STOPPED",
]
