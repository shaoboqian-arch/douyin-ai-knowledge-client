# -*- coding: utf-8 -*-
"""跑基线脚本：逐行读输出、同步写日志文件、支持中止。

抖音项目的采集脚本要跑约 25 分钟，所以这里必须流式读（不能等进程结束再读），
并且日志要落盘 —— 界面关掉之后还能看到这一轮到底跑到哪一页。
"""
import os
import re
import subprocess
import threading
import time

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# 上游脚本若把账号行改成 sec_uid= / secUid / JSON 形式，也尽量认出来；
# 认不出来的话 sec_uid 保持空串，由 engine.sync 的硬门 fail-closed 兜住。
_SEC_RE = re.compile(
    r"sec[_-]?uid['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{6,})", re.I)


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
    """从采集日志里认账号与总数。

    账号标识认几种写法（sec_uid: / sec_uid= / secUid / JSON 片段），
    昵称取标识之前的文字；解析不到标识时返回空串，调用方必须中止，
    不能因为「没解析到」就当作账号一致。
    """
    account = {"nickname": "", "sec_uid": ""}
    total = None
    pages = 0
    for line in lines:
        s = line.strip()
        m = _SEC_RE.search(s)
        if m:
            account["sec_uid"] = m.group(1).strip().strip("'\"")
            head = s[:m.start()]
            if "账号:" in head:
                head = head.split("账号:", 1)[1]
            head = re.sub(r"^\[self-profile\]\s*", "", head.strip())
            nick = re.search(r'"nickname"\s*:\s*"([^"]+)"', head)
            if nick:
                account["nickname"] = nick.group(1)
            else:
                account["nickname"] = head.strip(" :：,，\"'[]{}-")
        elif s.startswith("[self-profile] 账号:"):
            body = s.split("账号:", 1)[1].strip()
            # 标识写了但值为空：昵称仍要认出来，sec_uid 保持空串由硬门拦住。
            body = re.split(r"sec[_-]?uid\s*[:=]", body, flags=re.I)[0]
            account["nickname"] = body.strip(" :：,，\"'")
        if s.startswith("[collect] 共获取"):
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
