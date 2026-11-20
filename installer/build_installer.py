# -*- coding: utf-8 -*-
"""一键打包安装包：app 目录 → payload.zip → 单文件安装程序。

用法：python installer/build_installer.py
前置：先跑过 python build.py（生成 dist/分享助手Pro/）
产物：installer/dist/分享助手Pro_安装程序.exe
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
APP_DIST = os.path.join(APP_ROOT, "dist", "分享助手Pro")
PAYLOAD = os.path.join(HERE, "payload.zip")


def make_payload() -> int:
    if not os.path.isdir(APP_DIST):
        print("找不到应用目录：", APP_DIST, "\n先跑 python build.py")
        return 1
    count = 0
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for base, _dirs, files in os.walk(APP_DIST):
            for name in files:
                full = os.path.join(base, name)
                arc = os.path.relpath(full, APP_DIST)
                zf.write(full, arc)
                count += 1
    print(f"payload.zip: {count} 个文件 / {os.path.getsize(PAYLOAD) / 1024 / 1024:.1f} MB")
    return 0


def main() -> int:
    if make_payload() != 0:
        return 1
    print("打包安装程序…")
    code = subprocess.call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                            os.path.join(HERE, "installer.spec")], cwd=HERE)
    if code != 0:
        print("打包失败")
        return code
    exe = os.path.join(HERE, "dist", "分享助手Pro_安装程序.exe")
    if not os.path.isfile(exe):
        print("没找到安装程序：", exe)
        return 1
    print(f"完成：{exe}  {os.path.getsize(exe) / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
