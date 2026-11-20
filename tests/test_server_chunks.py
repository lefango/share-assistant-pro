# -*- coding: utf-8 -*-
"""验收：分片上传 HTTP 链路（真起服务，不用隧道）。"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = ROOT
sys.path.insert(0, PROJ)

from app.share.options import ShareOptions  # noqa: E402
from app.share.server import ShareServer  # noqa: E402
from app.share.stats import Stats  # noqa: E402

passed = failed = 0


def check(name: str, fn) -> None:
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"PASS {name}")
    except Exception as exc:
        failed += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="chunk-http-")
    src = os.path.join(tmp, "src")
    recv = os.path.join(tmp, "recv")
    os.makedirs(src)
    os.makedirs(recv)
    with open(os.path.join(src, "a.txt"), "wb") as fh:
        fh.write(b"hello")

    opts = ShareOptions(sources=[("测试", src)], title="测试", password="pw123",
                        allow_upload=True, upload_dir=recv,
                        receive_limit=1024 * 1024)
    stats = Stats(os.path.join(tmp, "stats.json"))
    server = ShareServer(opts, stats, os.path.join(PROJ, "web"))
    server.start()
    port = server.port
    cookie = ""

    def req(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        hdrs = dict(headers or {})
        if cookie:
            hdrs["Cookie"] = cookie
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        set_cookie = resp.getheader("Set-Cookie")
        conn.close()
        return resp.status, data, set_cookie

    def t_meta_public():
        status, data, _ = req("GET", "/api/meta")
        meta = json.loads(data)
        assert status == 200, status
        assert meta["need_password"] is True
        assert meta["allow_upload"] is True
        assert meta["receive"]["ok"] is True

    def t_login():
        nonlocal cookie
        status, data, set_cookie = req(
            "POST", "/api/login", json.dumps({"password": "pw123"}).encode(),
            {"Content-Type": "application/json"})
        assert status == 200, (status, data)
        assert set_cookie
        cookie = set_cookie.split(";")[0]

    def t_login_bad():
        status, _, _ = req("POST", "/api/login",
                           json.dumps({"password": "nope"}).encode(),
                           {"Content-Type": "application/json"})
        assert status == 403, status

    def t_receive_page():
        status, data, _ = req("GET", "/receive")
        assert status == 200
        assert "接收区" in data.decode("utf-8")

    def t_chunk_flow():
        payload = os.urandom(300000)
        status, data, _ = req("POST", "/api/upload/begin",
                              json.dumps({"name": "big.bin", "total": 300000}).encode(),
                              {"Content-Type": "application/json"})
        info = json.loads(data)
        assert status == 200 and info["ok"], (status, data)
        upload_id = info["upload_id"]
        for index, start in enumerate((0, 150000)):
            status, data, _ = req("POST", "/api/upload/chunk", payload[start:start + 150000],
                                  {"X-Upload-Id": upload_id,
                                   "X-Chunk-Index": str(index),
                                   "Content-Type": "application/octet-stream"})
            assert status == 200 and json.loads(data)["ok"], (status, data)
        status, data, _ = req("POST", "/api/upload/finish",
                              json.dumps({"upload_id": upload_id}).encode(),
                              {"Content-Type": "application/json"})
        result = json.loads(data)
        assert status == 200 and result["ok"], (status, data)
        path = os.path.join(recv, result["name"])
        assert os.path.isfile(path)
        with open(path, "rb") as fh:
            assert fh.read() == payload

    def t_quota_reject():
        status, data, _ = req("POST", "/api/upload/begin",
                              json.dumps({"name": "huge.bin", "total": 5 * 1024 * 1024}).encode(),
                              {"Content-Type": "application/json"})
        assert status == 413, (status, data)
        assert "remaining" in json.loads(data)

    def t_legacy_upload():
        status, data, _ = req("POST", "/api/upload", b"legacy-data",
                              {"X-File-Name": "small.txt",
                               "Content-Type": "application/octet-stream"})
        assert status == 200, (status, data)
        assert json.loads(data)["ok"]

    def t_need_auth():
        nonlocal cookie
        saved, cookie = cookie, ""
        try:
            status, _, _ = req("POST", "/api/upload/begin",
                               json.dumps({"name": "x", "total": 10}).encode(),
                               {"Content-Type": "application/json"})
            assert status == 401, status
        finally:
            cookie = saved

    try:
        check("meta 公开可读且带接收配额", t_meta_public)
        check("错误密码被拒", t_login_bad)
        check("正确密码登录", t_login)
        check("接收页可打开", t_receive_page)
        check("分片上传 → 拼回完整文件", t_chunk_flow)
        check("超过接收总量被拒", t_quota_reject)
        check("旧接口仍可用", t_legacy_upload)
        check("未登录不能上传", t_need_auth)
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

