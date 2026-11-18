# -*- coding: utf-8 -*-
"""MCP 接入配置：生成、检查、合并写入、连通性自检。

写入时**只增改 douyin-fav-sync 一个键**，其余连接器原样保留；
写前备份、临时文件原子替换；解析失败一律不写。
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

from common import MCP_SERVER_NAME, VERSION, is_frozen, src_dir

DESCRIPTION = "抖音收藏采集与知识库整理（读取本机抖音项目数据）"

# 窗口子系统构建下本进程没有控制台；派生 exe 时不加这个会自己弹一个黑框。
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def mcp_json_path():
    return os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")


def current_command():
    if is_frozen():
        return sys.executable, ["--mcp"]
    return sys.executable, [os.path.join(src_dir(), "app.py"), "--mcp"]


def server_entry():
    command, args = current_command()
    return {"type": "stdio", "command": command, "args": args, "description": DESCRIPTION}


def config_fragment():
    return {"mcpServers": {MCP_SERVER_NAME: server_entry()}}


def fragment_text():
    return json.dumps(config_fragment(), ensure_ascii=False, indent=2)


def read_config(path=None):
    path = path or mcp_json_path()
    if not os.path.isfile(path):
        return {"mcpServers": {}}, ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"读取/解析失败：{e}"
    if not isinstance(data, dict):
        return None, "顶层不是 JSON 对象"
    servers = data.get("mcpServers")
    if servers is None:
        data["mcpServers"] = {}
        servers = data["mcpServers"]
    if not isinstance(servers, dict):
        return None, "mcpServers 不是对象"
    return data, ""


def inspect_config(path=None):
    path = path or mcp_json_path()
    data, err = read_config(path)
    if err:
        return {"ok": False, "path": path, "error": err}
    servers = data.get("mcpServers", {})
    entry = servers.get(MCP_SERVER_NAME)
    command, args = current_command()
    return {
        "ok": True, "path": path, "exists": os.path.isfile(path),
        "servers": sorted(servers.keys()), "has_entry": entry is not None,
        "command_matches": bool(entry and entry.get("command") == command),
        "current_command": command, "current_args": args,
        "other_count": len([k for k in servers if k != MCP_SERVER_NAME]),
    }


def merge_into(path=None, backup=True):
    path = path or mcp_json_path()
    data, err = read_config(path)
    if err:
        return {"ok": False, "error": err, "path": path}
    servers = data["mcpServers"]
    preserved = sorted(k for k in servers if k != MCP_SERVER_NAME)
    existed = MCP_SERVER_NAME in servers
    old_command = servers.get(MCP_SERVER_NAME, {}).get("command", "") if existed else ""
    servers[MCP_SERVER_NAME] = server_entry()
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    backup_path = ""
    tmp = path + ".tmp-dysync"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if backup and os.path.isfile(path):
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = f"{path}.bak-{stamp}"
            n = 1
            while os.path.exists(backup_path):
                backup_path = f"{path}.bak-{stamp}-{n}"
                n += 1
            with open(path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except OSError as e:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return {"ok": False, "error": f"写入失败：{e}", "path": path}
    return {"ok": True, "path": path, "backup": backup_path,
            "action": "更新" if existed else "新增", "old_command": old_command,
            "command": server_entry()["command"],
            "preserved": preserved, "preserved_count": len(preserved)}


def test_connection(timeout=40):
    command, args = current_command()
    argv = [command] + list(args)
    try:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8",
                             errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW)
    except OSError as e:
        return {"ok": False, "error": f"无法启动：{e}"}

    def send(obj):
        p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        p.stdin.flush()

    def recv():
        line = p.stdout.readline()
        return json.loads(line) if line.strip() else None

    result = {"ok": False}
    t0 = time.perf_counter()
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "douyin-fav-sync-settings", "version": VERSION}}})
        init = (recv() or {}).get("result", {})
        result["protocol"] = init.get("protocolVersion", "")
        result["capabilities"] = sorted(init.get("capabilities", {}).keys())
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
        send({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
              "params": {"name": "dy_status", "arguments": {}}})
        r2, r3, r4, r5 = recv() or {}, recv() or {}, recv() or {}, recv() or {}
        tools = [t["name"] for t in r4.get("result", {}).get("tools", [])]
        body = {}
        try:
            body = json.loads(r5["result"]["content"][0]["text"])
        except (ValueError, KeyError, TypeError, IndexError):
            pass
        result["tools"] = tools
        result["resources_ok"] = "resources" in r2.get("result", {})
        result["prompts_ok"] = "prompts" in r3.get("result", {})
        result["ready"] = bool(body.get("ready"))
        result["message"] = body.get("message", "")
        core = {"dy_status", "dy_preflight", "dy_export"}
        result["ok"] = bool(result["protocol"] and "tools" in result["capabilities"]
                            and core.issubset(set(tools))
                            and result["resources_ok"] and result["prompts_ok"])
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    result["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return result
