# -*- coding: utf-8 -*-
"""分享助手 Pro 启动入口（PyInstaller 用这个文件当入口）。"""
import os
import sys
import traceback


def _crash_log(exc_type, exc, tb) -> None:
    """窗口版 exe 没有控制台，崩溃写文件，方便排查。"""
    try:
        import datetime

        from app import paths

        folder = paths.config_dir()
        path = os.path.join(folder, "error.log")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            fh.write("".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:
        pass


def main() -> int:
    from app.main import main as entry

    sys.excepthook = _crash_log
    try:
        return entry()
    except Exception:
        _crash_log(*sys.exc_info())
        raise


if __name__ == "__main__":
    sys.exit(main())
