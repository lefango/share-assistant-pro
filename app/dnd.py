# -*- coding: utf-8 -*-
"""拖拽支持：把任意控件（含其内部子控件）注册为文件投放目标。"""
from __future__ import annotations

from typing import Callable

from tkinterdnd2 import DND_FILES

DropHandler = Callable[[object], str]


def iter_widget_tree(widget):
    """深度遍历控件及其全部子控件。"""
    stack = [widget]
    seen = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        try:
            stack.extend(current.winfo_children())
        except Exception:
            continue


def parse_drop_text(widget, data: str) -> list[str]:
    """把 <<Drop>> 事件里的 data 解析成路径列表。"""
    if not data:
        return []
    try:
        items = widget.tk.splitlist(data)
    except Exception:
        items = [data]
    paths: list[str] = []
    for item in items:
        item = str(item).strip()
        if not item:
            continue
        if len(item) >= 2 and item[0] == "{" and item[-1] == "}":
            item = item[1:-1]
        paths.append(item)
    return paths


def register_drop_target(
    widget,
    on_drop: DropHandler,
    on_enter: DropHandler | None = None,
    on_leave: DropHandler | None = None,
    deep: bool = True,
) -> int:
    """把 widget（可选连同所有子控件）注册为 DND_FILES 投放目标。

    deep=True 时必须在该控件子树构建完成后再调用。
    返回成功注册的控件数量。
    """
    targets = list(iter_widget_tree(widget)) if deep else [widget]
    count = 0
    for target in targets:
        try:
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", on_drop)
            if on_enter is not None:
                target.dnd_bind("<<DropEnter>>", on_enter)
            if on_leave is not None:
                target.dnd_bind("<<DropLeave>>", on_leave)
            count += 1
        except Exception:
            continue
    return count


def unbind_drop_target(widget, deep: bool = True) -> None:
    targets = list(iter_widget_tree(widget)) if deep else [widget]
    for target in targets:
        try:
            target.drop_target_unregister()
        except Exception:
            continue


def bind_tree(widget, sequence: str, func, add: str = "+", deep: bool = True) -> None:
    """给控件（及子控件）绑定普通事件，让整张卡片都能响应点击。"""
    targets = list(iter_widget_tree(widget)) if deep else [widget]
    for target in targets:
        try:
            target.bind(sequence, func, add)
        except Exception:
            continue
