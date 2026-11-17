# -*- coding: utf-8 -*-
"""界面复检：常驻元素、进度表渲染、对比度、键盘可达、截图。

用法: python tests/verify_ui.py [轮次名]
"""
import os
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
ROUND = sys.argv[1] if len(sys.argv) > 1 else "本轮"


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def texts(widget):
    out = []
    try:
        for w in widget.winfo_children():
            try:
                t = w.cget("text")
                if isinstance(t, str) and t.strip():
                    out.append(t)
            except tk.TclError:
                pass
            out.extend(texts(w))
    except tk.TclError:
        pass
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="dysync-ui-")
    kb = _fixture.make_kb(tmp)
    project, _rows = _fixture.make_project(tmp)
    os.environ["DYSYNC_SETTINGS"] = _fixture.configure(tmp, project, kb)

    import common
    import gui
    import ui_kit
    from common import APP_NAME, PHASES, VERSION

    print("== 配色对比度（WCAG AA）==")
    for name, fg, bg, need in (
            ("正文/底色", ui_kit.TEXT, ui_kit.BG, 4.5),
            ("辅助字/底色", ui_kit.MUTED, ui_kit.BG, 4.5),
            ("辅助字/面板", ui_kit.MUTED, ui_kit.SURFACE, 4.5),
            ("主按钮字/品牌红", ui_kit.ON_ACCENT, ui_kit.ACCENT, 4.5),
            ("主按钮悬停", ui_kit.ON_ACCENT, ui_kit.ACCENT_HI, 4.5),
            ("完成态字/完成底", ui_kit.CYAN, ui_kit.DONE_BG, 4.5),
            ("错误字/错误底", ui_kit.ERR, ui_kit.ERR_BG, 4.5),
            ("错误字/底色", ui_kit.ERR, ui_kit.BG, 4.5)):
        ratio = ui_kit.contrast(fg, bg)
        check(f"{name} {ratio}:1 ≥ {need}", ratio >= need, str(ratio))

    root = tk.Tk()
    ui_kit.apply_theme(root)
    fm, fs, family = ui_kit.fonts(root)
    app = gui.App(root, fm, fs, family)
    root.update()
    time.sleep(0.25)
    root.update()

    print("== 常驻元素 ==")
    check("窗口标题含应用名与版本", APP_NAME in root.title() and VERSION in root.title(), root.title())
    check("窗口宽度 640", root.winfo_width() >= 640, str(root.winfo_width()))
    vis = texts(root)
    for label in ("交付到", "发布时间", "开始整理", "设置"):
        check(f"常驻元素存在：{label}", label in vis, str(vis[:12]))
    check("没有标语式长文案", not any(len(t) > 40 for t in vis if t not in ("ⓘ",)),
          str([t for t in vis if len(t) > 40][:3]))
    check("初始不展开进度表", not app.panel_visible)
    check("初始无提示块", not app.hint_visible)
    check("初始按钮为开始整理", app.btn.cget("text") == "开始整理")

    print("== 进度表渲染 ==")
    app.show_panel()
    root.update()
    check("阶段徽标 6 个", len(app.badges) == len(PHASES))
    app.set_phase("collect")
    root.update()
    check("进行中阶段高亮", app.badges["collect"]._mode == "now")
    check("已过阶段为完成态", app.badges["check"]._mode == "done")
    check("未来阶段为待办态", app.badges["export"]._mode == "pending")

    app.handle_event({"type": "plan", "total": 4})
    for i, (group, ai, ok) in enumerate((("video", True, True), ("video", False, True),
                                        ("album", True, False), ("video", False, False))):
        app.handle_event({"type": "item", "item": {"group": group, "ai": ai, "ok": ok}})
    app.handle_event({"type": "gap", "gap": {"标题": "缺介绍的一条", "原因": "缺百字介绍"}})
    app.refresh_table()
    root.update()
    check("视频计数 3", app.stats["video"]["total"] == 3, str(app.stats["video"]))
    check("图集计数 1", app.stats["album"]["total"] == 1)
    check("AI 子集计数 2", app.stats["ai"]["total"] == 2, str(app.stats["ai"]))
    check("待加工行数 1", len(app.gaps) == 1)
    check("待加工标题写入表格", app.gap_title.cget("text") == "待加工 1",
          app.gap_title.cget("text"))
    check("进度条推进到 4/4", app.prog._value == 4 and app.prog._maximum == 4,
          f"{app.prog._value}/{app.prog._maximum}")

    app.set_phase("done")
    root.update()
    check("完成态全部阶段为 done", all(b._mode == "done" for b in app.badges.values()))

    print("== 键盘可达 ==")
    fired = {"n": 0}
    app.btn.configure(command=lambda: fired.update(n=fired["n"] + 1))
    app.btn.focus_force()
    root.update()
    app.btn.event_generate("<space>")
    root.update()
    check("主按钮空格可触发", fired["n"] == 1, str(fired))
    check("状态行在 Tab 序列", int(app.state.cget("takefocus") or 0) == 1)

    print("== 截图 ==")
    out_dir = os.path.join(APP, "验证输出")
    os.makedirs(out_dir, exist_ok=True)
    shot = os.path.join(out_dir, f"界面-主窗口-{ROUND}.png")
    try:
        from PIL import ImageGrab
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(shot)
        check("截图已保存", os.path.isfile(shot) and os.path.getsize(shot) > 5000,
              shot)
    except Exception as e:
        check("截图已保存", False, f"{type(e).__name__}: {e}")

    root.destroy()
    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
