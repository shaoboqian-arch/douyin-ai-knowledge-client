# -*- coding: utf-8 -*-
"""命令行与冻结态：--version / --cli 三条 / GUI 启动截图。

用法: python tests/verify_cli.py [exe路径]
不给 exe 时只测源码入口。
"""
import ctypes
import ctypes.wintypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402
from common import APP_NAME, VERSION  # noqa: E402

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


def run(argv, env):
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=120)
    return r


def find_window():
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _l):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            # 必须是我们自己的 Tk 窗口：WorkBuddy 侧栏标题里也可能出现应用名
            # 精确匹配标题里的版本：本机可能还开着旧版本的窗口
            if cls.value == "TkTopLevel" and buf.value.strip() == f"{APP_NAME}  {VERSION}":
                found.append((hwnd, buf.value))
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, "")


def main():
    # 截图与 GetWindowRect 都要用物理像素；调用方不声明 DPI 感知会被系统缩放对不上
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    exe = sys.argv[1] if len(sys.argv) > 1 else ""
    tmp = tempfile.mkdtemp(prefix="dysync-cli-")
    kb = _fixture.make_kb(tmp)
    project, _rows = _fixture.make_project(tmp)
    env = os.environ.copy()
    env["DYSYNC_SETTINGS"] = _fixture.configure(tmp, project, kb)
    env["PYTHONIOENCODING"] = "utf-8"
    base = [exe] if exe else [sys.executable, os.path.join(APP, "src", "app.py")]
    label = "冻结态" if exe else "源码态"

    try:
        print(f"== {label} --version ==")
        r = run(base + ["--version"], env)
        check("退出码 0", r.returncode == 0, str(r.returncode))
        check("版本号正确", (r.stdout or "").strip().splitlines()[-1] == VERSION,
              (r.stdout or "").strip()[:60])

        print(f"== {label} --selftest ==")
        r = run(base + ["--selftest"], env)
        try:
            st = json.loads(r.stdout)
        except ValueError:
            st = {}
        failed = st.get("failed") or []
        gui_names = {"gui", "settings", "setup_env", "report_ui", "installer"}
        tk_only = bool(failed) and all(
            (f.get("name") in gui_names)
            and ("tkinter" in str(f.get("error") or "").lower()
                 or "No module named '_tkinter'" in str(f.get("error") or ""))
            for f in failed)
        if tk_only:
            print("  SKIP  模块自检中的界面模块（本环境没有 tkinter，未装系统包强跑 GUI）")
            check("非界面模块可导入",
                  {m.get("name") for m in (st.get("modules") or [])}
                  >= {"common", "config", "detect", "pipeline", "subcat", "manifest",
                      "kbreport", "engine", "mcp_server", "mcp_config"},
                  str([m.get("name") for m in (st.get("modules") or [])]))
        else:
            check("模块自检通过", st.get("ok") is True, str(st)[:300])
            check("15 个模块全部可导入", len(st.get("modules") or []) == 15,
                  str([m.get("name") for m in st.get("modules") or []]))
            check("无导入失败", not failed)

        print(f"== {label} --cli --status ==")
        r = run(base + ["--cli", "--status"], env)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = {}
        check("输出合法 JSON", bool(data), (r.stdout or "")[:100] + (r.stderr or "")[:100])
        check("ready=true", data.get("ready") is True, str(data.get("missing")))
        check("状态含账号昵称", (data.get("account") or {}).get("nickname") == "测试账号")

        print(f"== {label} --cli --preflight ==")
        r = run(base + ["--cli", "--preflight", "--from", "2026-10-01",
                        "--to", "2026-11-30"], env)
        data = json.loads(r.stdout or "{}")
        check("预检 ok", data.get("ok") is True, (r.stdout or "")[:120])
        check("预检条数 4", data.get("in_range") == 4, str(data.get("in_range")))

        print(f"== {label} --cli --export ==")
        dest = os.path.join(tmp, "out")
        r = run(base + ["--cli", "--export", "--dest", dest, "--from", "2026-10-01",
                        "--to", "2026-11-30"], env)
        data = json.loads(r.stdout or "{}")
        check("导出 ok", data.get("ok") is True, (r.stdout or "")[:200])
        check("批次存在", os.path.isdir(data.get("batch_path", "")))
        check("写出 4 个 md", len([1 for b, _d, fs in os.walk(data.get("batch_path", ""))
                                for f in fs if f.endswith(".md") and f != "_导出报告.md"]) == 4)

        print(f"== {label} 首启（无设置文件） ==")
        env2 = dict(env)
        env2["DYSYNC_SETTINGS"] = os.path.join(tmp, "fresh", "settings.json")
        r = run(base + ["--cli", "--status"], env2)
        try:
            fresh = json.loads(r.stdout)
        except ValueError:
            fresh = {}
        check("首启 ready=false", fresh.get("ready") is False, str(fresh)[:160])
        check("首启只报项目目录一个缺口", fresh.get("missing") == ["项目目录"],
              str(fresh.get("missing")))

        print(f"== {label} 参数错误 ==")
        r = run(base + ["--cli", "--nope"], env)
        check("无动作时退出码 2", r.returncode == 2, str(r.returncode))

        if exe:
            print("== 冻结态 GUI ==")
            # 不让 GUI 继承父进程的 stdout/stderr 管道：
            # PyInstaller 单文件会派生一个子进程，父进程被结束而子进程还活着时，
            # 管道不关闭会让调用方（run_all）一直等 EOF。
            p = subprocess.Popen([exe], env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shot = os.path.join(APP, "验证输出", f"冻结-GUI-{VERSION}.png")
            try:
                hwnd, title = None, ""
                for _ in range(40):
                    hwnd, title = find_window()
                    if hwnd:
                        break
                    time.sleep(0.25)
                check("窗口出现", bool(hwnd), title)
                if hwnd:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w, h = rect.right - rect.left, rect.bottom - rect.top
                    check("窗口尺寸合理", w >= 600 and h >= 260, f"{w}x{h}")
                    check("标题含版本", VERSION in title, title)
                    os.makedirs(os.path.dirname(shot), exist_ok=True)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    time.sleep(0.8)          # 等 Tk 把首帧画完，否则可能抓到空白
                    from PIL import ImageGrab
                    img = None
                    for _ in range(3):
                        try:
                            img = ImageGrab.grab(window=hwnd)   # Pillow 11.2+
                        except TypeError:
                            img = ImageGrab.grab(bbox=(rect.left, rect.top,
                                                       rect.right, rect.bottom))
                        if img is not None and len(img.tobytes()) > 20000:
                            break
                        time.sleep(0.5)
                    if img is not None:
                        img.save(shot)
                    check("截图已保存", os.path.isfile(shot) and os.path.getsize(shot) > 5000,
                          f"{os.path.getsize(shot) if os.path.isfile(shot) else 0} B")
            finally:
                # 连子进程一起收掉，避免残留窗口与占用的临时解压目录
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               capture_output=True)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
