# -*- coding: utf-8 -*-
"""V0.1.6 缺陷闭环门禁（run_all 第 15 步）：F-1~F-12 逐条回归。

与「审计一致性」互补：这里尽量用离线夹具／Tk 实证跑出行为，
而不是只 grep 源码。只读，不碰真实项目、设置、注册表、桌面快捷方式。
"""
import json
import os
import re
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
import config  # noqa: E402
import detect  # noqa: E402
import engine  # noqa: E402
import installer  # noqa: E402
import kbreport  # noqa: E402
import pipeline  # noqa: E402
import ui_kit  # noqa: E402
from common import DeferredCall, VERSION  # noqa: E402

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


def read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


OLD_LINE = 'print("[self-profile] 账号: 测试账号  sec_uid: " + SEC, flush=True)'
SEC = _fixture.SEC


def sync_case(log_line):
    """把夹具采集脚本的自述行换掉，跑一次完整 sync，返回 (ok, error)。"""
    tmp = tempfile.mkdtemp(prefix="dysync-f016-")
    try:
        kb = _fixture.make_kb(tmp)
        project, _rows = _fixture.make_project(tmp)
        p = os.path.join(project, "extract_favorites.py")
        src = open(p, encoding="utf-8").read()
        assert OLD_LINE in src, "夹具自述行变了，测试需同步更新"
        open(p, "w", encoding="utf-8").write(
            src.replace(OLD_LINE, "print(" + repr(log_line) + ", flush=True)"))
        os.environ["DYSYNC_SETTINGS"] = _fixture.configure(tmp, project, kb)
        os.environ["FAKE_NEW"] = "1"
        r = engine.sync(os.path.join(tmp, "out"))
        return bool(r.get("ok")), str(r.get("error") or "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_f1():
    print("== F-1 账号硬门 fail-closed ==")
    ok, err = sync_case(f"[self-profile] 账号: 测试账号  sec_uid: {SEC}")
    check("正常日志仍可完成", ok, err)
    for label, line in (
        ("日志格式变化（无 sec_uid）", "[self-profile] 账号: 换号了"),
        ("sec_uid 为空串", "[self-profile] 账号: 换号了  sec_uid: "),
    ):
        ok, err = sync_case(line)
        check(f"{label} → 中止", not ok and "账号无法核对" in err, f"ok={ok} err={err}")
    ok, err = sync_case(f"[self-profile] 账号: 别的号  sec_uid: MS4wOTHER000000000000000000000000000000000")
    check("账号不符 → 中止", not ok and "账号不符" in err, f"ok={ok} err={err}")
    ok, err = sync_case(f"[self-profile] sec_uid={SEC}")
    check("上游改写成 sec_uid= 仍能认出", ok, err)
    cases = [
        ("[self-profile] 账号: 测试账号  sec_uid: " + SEC, SEC, "测试账号"),
        ('{"nickname": "测试账号", "sec_uid": "' + SEC + '"}', SEC, "测试账号"),
        ("[self-profile] 账号: 换号了", "", "换号了"),
        ("[self-profile] 账号: 换号了  sec_uid: ", "", "换号了"),
    ]
    for line, sec, nick in cases:
        got = pipeline.scan_stdout([line, "[collect] 共获取 3 条收藏"])
        check(f"scan_stdout 解析 {line[:28]}",
              got["account"]["sec_uid"] == sec and got["account"]["nickname"] == nick
              and got["total"] == 3, str(got))
    src = read("src/engine.py")
    check("sync 里不再有 fail-open 分支",
          "if expect and acct.get(\"sec_uid\")" not in src and
          'identity_reason": "sec_uid_missing"' in src)

    # 旧批次（V0.1.5 的 gates_ok=True / matched=False）不能靠续跑绕过
    tmp = tempfile.mkdtemp(prefix="dysync-f016-retry-")
    try:
        batch = os.path.join(tmp, "batch")
        os.makedirs(batch)
        engine._write_state(batch, {
            "stage": "rebuild", "collect": {
                "gates_ok": True,
                "account": {"nickname": "旧账号", "matched": False}},
            "range": {}, "dest": tmp, "ids": {}})
        r = engine.retry(batch)
        check("V0.1.5 未核对身份的批次禁止续跑",
              not r.get("ok") and "身份未通过核对" in str(r.get("error")), str(r)[:120])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_f2():
    print("== F-2 续跑报告不伪称身份 ==")
    tmp = tempfile.mkdtemp(prefix="dysync-f016-f2-")
    try:
        kb = _fixture.make_kb(tmp)
        project, _ = _fixture.make_project(tmp)
        for matched, want_words, want_state in ((False, "未复核", kbreport.WARN),
                                                (True, "匹配", kbreport.OK)):
            collect = {"account": {"nickname": "沿用", "matched": matched},
                       "total": 3, "scope": {}}
            rep = kbreport.build(project, kb, {"min_count": 0}, collect,
                                 {"new": [], "removed": [], "old": []},
                                 _fixture.ROWS, [], {"1001": ["提示词工程"]},
                                 audit_rc=0, audit_lines=[], kb_enabled=True,
                                 mode="retry")
            row = rep["rows"][0]
            check(f"retry matched={matched} 身份如实",
                  want_words in row["结果"] and row["状态"] == want_state,
                  f"{row['结果']} / {row['状态']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deferred(root):
    print("== F-3 / F-9 后台调用不占 UI 线程 ==")
    if root is None:
        print("  SKIP  Tk 不可用")
        return
    main_tid = threading.get_ident()
    seen = {}
    q = DeferredCall(root,
                     lambda v: (seen.setdefault("tid", threading.get_ident()),
                                time.sleep(0.12), {"ok": True, "v": v})[-1],
                     lambda r: seen.setdefault("result", r))
    t0 = time.perf_counter()
    q.run("x")
    blocked_ms = (time.perf_counter() - t0) * 1000
    check("run() 立即返回（不阻塞主线程）", blocked_ms < 30, f"{blocked_ms:.1f} ms")
    deadline = time.time() + 3
    while "result" not in seen and time.time() < deadline:
        root.update()
        time.sleep(0.01)
    check("结果回主线程回调", seen.get("result", {}).get("v") == "x", str(seen))
    check("函数确实跑在后台线程", seen.get("tid") not in (None, main_tid),
          f"tid={seen.get('tid')} main={main_tid}")
    q.destroy()
    src_gui, src_set = read("src/gui.py"), read("src/settings.py")
    hint_fn = re.search(r"    def _update_range_hint\(self\):(.*?)\n    def ",
                        src_gui, re.S)
    check("gui 范围提示不再同步预检",
          bool(hint_fn) and "engine.preflight" not in hint_fn.group(1)
          and "self._range_call.run(frm, to)" in hint_fn.group(1)
          and "DeferredCall(root, engine.preflight" in src_gui,
          "防抖回调内仍有同步调用")
    check("点击动作复用预检缓存",
          src_gui.count("self._preflight_cached(frm, to)") == 2
          and src_gui.count("engine.safe_call(engine.preflight") == 1)
    check("settings 不再同步调用 engine_status",
          'stats = (engine_status() or {}).get("kb_stats")' not in src_set
          and "DeferredCall(root, engine_status" in src_set)
    check("窗口销毁会取消后台轮询",
          "_range_call.destroy()" in src_gui and "_status_call.destroy()" in src_set)


def test_f4(root):
    print("== F-4 键盘自动重复 ==")
    if root is None:
        print("  SKIP  Tk 不可用")
        return
    fired = {"n": 0}
    btn = ui_kit.CapsuleButton(root, text="测试", width=120, height=32,
                               command=lambda: fired.update(n=fired["n"] + 1))
    btn.pack()
    btn.focus_set()
    root.update()
    for _ in range(6):
        btn.event_generate("<space>")
        root.update()
    check("长按 6 次 keydown 只触发 1 次", fired["n"] == 1, str(fired))
    btn.event_generate("<KeyRelease-space>")
    root.update()
    btn.event_generate("<space>")
    root.update()
    check("松开后再按可再次触发", fired["n"] == 2, str(fired))
    btn.destroy()


def test_f5_f12():
    print("== F-5 / F-12 非文本对比度 ==")
    kit = read("src/ui_kit.py")
    check("深薄荷 token 存在", 'MINT_DEEP = "#0b6f66"' in kit)
    for name, bg, need in (("日历箭头 hover / SAND", ui_kit.SAND, 3.0),
                           ("进度条 / TRACK", ui_kit.TRACK, 3.0),
                           ("进度条 / BG", ui_kit.BG, 3.0),
                           ("进度条 / PAPER", ui_kit.PAPER, 3.0)):
        v = ui_kit.contrast(ui_kit.MINT_DEEP, bg)
        check(f"{name} ≥ {need}:1", v >= need, f"{v}:1")
    check("箭头 hover 用深薄荷", "configure(bg=SAND, fg=MINT_DEEP)" in kit)
    check("进度条两处填充都换深薄荷",
          kit.count("fill=MINT_DEEP, outline=\"\"") >= 2,
          str(kit.count("fill=MINT_DEEP")))
    check("MINT 仍用于主按钮（主题不回退）", "MINT =" in kit and "TRACK =" in kit)


def test_f6_f7(root):
    print("== F-6 / F-7 日历键盘与回调 ==")
    if root is None:
        print("  SKIP  Tk 不可用")
        return
    entry = ui_kit.RoundedEntry(root, width=160)
    entry.pack()
    picked = {"n": 0}
    p = ui_kit.DatePicker(entry, on_pick=lambda: picked.update(n=picked["n"] + 1))
    root.update()

    class E:
        def __init__(self, detail):
            self.detail = detail

    p.open()
    root.update()
    check("弹层可打开", p.win is not None)
    p._on_focus_out(E("NotifyInferior"))
    root.update()
    check("内部焦点转移不关弹层", p.win is not None)
    p._on_tab()
    root.update()
    check("Tab 到「清除 / 回到不限」且弹层仍在",
          p.win is not None and p.win.focus_get() is p._clear_btn,
          f"win={p.win} focus={p.win.focus_get() if p.win else None}")

    entry.delete(0, "end")
    entry.insert(0, "2026-11-17")
    p._clear()
    root.update()
    check("清除后回调 on_pick", picked["n"] == 1 and entry.get().strip() == "",
          f"n={picked['n']} text={entry.get()!r}")
    import datetime as dt
    p.open()
    p._pick(dt.date(2026, 11, 18))
    root.update()
    check("选日期也回调 on_pick（对照组）", picked["n"] == 2, str(picked))

    p.open()
    other = tk.Toplevel(root) if (tk := sys.modules.get("tkinter")) else None
    if other is not None:
        e2 = tk.Entry(other)
        e2.pack()
        e2.focus_set()
        root.update()
        p._on_focus_out(E("NotifyNonlinear"))
        root.update()
        check("真正失焦到外部窗口会关弹层", p.win is None)
        other.destroy()
    p.close()
    entry.destroy()
    kit = read("src/ui_kit.py")
    check("FocusOut 不再是裸 lambda close",
          'self.win.bind("<FocusOut>", lambda _e: self.close())' not in kit
          and "def _on_focus_out(self, event=None)" in kit)
    check("清除与选日共用回调", kit.count("self._notify_pick()") >= 2)


def test_f8():
    print("== F-8 安装路径单引号与失败可见 ==")
    check("单引号被转义",
          installer._ps_quote(r"C:\O'Brien\x") == "'C:\\O''Brien\\x'",
          installer._ps_quote(r"C:\O'Brien\x"))
    captured = []
    orig = installer._ps
    installer._ps = lambda s: (captured.append(s) or (0, ""))
    try:
        installer.make_shortcut(r"C:\O'Brien\a.lnk", r"C:\O'Brien\a.exe", r"C:\O'Brien")
        s = captured[0]
        check("生成的 PS 脚本路径不含裸单引号",
              "CreateShortcut('C:\\O''Brien\\a.lnk')" in s and
              "TargetPath = 'C:\\O''Brien\\a.exe'" in s,
              s.splitlines()[1])
    finally:
        installer._ps = orig

    tmp = tempfile.mkdtemp(prefix="dysync-f016-f8-")
    saved = (installer.make_shortcut, installer.write_uninstall_item,
             installer.desktop_dir, installer.start_menu_dir, installer.is_frozen)
    try:
        installer.make_shortcut = lambda *a: False
        installer.write_uninstall_item = lambda *a: False
        installer.desktop_dir = lambda: os.path.join(tmp, "desktop")
        installer.start_menu_dir = lambda: os.path.join(tmp, "menu")
        installer.is_frozen = lambda: False
        ok, msg, _ = installer.install(os.path.join(tmp, "dest"))
        check("附属项失败不再静默报「已安装」",
              ok and "未完成" in msg and msg != "已安装", f"ok={ok} msg={msg}")
    finally:
        (installer.make_shortcut, installer.write_uninstall_item,
         installer.desktop_dir, installer.start_menu_dir, installer.is_frozen) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    # 覆盖升级：旧 .lnk 被系统保护到不可写，但仍指向本版 exe → 视为已就位
    import base64
    tmp2 = tempfile.mkdtemp(prefix="dysync-f016-f8b-")
    saved2 = (installer.make_shortcut, installer.write_uninstall_item,
              installer.desktop_dir, installer.start_menu_dir,
              installer.is_frozen, installer._ps)
    try:
        desk, menu = os.path.join(tmp2, "desktop"), os.path.join(tmp2, "menu")
        os.makedirs(desk)
        os.makedirs(menu)
        for d in (desk, menu):
            with open(os.path.join(d, installer.APP_NAME + ".lnk"), "wb") as f:
                f.write(b"fake")
        dest = os.path.join(tmp2, "dest")
        exe = os.path.join(dest, installer.EXE_NAME)
        installer.make_shortcut = lambda *a: False
        installer.write_uninstall_item = lambda *a: True
        installer.desktop_dir = lambda: desk
        installer.start_menu_dir = lambda: menu
        installer.is_frozen = lambda: False
        installer._ps = lambda s: (0, base64.b64encode(exe.encode("utf-8")).decode("ascii")) \
            if "ToBase64String" in s else (0, "")
        ok, msg, _ = installer.install(dest)
        check("旧快捷方式指向本版 exe 时不误报失败",
              ok and msg == "已安装", f"ok={ok} msg={msg}")
    finally:
        (installer.make_shortcut, installer.write_uninstall_item,
         installer.desktop_dir, installer.start_menu_dir,
         installer.is_frozen, installer._ps) = saved2
        shutil.rmtree(tmp2, ignore_errors=True)


def test_f10_f11():
    print("== F-10 掩码口径 / F-11 文档主题 ==")
    setup = read("src/setup_env.py")
    check("校验通过框不再显示完整 sec_uid",
          'acct.get("nickname") or acct["secuid"]' not in setup
          and setup.count("detect.mask_sec_uid(") >= 2
          and 'or acct["sec_uid"]' not in setup,
          str(setup.count("detect.mask_sec_uid(")))
    shown = "" or detect.mask_sec_uid(SEC)
    check("昵称为空时展示掩码", shown != SEC and shown.endswith(SEC[-4:]), shown)

    readme, eng = read("README.md"), read("docs/工程说明.md")
    check("README 徽章换成新主题色", "25f4ee" not in readme and "19c8b9" in readme)
    check("README 技术栈不再写深色", "深色 + 抖音品牌色" not in readme
          and "海岛浅色" in readme)
    check("工程说明不再写深色自绘控件", "深色自绘控件" not in eng
          and "海岛浅色" in eng)


def main():
    print(f"== F 清单闭环 · V{VERSION} ==")
    try:
        import tkinter as tk
        root = tk.Tk()
        root.geometry("340x220+120+120")
        root.withdraw()
        root.update()
    except Exception as e:
        print(f"  SKIP  Tk 不可用：{e}")
        tk = None
        root = None
    try:
        test_f1()
        test_f2()
        test_deferred(root)
        if root is not None:
            root.deiconify()
        test_f4(root)
        test_f5_f12()
        test_f6_f7(root)
        test_f8()
        test_f10_f11()
    finally:
        if root is not None:
            root.destroy()
    print(f"\n   == 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"   FAIL {name} · {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
