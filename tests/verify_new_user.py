# -*- coding: utf-8 -*-
"""新用户路径复检：没有设置文件、没有整理结果时的首启 / 初始化 / 首次操作。

覆盖：
  · 首启主按钮是「初始化本机环境」，导出文件夹不可用
  · 初始化页自动填入项目与知识库；未校验账号时完成按钮不可用
  · 校验 → 采用 → 完成 后写盘，主窗口变为就绪
  · 没有 rows_merged 时，导出文件夹给出人话提示而不是路径报错
  · 范围 0 条时全仓同步不启动（二次确认取消）
  · 未安装 Obsidian：开关禁用、关闭知识库后仍可就绪
"""
import json
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402

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


def pump(root, seconds=1.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            root.update()
        except tk.TclError:
            return
        time.sleep(0.05)


def main():
    tmp = tempfile.mkdtemp(prefix="dysync-newuser-")
    os.environ["DYSYNC_SETTINGS"] = os.path.join(tmp, "settings.json")
    os.environ["DYSYNC_PREFS"] = os.path.join(tmp, "prefs.json")
    kb = _fixture.make_kb(tmp)
    project, _rows = _fixture.make_project(tmp)

    import config
    import detect
    import engine
    import gui
    import setup_env

    # 夹具没有真的 .venv/知识库脚本，这里替换掉两处“找文件”的函数，
    # 只验证新用户路径的界面与写盘逻辑（真实探测在 verify_kb 覆盖）。
    orig_resolve = detect.resolve_python
    orig_detect_kb = detect.detect_kb_dir
    detect.resolve_python = lambda project_dir, configured="": sys.executable
    detect.detect_kb_dir = lambda project_dir: kb
    from tkinter import messagebox
    from ui_kit import fonts

    # 消息框全部非阻塞
    seen = {"info": [], "ask": []}
    messagebox.showinfo = lambda *a, **k: seen["info"].append(a)
    messagebox.askyesno = lambda *a, **k: (seen["ask"].append(a), False)[1]

    root = tk.Tk()
    fm, fs, fam = fonts(root)
    app = gui.App(root, fm, fs, fam)
    pump(root, 1.0)
    try:
        print("== 首启 ==")
        check("首次启动按钮为初始化", app.btn.cget("text") == "初始化本机环境",
              app.btn.cget("text"))
        check("首次启动导出文件夹不可用", app.export_btn.cget("state") == "disabled")
        check("状态写明缺少项目目录", "项目目录" in app.state.cget("text"),
              app.state.cget("text"))
        check("项目目录外不再赘述其它缺失",
              "解释器" not in app.state.cget("text"), app.state.cget("text"))
        check("知识库摘要为未建立", "尚未建立知识库" in app.summary.cget("text"),
              app.summary.cget("text"))

        print("== 初始化：自动填入 ==")
        win = setup_env.Setup(tk.Toplevel(root), fm, fs, fam)
        pump(root, 0.3)
        check("初始提示第 1 步", "第 1 步" in win.state.cget("text"), win.state.cget("text"))
        orig = detect.candidate_project_dirs
        detect.candidate_project_dirs = lambda extra=None, deep=False: [project]
        try:
            win.autodetect()
        finally:
            detect.candidate_project_dirs = orig
        pump(root, 0.4)
        check("项目目录已填入", os.path.normpath(win.project.get()) == os.path.normpath(project),
              win.project.get())
        check("知识库随之填入", os.path.normpath(win.kb.get()) == os.path.normpath(kb),
              win.kb.get())
        check("未校验账号时完成不可用", win.done_btn.cget("state") == "disabled")

        print("== 初始化：校验并采用 ==")
        win.probe()
        for _ in range(60):
            pump(root, 0.1)
            if win.probed.get("sec_uid"):
                break
        check("校验拿到账号", win.probed.get("sec_uid") == _fixture.SEC,
              str(win.probed))
        win.adopt()
        pump(root, 0.2)
        check("采用后完成可用", win.done_btn.cget("state") == "normal")
        win.commit()
        pump(root, 0.3)
        saved = config.load()
        check("设置已写盘", saved["project_dir"] == os.path.normpath(project), str(saved))
        check("账号已写盘", saved["expect_sec_uid"] == _fixture.SEC)
        try:
            closed = not win.root.winfo_exists()
        except tk.TclError:
            closed = True
        check("初始化窗口关闭", closed)

        app.refresh_env()
        pump(root, 1.2)
        print("== 就绪后 ==")
        check("主按钮变为全仓同步", app.btn.cget("text") == "⚠️ 全仓同步",
              app.btn.cget("text"))
        check("导出文件夹可用", app.export_btn.cget("state") == "normal")
        check("状态显示就绪", "已就绪" in app.state.cget("text"), app.state.cget("text"))

        print("== 首次提示 ==")
        check("已有数据时不显示首启提示", not app.first_hint.winfo_manager(),
              app.first_hint.cget("text"))
        check("导出文件夹此时可用", app.export_btn.cget("state") == "normal")

        print("== 首次放数据前 ==")
        app.frm.delete(0, "end"); app.frm.insert(0, "2026-11-01")
        app.to.delete(0, "end"); app.to.insert(0, "2026-11-30")
        app._update_range_hint()
        pump(root, 0.8)        # 范围预检现在跑在后台线程，等结果回主线程
        check("范围提示按数据实算", "范围内" in app.range_hint.cget("text"),
              app.range_hint.cget("text"))

        print("== 范围 0 条不启动 ==")
        app.frm.delete(0, "end"); app.frm.insert(0, "2020-01-01")
        app.to.delete(0, "end"); app.to.insert(0, "2020-01-02")
        app.start()
        pump(root, 0.3)
        check("取消确认后不进入忙碌", app.busy is False)
        check("确实弹过二次确认", len(seen["ask"]) >= 1, str(seen["ask"]))

        print("== 没有整理结果时导出文件夹 ==")
        empty = tempfile.mkdtemp(prefix="dysync-empty-")
        empty_project, _ = _fixture.make_project(empty)
        os.remove(os.path.join(empty_project, "work", "rows_merged.json"))
        cfg = config.load()
        cfg["project_dir"] = os.path.normpath(empty_project)
        cfg["python"] = sys.executable
        config.save(cfg)
        r = engine.export_only(os.path.join(empty, "out"))
        check("给出人话提示", r.get("ok") is False and "还没有整理结果" in r.get("error", ""),
              str(r)[:160])
        app.refresh_env()
        deadline = time.time() + 5
        while time.time() < deadline and app.rows_ok:
            pump(root, 0.05)
        pump(root, 0.2)
        check("无整理结果时显示首启提示", bool(app.first_hint.winfo_manager()),
              app.first_hint.cget("text"))
        check("首启提示说明先做全仓同步",
              "全仓同步" in app.first_hint.cget("text"), app.first_hint.cget("text"))
        check("无整理结果时导出文件夹禁用", app.export_btn.cget("state") == "disabled")

        print("== 未安装 Obsidian ==")
        orig_find = detect.find_obsidian
        detect.find_obsidian = lambda *_a, **_k: ""
        try:
            cfg = config.load()
            cfg["kb_enabled"] = True
            cfg["kb_dir"] = kb
            config.save(cfg)
            st = engine.status()
            check("没装 Obsidian 仍可就绪（Markdown 照写）",
                  st["ready"] is True, str(st.get("missing")))
            check("状态提示未装 Obsidian",
                  any("Obsidian" in w for w in st.get("warnings") or []), str(st.get("warnings")))
            cfg["kb_enabled"] = False
            cfg["kb_dir"] = os.path.join(tmp, "不存在的库")
            config.save(cfg)
            st2 = engine.status()
            check("关掉知识库后缺库也不影响", st2["ready"] is True, str(st2.get("missing")))
            sw = setup_env.Setup(tk.Toplevel(root), fm, fs, fam)
            pump(root, 0.2)
            check("未装 Obsidian 时复选框禁用",
                  "disabled" in str(sw.kb_switch.cget("state")) or not sw.kb_switch._enabled,
                  str(sw.kb_switch.cget("state")))
            sw.root.destroy()
        finally:
            detect.find_obsidian = orig_find
    finally:
        detect.resolve_python = orig_resolve
        detect.detect_kb_dir = orig_detect_kb
        try:
            root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        for k in ("DYSYNC_SETTINGS", "DYSYNC_PREFS"):
            os.environ.pop(k, None)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
