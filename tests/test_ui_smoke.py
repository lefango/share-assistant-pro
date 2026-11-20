# -*- coding: utf-8 -*-
"""界面冒烟：建窗口、切三页、关掉。不联网、不起隧道。"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = ROOT
sys.path.insert(0, PROJ)

sandbox = tempfile.mkdtemp(prefix="ui-smoke-")
os.environ["APPDATA"] = sandbox
os.environ["USERPROFILE"] = sandbox

from app import paths  # noqa: E402
from app.config import Config  # noqa: E402
from app.service import ShareService  # noqa: E402
from app.library import Library  # noqa: E402
from app import skin  # noqa: E402


class Ctx:
    pass


def build():
    cfg = Config(os.path.join(sandbox, "config.json"))
    cfg.set("auto_start", False)
    lib_dir = os.path.join(sandbox, "文件库")
    recv_dir = os.path.join(sandbox, "收件箱")
    os.makedirs(os.path.join(lib_dir, "默认分组"), exist_ok=True)
    os.makedirs(recv_dir, exist_ok=True)
    cfg.set("library_dir", lib_dir)
    cfg.set("receive_dir", recv_dir)
    theme = skin.load("default")
    import queue
    ctx = Ctx()
    ctx.cfg = cfg
    ctx.theme = theme
    ctx.library = Library(lib_dir)
    ctx.library_dir = lib_dir
    ctx.receive_dir = recv_dir
    ctx.events = queue.Queue()
    ctx.service = ShareService(os.path.join(sandbox, "stats.json"),
                               os.path.join(PROJ, "web"), theme)
    return ctx


def main() -> int:
    from app.ui.default import App
    ctx = build()
    app = App(ctx)
    app.update()
    for page in ("receive", "settings", "files", "receive"):
        app.show_page(page)
        app.update()
    app._render_groups()
    app._render_files()
    app._refresh_receive_list()
    app.update()

    shots = os.path.join(ROOT, "_work", "shots")
    os.makedirs(shots, exist_ok=True)
    # 不截屏：会拍到用户桌面。这里只做结构校验。
    for page in ("files", "receive", "settings"):
        app.show_page(page)
        app.update()
    assert app.winfo_width() > 800
    assert len(app.pages) == 3
    assert len(app.file_list.winfo_children()) >= 0

    app.after(400, app.destroy)
    app.mainloop()
    print("ui smoke ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

