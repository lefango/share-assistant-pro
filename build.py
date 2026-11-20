# -*- coding: utf-8 -*-
"""一键打包：生成图标 → PyInstaller 出目录版 → 校验。

用法：python build.py
产物：dist/分享助手Pro/分享助手Pro.exe（目录版，整个文件夹一起分发）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
OUT_DIR = os.path.join(DIST, "分享助手Pro")
OUT_EXE = os.path.join(OUT_DIR, "分享助手Pro.exe")


def run(cmd: list[str], timeout: int = 1200) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT, timeout=timeout)


def main() -> int:
    started = time.time()
    print("[1/4] 生成图标")
    if run([sys.executable, os.path.join(ROOT, "_build", "make_icon.py")]) != 0:
        print("图标生成失败")
        return 1

    print("[2/4] 清理旧产物")
    for folder in (DIST, BUILD):
        shutil.rmtree(folder, ignore_errors=True)

    print("[3/4] PyInstaller 打包（目录版，30~60 秒）")
    code = run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                os.path.join(ROOT, "分享助手Pro.spec")])
    if code != 0:
        print("打包失败")
        return code

    if not os.path.isfile(OUT_EXE):
        print("没找到产物：", OUT_EXE)
        return 1
    total = 0
    for folder, _dirs, files in os.walk(OUT_DIR):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass
    print(f"[4/4] 完成：{OUT_DIR}（{total / 1024 / 1024:.0f} MB，"
          f"整个文件夹一起分发）用时 {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
