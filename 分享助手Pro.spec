# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包定义：分享助手Pro（目录版）。

为什么不是单文件：单文件版在含中文的目录下启动会报
"Could not create temporary directory"，装到 Program Files\分享助手Pro 也会踩到。
目录版不往临时目录解包，启动更快，也更好卸载。
"""
import os

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821
sys.path.insert(0, ROOT)

datas = [
    (os.path.join(ROOT, "web"), "web"),
    (os.path.join(ROOT, "skin"), "skin"),
    (os.path.join(ROOT, "assets"), "assets"),
]
if os.path.isdir(os.path.join(ROOT, "bin")):
    datas.append((os.path.join(ROOT, "bin"), "bin"))

hiddenimports = (
    collect_submodules("customtkinter")
    + collect_submodules("tkinterdnd2")
    + collect_submodules("app") + ["qrcode", "qrcode.image.svg", "PIL._tkinter_finder", "PIL.ImageTk"]
)
datas += collect_data_files("customtkinter")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "pandas", "matplotlib", "scipy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="分享助手Pro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="分享助手Pro",
)


