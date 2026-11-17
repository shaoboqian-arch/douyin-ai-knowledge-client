# -*- coding: utf-8 -*-
"""MCP 兼容性：Content-Length 帧 / 换行帧、协议版本回显、握手探测、批量请求、字符串 id。

用法: python tests/verify_mcp_compat.py [目标程序]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
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


def start(target=""):
    argv = [target, "--mcp"] if target else [sys.executable,
                                             os.path.join(APP, "src", "app.py"), "--mcp"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env)


def read_lsp(p):
    headers = {}
    while True:
        line = p.stdout.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        k, _v = line.decode("ascii", "replace").split(":", 1)
        headers[k.lower()] = _v.strip()
    n = int(headers.get("content-length", "0"))
    return json.loads(p.stdout.read(n).decode("utf-8"))


def send_lsp(p, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    p.stdin.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    p.stdin.flush()


def send_line(p, obj):
    p.stdin.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    p.stdin.flush()


def recv_line(p):
    line = p.stdout.readline()
    return json.loads(line.decode("utf-8")) if line.strip() else None


def close(p):
    try:
        p.stdin.close()
        p.wait(timeout=5)
    except Exception:
        p.kill()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else ""

    print("== Content-Length 帧 ==")
    p = start(target)
    try:
        send_lsp(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "lsp-client", "version": "1"}}})
        r = read_lsp(p)
        check("LSP 帧可解析", isinstance(r, dict), str(r)[:120])
        check("回显 2024-11-05", r.get("result", {}).get("protocolVersion") == "2024-11-05")
        send_lsp(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        send_lsp(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        r2 = read_lsp(p)
        check("LSP 帧下工具清单正常", len(r2.get("result", {}).get("tools", [])) == 6)
    finally:
        close(p)

    print("== 换行帧 + 协议版本 ==")
    p = start(target)
    try:
        for ver in ("2025-06-18", "2024-11-05", "2026-01-01"):
            send_line(p, {"jsonrpc": "2.0", "id": ver, "method": "initialize",
                          "params": {"protocolVersion": ver, "capabilities": {},
                                     "clientInfo": {"name": "line", "version": "1"}}})
            r = recv_line(p)
            check(f"回显 {ver}", r.get("result", {}).get("protocolVersion") == ver)
        send_line(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        print("== 握手探测方法 ==")
        for method, key in (("resources/list", "resources"),
                            ("resources/templates/list", "resourceTemplates"),
                            ("prompts/list", "prompts")):
            send_line(p, {"jsonrpc": "2.0", "id": method, "method": method})
            r = recv_line(p)
            check(f"{method} 返回 {key} 空数组", r.get("result", {}).get(key) == [])
        send_line(p, {"jsonrpc": "2.0", "id": "rr", "method": "resources/read",
                      "params": {"uri": "x"}})
        check("resources/read 返回空 contents", recv_line(p).get("result", {}).get("contents") == [])
        send_line(p, {"jsonrpc": "2.0", "id": "cc", "method": "completion/complete",
                      "params": {}})
        check("completion/complete 合法空结果",
              "completion" in recv_line(p).get("result", {}))
        send_line(p, {"jsonrpc": "2.0", "id": "sl", "method": "logging/setLevel",
                      "params": {"level": "info"}})
        check("logging/setLevel 返回空对象", recv_line(p).get("result") == {})
        send_line(p, {"jsonrpc": "2.0", "id": "p", "method": "ping"})
        check("ping 返回空对象", recv_line(p).get("result") == {})

        print("== 批量与 id 形态 ==")
        send_line(p, [{"jsonrpc": "2.0", "id": "a", "method": "ping"},
                      {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}])
        r1, r2 = recv_line(p), recv_line(p)
        ids = {r1.get("id"), r2.get("id")}
        check("批量请求逐条响应", ids == {"a", 7}, str(ids))
        check("字符串 id 原样回显", "a" in ids)

        print("== 通知不产生响应 ==")
        send_line(p, {"jsonrpc": "2.0", "method": "notifications/progress",
                      "params": {"progressToken": "x"}})
        send_line(p, {"jsonrpc": "2.0", "id": "after-note", "method": "ping"})
        r = recv_line(p)
        check("通知无响应帧（下一条就是后续请求）", r.get("id") == "after-note", str(r)[:120])

        print("== 关闭 ==")
        send_line(p, {"jsonrpc": "2.0", "id": "sd", "method": "shutdown"})
        check("shutdown 返回空对象", recv_line(p).get("result") == {})
        send_line(p, {"jsonrpc": "2.0", "method": "exit"})
        check("exit 后进程退出", p.wait(timeout=5) == 0)
    finally:
        if p.poll() is None:
            close(p)

    print("== 垃圾输入 ==")
    p = start(target)
    try:
        p.stdin.write(b"{not json}\n")
        p.stdin.flush()
        r = recv_line(p)
        check("非法 JSON 返回 -32700", r.get("error", {}).get("code") == -32700, str(r)[:120])
        send_line(p, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        check("非法输入后仍可服务", recv_line(p).get("result") == {})
    finally:
        close(p)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
