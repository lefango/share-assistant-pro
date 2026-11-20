# -*- coding: utf-8 -*-
import os
import uuid

from ..uploads import ChunkStore, UploadQuota, CHUNK_SIZE


class UploadAPI:
    """分片接收的业务层：只处理参数和配额，不碰 HTTP。"""

    def __init__(self, quota: UploadQuota, store: ChunkStore, receive_dir: str) -> None:
        self.quota = quota
        self.store = store
        self.receive_dir = receive_dir

    def begin(self, name: str, total: int) -> dict:
        if not name or total <= 0:
            return {"ok": False, "error": "name 为空或 total 须为正整数"}
        if not self.quota.accept(total):
            return {"ok": False, "error": "超过本次接收总量",
                    "remaining": self.quota.remaining()}
        upload_id = uuid.uuid4().hex
        self.store.begin(upload_id, name, total)
        return {"ok": True, "upload_id": upload_id, "chunk_size": CHUNK_SIZE}

    def put(self, upload_id: str, index: int, data: bytes) -> dict:
        try:
            self.store.write_chunk(upload_id, index, data)
        except KeyError:
            return {"ok": False, "error": "上传会话不存在"}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "received": self.store.received(upload_id)}

    def finish(self, upload_id: str) -> dict:
        try:
            path, size = self.store.finish(upload_id, self.receive_dir)
        except KeyError:
            return {"ok": False, "error": "上传会话不存在"}
        except Exception as exc:
            self.store.abort(upload_id)
            return {"ok": False, "error": str(exc)}
        file_name = os.path.basename(path)
        self.quota.add(size)
        return {"ok": True, "name": file_name, "size": size}

    def abort(self, upload_id: str) -> dict:
        self.store.abort(upload_id)
        return {"ok": True}

    def status(self) -> dict:
        snap = self.quota.snapshot()
        limit = snap.get("limit", 0)
        remaining = snap.get("remaining", 0)
        if limit == 0:
            limit_text = "不限量"
        else:
            limit_text = "剩余 %dMB" % (remaining // 1048576)
        return {"ok": True, "quota": snap, "limit_text": limit_text}


if __name__ == "__main__":
    # [[ASK]] ChunkStore 与 UploadQuota 的构造函数签名未在任务中给出，
    #         此处假设 ChunkStore(base_dir: str) 与 UploadQuota(limit_bytes: int)。
    import tempfile
    import shutil

    tmp_root = tempfile.mkdtemp(prefix="upload_api_test_")
    try:
        receive_dir = os.path.join(tmp_root, "receive")
        os.makedirs(receive_dir)
        chunk_dir = os.path.join(tmp_root, "chunks")
        os.makedirs(chunk_dir)

        # 10 MB 限额
        quota = UploadQuota(10 * 1048576)
        store = ChunkStore(chunk_dir)
        api = UploadAPI(quota, store, receive_dir)

        # begin 小文件（200 字节）
        r = api.begin("hello.txt", 200)
        assert r["ok"] is True, r
        uid = r["upload_id"]
        assert isinstance(uid, str) and len(uid) > 0

        # 分两片 put
        part0 = b"0123456789" * 10          # 100 bytes
        part1 = b"ABCDEFGHIJ" * 10          # 100 bytes
        r = api.put(uid, 0, part0)
        assert r["ok"] is True, r
        assert r["received"] == 100, r

        r = api.put(uid, 1, part1)
        assert r["ok"] is True, r
        assert r["received"] == 200, r

        used_before = quota.snapshot()["used"]

        # finish
        r = api.finish(uid)
        assert r["ok"] is True, r
        assert r["name"] == "hello.txt", r
        assert r["size"] == 200, r

        # 断言落盘文件内容正确
        final_path = os.path.join(receive_dir, "hello.txt")
        with open(final_path, "rb") as f:
            content = f.read()
        assert content == part0 + part1, "落盘内容不一致"

        # quota used 增加
        used_after = quota.snapshot()["used"]
        assert used_after == used_before + 200, "quota.used 未正确累加"

        # 超限 begin 失败（limit=100，请求 200）
        quota_small = UploadQuota(100)
        store_small = ChunkStore(os.path.join(tmp_root, "chunks_small"))
        os.makedirs(store_small._base_dir if hasattr(store_small, "_base_dir")
                    else os.path.join(tmp_root, "chunks_small"), exist_ok=True)
        api_small = UploadAPI(quota_small, store_small, receive_dir)
        r = api_small.begin("big.bin", 200)
        assert r["ok"] is False, r
        assert r["error"] == "超过本次接收总量", r
        assert "remaining" in r, r

        # 坏 id 的 put → ok=False
        r = api.put("deadbeef" * 4, 0, part0)
        assert r["ok"] is False, r
        assert r["error"] == "上传会话不存在", r

        print("all ok")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
