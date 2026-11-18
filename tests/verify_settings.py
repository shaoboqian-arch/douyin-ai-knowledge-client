# -*- coding: utf-8 -*-
"""设置页与 MCP 配置写入：合并保留、备份、幂等、损坏拒写、真实握手、设置窗口。

用法: python tests/verify_settings.py [轮次名]
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402

FAILS = []
PASS = 0
ROUND = sys.argv[1] if len(sys.argv) > 1 else "本轮"


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="dysync-settings-")
    kb = _fixture.make_kb(tmp)
    project, _rows = _fixture.make_project(tmp)
    settings_file = _fixture.configure(tmp, project, kb)
    os.environ["DYSYNC_SETTINGS"] = settings_file

    import config
    import mcp_config as mc

    print("== 配置往返 ==")
    cfg = config.load()
    check("项目目录落盘", cfg["project_dir"] == project)
    check("账号落盘", cfg["expect_sec_uid"] == _fixture.SEC)
    check("没有 cookie 字段", "cookie" not in cfg, str(list(cfg)))
    check("条数下限字段已移除", "min_count" not in cfg, str(list(cfg)))
    config.save(cfg)
    check("配置往返可保存", config.load()["project_dir"] == project)

    print("== MCP 配置合并 ==")
    mcp_path = os.path.join(tmp, "mcp.json")
    with open(mcp_path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"keep-a": {"type": "stdio", "command": "a"},
                                  "keep-b": {"type": "stdio", "command": "b"}}},
                  f, ensure_ascii=False)
    r = mc.merge_into(mcp_path)
    check("写入成功", r.get("ok"), str(r)[:200])
    check("动作是新增", r.get("action") == "新增")
    check("保留其他 2 个连接器", r.get("preserved_count") == 2, str(r.get("preserved")))
    check("备份文件已生成", r.get("backup") and os.path.isfile(r["backup"]))
    data = json.load(open(mcp_path, encoding="utf-8"))
    check("三个键都在", set(data["mcpServers"]) == {"keep-a", "keep-b", "douyin-fav-sync"})
    check("条目是 stdio + --mcp", data["mcpServers"]["douyin-fav-sync"]["type"] == "stdio"
          and data["mcpServers"]["douyin-fav-sync"]["args"][-1] == "--mcp")

    before = json.dumps(data, sort_keys=True)
    r2 = mc.merge_into(mcp_path)
    after = json.dumps(json.load(open(mcp_path, encoding="utf-8")), sort_keys=True)
    check("重复写入幂等", r2.get("action") == "更新" and after == before, r2.get("action", ""))

    print("== 损坏配置拒写 ==")
    bad = os.path.join(tmp, "bad.json")
    open(bad, "w", encoding="utf-8").write("{broken")
    r3 = mc.merge_into(bad)
    check("解析失败不写", not r3.get("ok") and "解析失败" in r3.get("error", ""), str(r3)[:150])
    check("坏文件原样保留", open(bad, encoding="utf-8").read() == "{broken")

    print("== 真实握手 ==")
    tr = mc.test_connection(timeout=40)
    check("握手通过", tr.get("ok"), str(tr)[:300])
    check("协议 2025-06-18", tr.get("protocol") == "2025-06-18", str(tr.get("protocol")))
    check("工具 6 个", len(tr.get("tools") or []) == 6, str(tr.get("tools")))
    check("dy_status ready", tr.get("ready") is True, str(tr.get("message")))

    print("== 设置窗口 ==")
    try:
        import tkinter as tk
    except ImportError:
        print("  SKIP  设置窗口（本环境没有 tkinter，未装系统包强跑 GUI）")
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
        for name, detail in FAILS:
            print(f"  FAIL  {name}  {detail}")
        return 1 if FAILS else 0
    import settings as settings_ui
    from ui_kit import fonts
    root = tk.Tk()
    fm, fs, family = fonts(root)
    win = settings_ui.Settings(root, fm, fs, family)
    root.update()
    check("设置窗口可打开", win.root.winfo_exists() == 1)
    check("显示 4 个路径/账号字段", win.project.get() == project and win.kb.get() == kb)
    check("账号显示为昵称+掩码", "测试账号" in win.account.get()
          and "…" in win.account.get(), win.account.get())
    check("MCP 预览含服务名", "douyin-fav-sync" in win.preview.get("1.0", "end"))
    check("知识库开关存在", hasattr(win, "kb_switch"))

    # 同一行控件不得重叠（V0.1.2 发现「自动发现/浏览」被放进同一格）
    def bbox(widget):
        return (widget.winfo_rootx(), widget.winfo_rooty(),
                widget.winfo_rootx() + widget.winfo_width(),
                widget.winfo_rooty() + widget.winfo_height())

    def overlap(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    project_row = [win.project]
    for child in win.project.master.winfo_children():
        try:
            text = child.cget("text")
        except Exception:
            continue
        if text in ("自动发现", "浏览…"):
            project_row.append(child)
    bad = [(a, b) for i, a in enumerate(project_row) for b in project_row[i + 1:]
           if overlap(bbox(a), bbox(b))]
    check("项目目录行控件不重叠", not bad,
          str([(getattr(a, "cget", lambda *_: "?")(), getattr(b, "cget", lambda *_: "?" )())
               for a, b in bad]))
    check("Obsidian 状态已显示", "Obsidian" in win.obs_state.cget("text"),
          win.obs_state.cget("text"))
    out = os.path.join(APP, "验证输出")
    os.makedirs(out, exist_ok=True)
    shot = os.path.join(out, f"设置页-{ROUND}.png")
    try:
        import ctypes
        from PIL import ImageGrab
        win.root.lift()
        win.root.attributes("-topmost", True)
        root.update()
        time.sleep(0.4)
        hwnd = ctypes.windll.user32.GetParent(win.root.winfo_id()) or win.root.winfo_id()
        try:
            img = ImageGrab.grab(window=hwnd)
        except Exception:
            x, y = win.root.winfo_rootx(), win.root.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + win.root.winfo_width(),
                                       y + win.root.winfo_height()))
        img.save(shot)
        win.root.attributes("-topmost", False)
        check("设置页截图已保存", os.path.isfile(shot) and os.path.getsize(shot) > 5000)
    except Exception as e:
        check("设置页截图已保存", False, f"{type(e).__name__}: {e}")
    win.root.destroy()

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
