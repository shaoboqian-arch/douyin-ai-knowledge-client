# -*- coding: utf-8 -*-
"""抖音收藏整理 · 单一入口

    （双击）              主界面：交付目录 + 发布时间范围 → 开始整理
    --setup / 文件名含 Setup  安装向导
    --mcp                 MCP stdio 服务端
    --cli --status        环境状态（JSON）
    --cli --preflight     只读预检（JSON）
    --cli --export        只导出（用已有数据写一批交付，不联网）
    --cli --sync          完整整理（采集 + 重建 + 导出，约 25 分钟）
    --cli --retry --batch 对未完成批次续跑
    --install             静默安装/覆盖升级（--dir 可指定目录）
    --install-headless    构建验证用：只释放文件，不写快捷方式/注册表
    --uninstall           卸载快捷方式与注册表项（不动任何交付数据）
    --version             版本号
"""
import argparse
import ctypes
import json
import os
import sys

import engine
from common import VERSION


def hide_console():
    """只隐藏「自己独占」的控制台。

    从终端里启动时控制台是与终端共享的，隐藏它会把用户的终端窗口一起藏掉；
    单文件 exe 还带着自解压的父进程。所以先数一下挂在这个控制台上的进程数：
    只有 1 个才说明是我们自己的黑框。
    """
    if os.name != "nt":
        return
    try:
        k32 = ctypes.windll.kernel32
        h = k32.GetConsoleWindow()
        if not h:
            return
        arr = (ctypes.c_uint * 4)()
        n = k32.GetConsoleProcessList(arr, 4)
        if n <= 1:
            ctypes.windll.user32.ShowWindow(h, 0)
    except Exception:
        pass


def out(obj):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _progress(text):
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def cli(argv):
    ap = argparse.ArgumentParser(prog="douyin-fav-sync", add_help=True)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--export", action="store_true", help="只导出（不采集、不重建）")
    ap.add_argument("--sync", action="store_true", help="完整整理（采集约 25 分钟）")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--report", action="store_true", help="输出批次的入库报告（JSON）")
    ap.add_argument("--batch", default="")
    ap.add_argument("--dest", default="")
    ap.add_argument("--from", dest="frm", default="")
    ap.add_argument("--to", dest="to", default="")
    ap.add_argument("--project", default="")
    a = ap.parse_args(argv)

    if a.status:
        out(engine.safe_call(engine.status, a.project or None))
        return 0
    if a.preflight:
        r = engine.safe_call(engine.preflight, a.frm, a.to, a.project or None)
        out(r)
        return 0 if r.get("ok") else 1
    if a.export:
        r = engine.safe_call(engine.export_only, a.dest, a.frm, a.to,
                             lambda e: None, _progress, a.project or None)
        out(r)
        return 0 if r.get("ok") else 1
    if a.sync:
        r = engine.safe_call(engine.sync, a.dest, a.frm, a.to,
                             lambda e: None, _progress, None, a.project or None)
        out(r)
        return 0 if r.get("ok") else 1
    if a.retry:
        r = engine.safe_call(engine.retry, a.batch, lambda e: None, _progress)
        out(r)
        return 0 if r.get("ok") else 1
    if a.report:
        import kbreport
        rep = kbreport.load(a.batch)
        if not rep:
            rep = engine.read_state(a.batch).get("report") or {}
        out(rep or {"ok": False, "error": "批次里没有入库报告"})
        return 0 if rep else 1
    out({"ok": False,
         "error": "需要 --status / --preflight / --export / --sync / --retry / --report"})
    return 2


def main():
    argv = sys.argv[1:]
    if "--version" in argv:
        print(VERSION)
        return 0

    if "--selftest" in argv:
        import importlib
        mods, failed = [], []
        for name in ("common", "config", "detect", "pipeline", "subcat", "manifest",
                     "kbreport", "engine", "gui", "settings", "setup_env",
                     "report_ui", "mcp_server", "mcp_config", "installer"):
            try:
                mod = importlib.import_module(name)
                mods.append({"name": name,
                             "version": getattr(mod, "VERSION", VERSION)})
            except Exception as e:
                failed.append({"name": name, "error": f"{type(e).__name__}: {e}"})
        out({"ok": not failed, "version": VERSION, "modules": mods, "failed": failed})
        return 0 if not failed else 1

    if "--mcp" in argv:
        import mcp_server
        return mcp_server.serve()

    if "--install-headless" in argv:
        import installer
        ap = argparse.ArgumentParser()
        ap.add_argument("--dir", required=True)
        a, _ = ap.parse_known_args(argv)
        ok, msg, dest = installer.install(a.dir, no_shortcut=True)
        out({"ok": ok, "message": msg, "dir": dest})
        return 0 if ok else 1

    if "--install" in argv:
        import installer
        ap = argparse.ArgumentParser()
        ap.add_argument("--dir", default="")
        a, _ = ap.parse_known_args(argv)
        ok, msg, dest = installer.install(a.dir.strip() or installer.default_dir())
        out({"ok": ok, "message": msg, "dir": dest, "version": VERSION})
        return 0 if ok else 1

    if "--uninstall" in argv:
        import installer
        ok, msg = installer.uninstall()
        out({"ok": ok, "message": msg})
        return 0

    if "--cli" in argv:
        return cli([x for x in argv if x != "--cli"])

    hide_console()
    from ui_kit import enable_dpi
    enable_dpi()
    if "--settings" in argv:
        import settings
        return settings.open(None)
    basename = os.path.basename(sys.executable)
    if "--setup" in argv or "Setup" in basename or "安装" in basename:
        import installer
        return installer.run()
    import gui
    return gui.run()


if __name__ == "__main__":
    sys.exit(main())
