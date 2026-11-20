# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包定义：分享助手Pro.exe（单文件）。"""
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821

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
    + ["qrcode", "qrcode.image.svg", "PIL._tkinter_finder", "PIL.ImageTk"]
)

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
    a.binaries,
    a.datas,
    [],
    name="ShareProDebug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.ico"),
)

