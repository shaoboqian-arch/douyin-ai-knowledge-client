# -*- coding: utf-8 -*-
"""MCP 全链路：握手 → 工具清单 → 状态 → 预检 → 真实导出 → 边界错误。

用法: python tests/verify_mcp.py [目标程序]
默认用源码入口（python src/app.py --mcp）；给 exe 时直接对冻结态跑。
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402
from common import VERSION  # noqa: E402

FAILS = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


class Client:
    def __init__(self, argv, env):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                  errors="replace", bufsize=1, env=env)
        self.n = 0

    def send(self, obj):
        self.p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def recv(self):
        line = self.p.stdout.readline()
        return json.loads(line) if line.strip() else None

    def call(self, method, params=None, mid=None):
        if mid is None:
            self.n += 1
            mid = self.n
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        return self.recv()

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    argv = [target, "--mcp"] if target else [sys.executable,
                                             os.path.join(APP, "src", "app.py"), "--mcp"]
    tmp = tempfile.mkdtemp(prefix="dysync-mcp-")
    kb = _fixture.make_kb(tmp)
    project, _rows = _fixture.make_project(tmp)
    settings = _fixture.configure(tmp, project, kb)
    env = os.environ.copy()
    env["DYSYNC_SETTINGS"] = settings
    env["PYTHONIOENCODING"] = "utf-8"

    c = Client(argv, env)
    try:
        print("== 握手 ==")
        r = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "verify", "version": "1"}})
        res = r.get("result", {})
        check("回显协议版本", res.get("protocolVersion") == "2025-06-18", str(res)[:200])
        check("serverInfo 名称正确", res.get("serverInfo", {}).get("name") == "douyin-fav-sync")
        check(f"serverInfo 版本为 {VERSION}", res.get("serverInfo", {}).get("version") == VERSION)
        check("声明 tools 能力", "tools" in res.get("capabilities", {}))
        check("带 instructions", bool(res.get("instructions")))
        c.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        print("== 工具清单 ==")
        r = c.call("tools/list")
        tools = [t["name"] for t in r["result"]["tools"]]
        check("6 个工具", len(tools) == 6, str(tools))
        check("工具名齐全", set(tools) == {"dy_status", "dy_preflight", "dy_export",
                                     "dy_sync", "dy_retry", "dy_report"}, str(tools))
        check("每个工具都有 inputSchema",
              all(t.get("inputSchema", {}).get("type") == "object" for t in r["result"]["tools"]))

        print("== 状态与预检 ==")
        r = c.call("tools/call", {"name": "dy_status", "arguments": {}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("状态 ready", body.get("ready") is True, str(body)[:300])
        check("状态带 elapsed_ms", isinstance(body.get("elapsed_ms"), int))
        check("状态不含 cookie 原文", "fake-cookie" not in json.dumps(body, ensure_ascii=False))

        r = c.call("tools/call", {"name": "dy_preflight", "arguments": {}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("预检总数 5", body.get("total") == 5, str(body)[:200])
        check("预检范围内 5", body.get("in_range") == 5)

        r = c.call("tools/call", {"name": "dy_preflight",
                                  "arguments": {"from": "2026-01-01", "to": "2026-01-02"}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("预检日期过滤生效", body.get("in_range") == 1, str(body)[:200])

        print("== 真实导出 ==")
        dest = os.path.join(tmp, "out")
        r = c.call("tools/call", {"name": "dy_export",
                                  "arguments": {"dest": dest, "from": "2026-10-01",
                                                "to": "2026-11-30"}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("导出成功", body.get("ok") is True, str(body)[:300])
        batch = body.get("batch_path", "")
        check("批次目录存在", os.path.isdir(batch), batch)
        check("写出 4 个 md", len([1 for b, _d, fs in os.walk(batch) for f in fs
                                if f.endswith(".md")]) == 4)
        check("清单存在", os.path.isfile(os.path.join(batch, "_导出清单.csv")))

        r = c.call("tools/call", {"name": "dy_export", "arguments": {}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("缺 dest 返回错误", r["result"].get("isError") is True and not body.get("ok"))

        print("== 完整整理与入库报告 ==")
        dest2 = os.path.join(tmp, "out-sync")
        r = c.call("tools/call", {"name": "dy_sync", "arguments": {"dest": dest2}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("dy_sync 成功", body.get("ok") is True, str(body)[:300])
        batch2 = body.get("batch_path", "")
        check("dy_sync 产出报告", bool((body.get("report") or {}).get("rows")),
              str(body.get("report"))[:200])
        r = c.call("tools/call", {"name": "dy_report", "arguments": {"batch_path": batch2}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("dy_report 返回 8 行", len(body.get("rows") or []) == 8, str(body)[:200])
        check("dy_report 含身份校验", any(x.get("环节") == "身份校验"
                                    for x in body.get("rows") or []))

        print("== 续跑边界 ==")
        r = c.call("tools/call", {"name": "dy_retry", "arguments": {"batch_path": batch}})
        body = json.loads(r["result"]["content"][0]["text"])
        check("已完成批次不再续跑", body.get("ok") is False and "已经完成" in body.get("error", ""),
              str(body)[:200])

        print("== 协议边界 ==")
        r = c.call("tools/call", {"name": "nope", "arguments": {}})
        check("未知工具报 isError", r["result"].get("isError") is True)
        r = c.call("tools/call", {"name": "dy_status", "arguments": [1, 2]})
        check("arguments 非对象被拒", r["result"].get("isError") is True)
        r = c.call("no/such/method")
        check("未知方法 -32601", r.get("error", {}).get("code") == -32601, str(r)[:120])
        r = c.call("ping")
        check("ping 返回空结果", r.get("result") == {})

        print("== stdout 纯 ASCII ==")
        # 只检查协议层：重新发一次请求，读原始行
        c.send({"jsonrpc": "2.0", "id": 99, "method": "tools/list"})
        raw = c.p.stdout.readline()
        check("协议帧为纯 ASCII", all(ord(ch) < 128 for ch in raw), repr(raw[:80]))
    finally:
        c.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
