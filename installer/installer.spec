# -*- mode: python ; coding: utf-8 -*-
"""安装程序（目录版）。

不用单文件：这台机器上 PyInstaller 单文件在含中文的路径下会报
"Could not create temporary directory"，目录版不往临时目录解包，放哪都能跑。
"""
import os

ROOT = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821

a = Analysis(
    [os.path.join(ROOT, "installer.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "payload.zip"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "pandas", "matplotlib", "scipy", "pytest", "customtkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="分享助手Pro_安装程序",
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
    icon=os.path.join(ROOT, "..", "assets", "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="分享助手Pro_安装程序",
)
