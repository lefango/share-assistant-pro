# -*- coding: utf-8 -*-
"""验收：app/uploads.py（本地模型产出，人验收）。"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.uploads import CHUNK_SIZE, ChunkStore, UploadQuota  # noqa: E402

passed, failed = 0, 0


def check(name: str, fn) -> None:
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"PASS {name}")
    except Exception as exc:
        failed += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def t_quota() -> None:
    q = UploadQuota(100)
    assert q.accept(60)
    q.add(60)
    assert not q.accept(50)
    assert q.remaining() == 40
    assert q.snapshot() == {"limit": 100, "used": 60, "remaining": 40}


def t_unlimited() -> None:
    q = UploadQuota(0)
    assert q.remaining() == -1
    assert q.accept(10 ** 9)
    q.add(-5)
    assert q.snapshot()["used"] == 0


def t_chunk_size() -> None:
    assert CHUNK_SIZE == 64 * 1024 * 1024


def t_roundtrip() -> None:
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    dest = os.path.join(root, "dest")
    store.begin("u1", "a.txt", 10)
    store.write_chunk("u1", 0, b"0123")
    store.write_chunk("u1", 1, b"456")
    store.write_chunk("u1", 2, b"789")
    path, size = store.finish("u1", dest)
    assert size == 10
    with open(path, "rb") as fh:
        assert fh.read() == b"0123456789"
    assert os.path.basename(path) == "a.txt"


def t_dup_name() -> None:
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    dest = os.path.join(root, "dest")
    for uid in ("a", "b"):
        store.begin(uid, "same.txt", 1)
        store.write_chunk(uid, 0, b"x")
    p1, _ = store.finish("a", dest)
    p2, _ = store.finish("b", dest)
    assert p1 != p2
    assert os.path.basename(p1) == "same.txt"
    assert os.path.basename(p2) != "same.txt"


def t_skip_index() -> None:
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    store.begin("s", "x.bin", 10)
    store.write_chunk("s", 0, b"aa")
    try:
        store.write_chunk("s", 2, b"bb")
    except ValueError:
        return
    raise AssertionError("跳号没有抛 ValueError")


def t_cleanup() -> None:
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    store.begin("c", "x.bin", 10)
    time.sleep(0.01)
    assert store.cleanup(0) >= 1


def t_abort() -> None:
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    temp = store.begin("z", "x.bin", 10)
    store.abort("z")
    assert not os.path.exists(temp)


def t_dirty_id() -> None:
    """已知瑕疵：id 只在 begin 里清洗，write_chunk 用原始 id 查表。"""
    root = tempfile.mkdtemp()
    store = ChunkStore(os.path.join(root, "tmp"))
    store.begin("a/b", "x.bin", 2)
    store.write_chunk("a/b", 0, b"ab")
    store.finish("a/b", os.path.join(root, "dest"))


check("配额基本语义", t_quota)
check("不限量", t_unlimited)
check("分片常量", t_chunk_size)
check("分片拼回内容一致", t_roundtrip)
check("重名自动加序号", t_dup_name)
check("跳号拒绝", t_skip_index)
check("超时清理", t_cleanup)
check("中止删临时文件", t_abort)
check("带非法字符的 upload_id", t_dirty_id)

print(f"\n{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)

