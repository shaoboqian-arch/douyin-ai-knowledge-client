# -*- coding: utf-8 -*-
"""跑基线脚本：逐行读输出、同步写日志文件、支持中止。

抖音项目的采集脚本要跑约 25 分钟，所以这里必须流式读（不能等进程结束再读），
并且日志要落盘 —— 界面关掉之后还能看到这一轮到底跑到哪一页。
"""
import os
import subprocess
import threading
import time

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class Cancelled(Exception):
    pass


def run_script(python, script_path, args, cwd, log_path, on_line=None,
               cancel=None, timeout=None, env_extra=None):
    """执行 `python -u <script> <args>`，返回 {code, lines, elapsed, cancelled, log}。

    cancel 是一个 threading.Event；被置位时终止子进程并标记 cancelled=True。
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [python, "-u", script_path] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    t0 = time.perf_counter()
    lines = []
    cancelled = False

    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("# " + " ".join(cmd) + "\n")
        log.flush()
        try:
            p = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            log.write(f"# 启动失败：{e}\n")
            return {"code": -1, "lines": [], "elapsed": 0.0, "cancelled": False,
                    "log": log_path, "error": f"无法启动：{e}"}

        def watch():
            nonlocal cancelled
            while p.poll() is None:
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    try:
                        p.terminate()
                    except OSError:
                        pass
                    deadline = time.time() + 5
                    while p.poll() is None and time.time() < deadline:
                        time.sleep(0.1)
                    if p.poll() is None:
                        try:
                            p.kill()
                        except OSError:
                            pass
                    return
                time.sleep(0.15)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            for line in p.stdout:
                raw = line.rstrip("\r\n")
                lines.append(raw)
                try:
                    log.write(raw + "\n")
                    log.flush()
                except (OSError, ValueError):
                    pass
                if on_line:
                    try:
                        on_line(raw)
                    except Exception:
                        pass
                if timeout and time.perf_counter() - t0 > timeout:
                    cancelled = True
                    try:
                        p.kill()
                    except OSError:
                        pass
                    break
            p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            try:
                p.kill()
            except OSError:
                pass
        watcher.join(timeout=1)

    return {"code": p.returncode if p.returncode is not None else -1,
            "lines": lines, "elapsed": round(time.perf_counter() - t0, 1),
            "cancelled": cancelled, "log": log_path}


def scan_stdout(lines):
    """从采集日志里认账号与总数（extract_favorites.py 的两条固定输出）。"""
    account = {"nickname": "", "sec_uid": ""}
    total = None
    pages = 0
    for line in lines:
        s = line.strip()
        if s.startswith("[self-profile] 账号:"):
            body = s.split("账号:", 1)[1]
            if "sec_uid:" in body:
                name, sec = body.split("sec_uid:", 1)
                account["nickname"] = name.strip()
                account["sec_uid"] = sec.strip()
        elif s.startswith("[collect] 共获取"):
            m = s.replace("条收藏", "").split()[-1]
            if m.isdigit():
                total = int(m)
        elif s.startswith("[collect] 第") and "页完成" in s:
            pages += 1
        elif s.startswith("DONE rows="):
            m = s.split("rows=", 1)[1].split()[0]
            if m.isdigit() and total is None:
                total = int(m)
    return {"account": account, "total": total, "pages": pages}
