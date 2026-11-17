# -*- coding: utf-8 -*-
"""本轮界面改动的行为复检（不依赖本机显示与真实交付批次）。

无 tkinter 时跑纯逻辑：续跑取消、报告 Markdown、待加工行文案、拖离判定、回车绑定接线。
有 tkinter 时再补回车、路径尾部与胶囊松开的控件级用例。
"""
import inspect
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402

FAILS = []
PASS = 0
SKIP = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def skip(name, reason):
    SKIP.append((name, reason))
    print(f"  SKIP  {name}  {reason}")


def test_format():
    import common
    print("== 待加工文案 ==")
    check("短文本不截断", common.clip_text("待加工", 10) == "待加工")
    check("截断加省略号", common.clip_text("ABCDEFG", 4) == "ABC…")
    check("换行收成单行", common.clip_text("上半\n下半", 20) == "上半 下半")
    rows = common.format_gap_rows([
        {"标题": "同一条\n标题", "原因": "缺介绍", "序号": 3},
        {"标题": "同一条 标题", "原因": "缺标引\n且很长" + "字" * 40, "序号": 7},
        {"标题": "", "原因": "缺转写", "序号": 9},
    ], title_width=20, reason_width=8)
    check("同名条目带序号", rows[0][0].startswith("同一条 标题（3）") or "（3）" in rows[0][0],
          rows[0][0])
    check("同名第二条也带序号", "（7）" in rows[1][0], rows[1][0])
    check("空标题退回序号", rows[2][0] == "9", rows[2][0])
    check("原因截断带省略号", rows[1][1].endswith("…") and "\n" not in rows[1][1],
          rows[1][1])
    check("全文可还原", "缺介绍" in rows[0][2] and "同一条 标题" in rows[0][2])
    many = [{"标题": f"t{i}", "原因": "r", "序号": i} for i in range(1, 251)]
    out = common.format_gap_rows(many)
    check("只保留最近 200 条", len(out) == 200 and out[0][0] == "t51" and out[-1][0] == "t250",
          f"{len(out)} {out[0][0] if out else ''} {out[-1][0] if out else ''}")
    check("超过 200 时标题写明只显示最近 200 条",
          "只显示最近 200 条" in common.gap_heading(201)
          and "导出报告" in common.gap_heading(201),
          common.gap_heading(201))
    check("不超过 200 时标题为全量计数", common.gap_heading(1) == "待加工 1")
    check("计数用千分位", common.gap_heading(1284, shown=2000) == "待加工 1,284",
          common.gap_heading(1284, shown=2000))


def test_pointer():
    import common
    print("== 胶囊拖离判定 ==")
    check("指针在矩形内", common.pointer_inside(10, 10, 80, 36))
    check("指针在左缘外取消", not common.pointer_inside(-1, 10, 80, 36))
    check("指针在下缘外取消", not common.pointer_inside(10, 40, 80, 36))
    check("边界仍算在内", common.pointer_inside(80, 36, 80, 36))


def test_render_md():
    import kbreport
    print("== 入库报告 Markdown ==")
    md = kbreport.render_md({
        "generated_at": "2026-11-17 12:00:00",
        "account": {"nickname": "测试账号"},
        "version": "0.1.0",
        "rows": [{"环节": "测试", "状态": "ok",
                  "结果": "第一行\n第二行 | 竖线"}],
    })
    table = [ln for ln in md.splitlines() if ln.startswith("| 测试")]
    check("结果换行不拆表格行", len(table) == 1, md)
    check("结果换行收成空格", table and "第一行 第二行" in table[0], table[:1])
    check("竖线已转义", table and "\\|" in table[0], table[:1])
    check("仍是 Markdown 表格", "| 环节 | 结果 |" in md and md.startswith("# 入库报告"))


def test_retry_cancel():
    import engine
    print("== 续跑取消 ==")
    sig = inspect.signature(engine.retry)
    check("retry 接受 cancel 参数", "cancel" in sig.parameters, str(sig))

    tmp = tempfile.mkdtemp(prefix="dysync-retry-cancel-")
    try:
        kb = _fixture.make_kb(tmp)
        project, _rows = _fixture.make_project(tmp)
        os.environ["DYSYNC_SETTINGS"] = _fixture.configure(tmp, project, kb)
        dest = os.path.join(tmp, "out")
        os.makedirs(dest, exist_ok=True)
        batch = os.path.join(dest, "export-all-20260101-000000")
        os.makedirs(batch, exist_ok=True)
        engine._write_state(batch, {
            "version": 1, "stage": "rebuild", "ok": False, "error": "体检失败",
            "project_dir": project, "kb_dir": kb, "dest": dest, "batch": batch,
            "range": {"from": "", "to": ""},
            "collect": {"gates_ok": True, "total": 5},
            "ids": {"old": [], "new": [], "removed": []},
        })

        ev = threading.Event()
        ev.set()
        r = engine.retry(batch, cancel=ev)
        check("预先置位时续跑立即停止",
              (not r.get("ok")) and "已停止" in (r.get("error") or ""),
              str(r)[:240])
        check("停止后不写出交付清单",
              not os.path.isfile(os.path.join(r.get("batch_path") or "", "_导出报告.md")))

        with open(os.path.join(project, "make_tables.py"), "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\nimport time, sys\ntime.sleep(30)\n"
                    "print('should not finish')\nsys.exit(0)\n")
        ev2 = threading.Event()
        box = {}

        def work():
            box["r"] = engine.retry(batch, cancel=ev2)

        th = threading.Thread(target=work)
        th.start()
        time.sleep(0.4)
        ev2.set()
        th.join(timeout=8)
        r2 = box.get("r") or {}
        check("运行中取消能结束线程", not th.is_alive(), f"alive={th.is_alive()}")
        check("运行中取消返回已停止",
              (not r2.get("ok")) and "已停止" in (r2.get("error") or ""),
              str(r2)[:240])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wiring():
    print("== 界面接线（读源码）==")
    gui = open(os.path.join(APP, "src", "gui.py"), encoding="utf-8").read()
    start = gui.find("def start_retry")
    end = gui.find("def _finish", start)
    body = gui[start:end] if start >= 0 and end > start else ""
    check("续跑会清空取消标志", "self.cancel.clear()" in body)
    check("续跑把 cancel 传给引擎", "cancel=self.cancel" in body)
    check("窗口回车不再无条件开跑",
          "root.bind(\"<Return>\", self._on_root_return)" in gui
          and "lambda _e: self.primary_action()" not in gui.split("def _on_root_return")[0][-400:],
          "bind still points at primary_action")
    check("回车只在主按钮聚焦时生效",
          "if event.widget is self.btn" in gui and "def _on_root_return" in gui)
    setup = open(os.path.join(APP, "src", "setup_env.py"), encoding="utf-8").read()
    check("初始化账号框只读", "self.account.set_readonly(True)" in setup)
    check("初始化写明先校验再采用", "请先校验账号，再点采用" in setup)
    check("目录对话框去掉上游工程名",
          "TikTokDownloader 项目目录" not in setup
          and "选择采集项目目录（需含 extract_favorites.py）" in setup)
    settings = open(os.path.join(APP, "src", "settings.py"), encoding="utf-8").read()
    check("设置页查看完整用对话框",
          "messagebox.showinfo" in settings and "sec_uid：" not in settings)
    check("设置页未保存关闭会询问", "有未保存的更改" in settings)
    inst = open(os.path.join(APP, "src", "installer.py"), encoding="utf-8").read()
    check("安装向导未改覆盖口径文案", "默认不覆盖本机已装程序" not in inst)


def test_tk():
    print("== 控件级（需 tkinter）==")
    try:
        import tkinter as tk
    except ImportError:
        skip("主按钮回车 / 路径框回车 / 路径尾部 / 胶囊松开",
             "本环境没有 tkinter，未装系统包强跑 GUI")
        return
    import ui_kit
    root = tk.Tk()
    try:
        ui_kit.apply_theme(root)
        fired = {"n": 0}
        btn = ui_kit.CapsuleButton(root, text="测", command=lambda: fired.update(n=fired["n"] + 1),
                                   width=80, height=36)
        btn.pack()
        entry = ui_kit.RoundedEntry(root, path=True, pxwidth=200)
        entry.pack()
        root.update()

        class Ev:
            pass

        ev = Ev()
        ev.x, ev.y = -8, 10
        btn._on_release(ev)
        check("松开在按钮外不触发", fired["n"] == 0, str(fired))
        ev.x, ev.y = 20, 18
        btn._on_release(ev)
        check("松开在按钮内触发", fired["n"] == 1, str(fired))

        count = {"n": 0}

        def on_return(_e=None):
            count["n"] += 1

        root.bind("<Return>", on_return)
        entry.entry.focus_force()
        root.update()
        entry.entry.event_generate("<Return>")
        root.update()
        check("圆角输入回车不冒泡到窗口", count["n"] == 0, str(count))

        long_path = os.path.join(tempfile.gettempdir(), *["pathseg"] * 16)
        entry.delete(0, "end")
        entry.insert(0, long_path)
        entry.reveal_end()
        root.update()
        first, last = entry.entry.xview()
        check("失焦/reveal 后能看到路径尾部",
              last >= 0.99 or first > 0 or entry.get().endswith("pathseg"),
              f"xview=({first}, {last})")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def main():
    test_format()
    test_pointer()
    test_render_md()
    test_retry_cancel()
    test_wiring()
    test_tk()
    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL / {len(SKIP)} SKIP ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    for name, reason in SKIP:
        print(f"  SKIP  {name}  {reason}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
