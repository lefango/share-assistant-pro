# -*- coding: utf-8 -*-
"""分享助手 Pro · 入口。

用法：
    分享助手Pro.exe             打开界面
    分享助手Pro.exe --check     自检（不打开界面）
    分享助手Pro.exe --version   看版本
"""
from __future__ import annotations

import argparse
import importlib
import os
import queue
import sys
import traceback


def _enable_dpi() -> None:
    """让窗口按物理像素渲染：不做的话 Windows 会位图拉伸，界面发虚。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        # Per-Monitor V2：多显示器、不同缩放比下都清晰
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def build_context():
    from . import paths, skin
    from .config import Config
    from .library import Library
    from .service import ShareService

    cfg = Config()
    library_dir, receive_dir = cfg.ensure_dirs()
    theme = skin.load(cfg.get("skin"))
    events: queue.Queue = queue.Queue()
    service = ShareService(
        stats_path=os.path.join(paths.config_dir(), "stats.json"),
        web_dir=paths.web_dir(),
        theme=theme,
        on_state=lambda state, message: events.put(("state", (state, message))),
        on_url=lambda url: events.put(("url", url)),
        on_log=lambda line: events.put(("log", line)),
    )
    ctx = _Context(cfg=cfg, service=service, theme=theme,
                   library=Library(library_dir), events=events,
                   library_dir=library_dir, receive_dir=receive_dir)
    return ctx


class _Context:
    """界面拿到的全部依赖（新 UI 只要实现 run(ctx) 就能替换）。"""

    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def check() -> int:
    """不打开界面的自检，打包后也能跑。"""
    from . import paths, skin

    ok = True
    print(f"分享助手 Pro {paths.VERSION}")
    print(f"程序目录 : {paths.app_dir()}")
    print(f"资源目录 : {paths.resource_dir()}")

    cfg = build_context()
    print(f"配置文件 : {cfg.cfg.path}")
    for label, folder in (("文件库", cfg.library_dir), ("收件箱", cfg.receive_dir)):
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".write-test")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            print(f"{label} : {folder} 可写")
        except Exception as exc:
            ok = False
            print(f"{label} : {folder} 不可写（{exc}）")

    web = paths.web_dir()
    for name in ("index.html", "receive.html", "style.css", "app.js", "receive.js"):
        exists = os.path.isfile(os.path.join(web, name))
        ok = ok and exists
        print(f"网页 {name:14s} {'有' if exists else '缺失'}")

    cf = paths.cloudflared_path()
    print(f"cloudflared: {'有' if os.path.isfile(cf) else '缺失（可只用局域网模式）'}")

    try:
        import qrcode  # noqa: F401
        print("二维码库 : 有")
    except Exception:
        print("二维码库 : 缺失（二维码功能不可用）")

    theme = skin.load(cfg.cfg.get("skin"))
    print(f"皮肤 : {theme.get('name')} / {theme.get('label')}")

    try:
        import customtkinter  # noqa: F401
        from tkinterdnd2 import TkinterDnD  # noqa: F401
        print("界面依赖 : 有")
    except Exception as exc:
        ok = False
        print(f"界面依赖 : 缺失（{exc}）")

    print("自检结果 :", "通过" if ok else "有问题")
    try:
        cfg.service.stop()
    except Exception:
        pass
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--check", action="store_true", help="自检后退出")
    parser.add_argument("--version", action="store_true", help="显示版本")
    parser.add_argument("--ui", default="", help="指定界面实现（默认读配置）")
    args = parser.parse_args(argv)

    _enable_dpi()

    if args.version:
        from . import paths
        print(paths.VERSION)
        return 0
    if args.check:
        return check()

    ctx = build_context()
    ui_name = args.ui or ctx.cfg.get("ui") or "default"
    try:
        module = importlib.import_module(f".ui.{ui_name}", __package__)
    except Exception:
        traceback.print_exc()
        module = importlib.import_module(".ui.default", __package__)
    return int(module.run(ctx) or 0)


if __name__ == "__main__":
    sys.exit(main())
