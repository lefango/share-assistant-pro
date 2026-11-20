# -*- coding: utf-8 -*-
"""界面注册表：一个界面实现 = app/ui/<名字>/，必须暴露 run(ctx)。

后面换 UI 的步骤：
    1. 新建 app/ui/<新名字>/__init__.py，里面写 def run(ctx) -> int
    2. 配置里把 "ui" 改成 <新名字>（设置页下拉框）
    3. 网页皮肤跟着 skin/<名字>/theme.json 一起换
"""
from __future__ import annotations

import importlib
import os


def available() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    names = []
    for entry in os.listdir(here):
        if entry.startswith("_") or entry == "base.py":
            continue
        path = os.path.join(here, entry)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            names.append(entry)
    return sorted(names) or ["default"]


def load(name: str):
    return importlib.import_module(f"{__name__}.{name}")
