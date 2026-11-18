# -*- coding: utf-8 -*-
"""MCP stdio 服务端（零第三方依赖，手写 JSON-RPC 2.0 子集）。

工具：
  dy_status     环境是否就绪
  dy_preflight  只读预检（范围内条数 / AI 数 / 待加工数）
  dy_export     只导出（用已有数据写一批交付，不联网）
  dy_sync       完整整理（采集 → 对比 → 重建 → 导出；每条收藏约 1 秒）
  dy_retry      对未完成的批次重跑重建 + 导出（不重新采集）
  dy_report     读批次里的入库报告（环节 / 结果）

协议层与 wx V0.4.3 相同：换行分隔与 Content-Length 双帧自动识别、版本回显、
常见探测方法返回合法空结果、stdout 只输出协议帧（纯 ASCII）。
"""
import json
import sys
import time
import traceback

import engine
from common import MCP_SERVER_NAME, VERSION

PROTOCOL_FALLBACK = "2024-11-05"
_FRAME_MODE = "line"
_EXIT = False

INSTRUCTIONS = (
    "首次接入先调用 dy_status 确认项目目录、解释器、Cookie、账号、知识库五项就绪。"
    "dy_preflight 只读，返回范围内条数与待加工数，建议先跑。"
    "dy_export 只用项目里已有的 rows_merged.json 写一批交付，不联网、不重建，秒级返回。"
    "dy_sync 会真实采集抖音收藏（每条收藏约 1 秒，用时随收藏数等比，受网络与账号影响），"
    "包含账号硬校验，账号不符或无法核对会中止且不重建交付物；"
    "大任务建议先用 dy_preflight 看规模。"
    "dy_retry 只对已有批次重跑重建与导出，不重新采集。"
    "所有导出都新建带时间戳的批次目录，绝不覆盖已有文件。"
)

TOOLS = [
    {
        "name": "dy_status",
        "description": "检查抖音收藏整理环境是否就绪（项目目录、解释器、Cookie、账号确认、知识库）。接入后先调用。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "dy_preflight",
        "description": "只读预检：统计发布时间范围内的条目数、视频/图集数、AI 数、待加工数，不写任何文件。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "起始日期 YYYY-MM-DD（含当天）；留空表示不限"},
                "to": {"type": "string", "description": "结束日期 YYYY-MM-DD（含当天）；留空表示不限"},
                "project_dir": {"type": "string", "description": "可选：项目目录绝对路径"},
            },
            "required": [],
        },
    },
    {
        "name": "dy_export",
        "description": "用项目里已有的整理结果写一批交付到目标目录（不采集、不重建、不联网）。每次新建带时间戳的批次目录，绝不覆盖。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dest": {"type": "string", "description": "交付目录绝对路径"},
                "from": {"type": "string", "description": "起始日期 YYYY-MM-DD；留空表示不限"},
                "to": {"type": "string", "description": "结束日期 YYYY-MM-DD；留空表示不限"},
                "project_dir": {"type": "string", "description": "可选：项目目录绝对路径"},
            },
            "required": ["dest"],
        },
    },
    {
        "name": "dy_sync",
        "description": "完整整理：采集收藏（每条收藏约 1 秒）→ 对比新增 → 重建 Excel/CSV 与 Obsidian 知识库 → 体检 → 写出一批交付。账号不符或无法核对会中止且不重建。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dest": {"type": "string", "description": "交付目录绝对路径"},
                "from": {"type": "string", "description": "起始日期 YYYY-MM-DD；留空表示不限"},
                "to": {"type": "string", "description": "结束日期 YYYY-MM-DD；留空表示不限"},
                "project_dir": {"type": "string", "description": "可选：项目目录绝对路径"},
            },
            "required": ["dest"],
        },
    },
    {
        "name": "dy_report",
        "description": "读取指定批次的入库报告（身份校验 / 新增 / 取消 / 转写 / 介绍 / 概念 / 交付物 / 体检）。",
        "inputSchema": {
            "type": "object",
            "properties": {"batch_path": {"type": "string", "description": "批次目录绝对路径"}},
            "required": ["batch_path"],
        },
    },
    {
        "name": "dy_retry",
        "description": "对采集成功但重建/导出失败的批次重跑（不重新采集），结果写成新的一批，旧批次保留。",
        "inputSchema": {
            "type": "object",
            "properties": {"batch_path": {"type": "string", "description": "批次目录绝对路径"}},
            "required": ["batch_path"],
        },
    },
]


def _log(msg):
    try:
        sys.stderr.write(f"[{MCP_SERVER_NAME}] {msg}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _send(obj):
    data = json.dumps(obj, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    out = sys.stdout.buffer
    if _FRAME_MODE == "lsp":
        out.write(b"Content-Length: " + str(len(data)).encode("ascii") + b"\r\n\r\n" + data)
    else:
        out.write(data + b"\n")
    out.flush()


def _ok(mid, result):
    _send({"jsonrpc": "2.0", "id": mid, "result": result})


def _err(mid, code, message):
    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})


def _text(obj, is_error=False):
    return {"content": [{"type": "text",
                         "text": json.dumps(obj, ensure_ascii=False, indent=2)}],
            "isError": bool(is_error)}


def _call_tool(name, args):
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _text({"ok": False, "error": "arguments 必须是对象"}, True)
    proj = args.get("project_dir") or None
    if name == "dy_status":
        return _text(engine.safe_call(engine.status, proj))
    if name == "dy_preflight":
        r = engine.safe_call(engine.preflight, args.get("from", ""), args.get("to", ""), proj)
        return _text(r, not r.get("ok", False))
    if name == "dy_export":
        if not args.get("dest"):
            return _text({"ok": False, "error": "缺少 dest"}, True)
        r = engine.safe_call(engine.export_only, args.get("dest"), args.get("from", ""),
                             args.get("to", ""), None, None, proj)
        return _text(r, not r.get("ok", False))
    if name == "dy_sync":
        if not args.get("dest"):
            return _text({"ok": False, "error": "缺少 dest"}, True)
        r = engine.safe_call(engine.sync, args.get("dest"), args.get("from", ""),
                             args.get("to", ""), None, None, None, proj)
        return _text(r, not r.get("ok", False))
    if name == "dy_retry":
        r = engine.safe_call(engine.retry, args.get("batch_path"))
        return _text(r, not r.get("ok", False))
    if name == "dy_report":
        import kbreport
        rep = kbreport.load(args.get("batch_path", ""))
        if not rep:
            rep = engine.read_state(args.get("batch_path", "")).get("report") or {
                "ok": False, "error": "批次里没有入库报告"}
        return _text(rep, not bool(rep.get("rows")))
    return _text({"ok": False, "error": f"未知工具：{name}"}, True)


def _handle(msg):
    global _EXIT
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        ver = params.get("protocolVersion") or PROTOCOL_FALLBACK
        return _ok(mid, {
            "protocolVersion": ver,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {"name": MCP_SERVER_NAME, "version": VERSION},
            "instructions": INSTRUCTIONS,
        })
    if str(method).startswith("notifications/"):
        return None
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    empty = {"resources/list": "resources",
             "resources/templates/list": "resourceTemplates",
             "prompts/list": "prompts"}
    if method in empty:
        return _ok(mid, {empty[method]: []})
    if method == "resources/read":
        return _ok(mid, {"contents": []})
    if method == "completion/complete":
        return _ok(mid, {"completion": {"values": [], "total": 0, "hasMore": False}})
    if method == "logging/setLevel":
        return _ok(mid, {})
    if method == "shutdown":
        _EXIT = True
        return _ok(mid, {})
    if method == "exit":
        _EXIT = True
        return None
    if method == "tools/call":
        t0 = time.perf_counter()
        try:
            res = _call_tool(params.get("name"), params.get("arguments"))
        except Exception as e:
            _log(traceback.format_exc(limit=5))
            res = _text({"ok": False, "error": str(e)}, True)
        ms = int((time.perf_counter() - t0) * 1000)
        try:
            body = json.loads(res["content"][0]["text"])
            if isinstance(body, dict):
                body["elapsed_ms"] = ms
                res["content"][0]["text"] = json.dumps(body, ensure_ascii=False, indent=2)
        except (ValueError, KeyError, TypeError):
            pass
        return _ok(mid, res)
    if mid is not None:
        return _err(mid, -32601, f"Method not found: {method}")
    return None


def _dispatch(text):
    try:
        msg = json.loads(text)
    except json.JSONDecodeError as e:
        _send({"jsonrpc": "2.0", "id": None,
               "error": {"code": -32700, "message": f"Parse error: {e}"}})
        return
    try:
        if isinstance(msg, list):
            for one in msg:
                _handle(one)
        elif isinstance(msg, dict):
            _handle(msg)
        else:
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32600, "message": "Invalid Request"}})
    except Exception as e:
        _log(traceback.format_exc(limit=5))
        if isinstance(msg, dict) and msg.get("id") is not None:
            _err(msg["id"], -32603, f"Internal error: {e}")


def serve():
    global _FRAME_MODE
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    _log(f"MCP stdio ready, version {VERSION}")
    inp = sys.stdin.buffer
    while not _EXIT:
        line = inp.readline()
        if not line:
            break
        head = line.strip()
        if not head:
            continue
        if head.lower().startswith(b"content-length:"):
            _FRAME_MODE = "lsp"
            try:
                length = int(head.split(b":", 1)[1].strip())
            except ValueError:
                _send({"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": "Invalid Content-Length"}})
                continue
            while True:
                h = inp.readline()
                if not h or h in (b"\r\n", b"\n"):
                    break
            body = inp.read(length) if length > 0 else b""
            _dispatch(body.decode("utf-8", "replace"))
        else:
            _FRAME_MODE = "line"
            _dispatch(line.decode("utf-8", "replace"))
    return 0
