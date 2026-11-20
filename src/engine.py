# -*- coding: utf-8 -*-
"""整理引擎：状态 / 预检 / 整批整理 / 只导出 / 续跑。

设计口径与 wx V0.4.3 相同：
  · 主界面一次操作 = 一个带时间戳的批次目录，绝不覆盖已有文件
  · 引擎把每一步做成事件（phase / stage / page / item / gap），界面只负责渲染
  · 关键门禁在引擎里，不依赖界面：账号不符、条数骤降都在这里中止
"""
import datetime as dt
import ctypes
import hashlib
import json
import os
import shutil
import threading
import time
import traceback

import config
import detect
import kbreport
import manifest
import pipeline
import subcat
from common import VERSION

STATE_NAME = "_整理状态.json"
LOG_DIR = "_日志"


# ---------------------------------------------------------------- 小工具
def safe_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(limit=6)}


def _emit(cb, payload):
    if cb:
        try:
            cb(payload)
        except Exception:
            pass


def _say(cb, text):
    if cb:
        try:
            cb(text)
        except Exception:
            pass


def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_range(frm, to):
    """起止都含当天；允许两端都空（表示全部）。返回 (ok, frm, to, error)。"""
    frm, to = (frm or "").strip(), (to or "").strip()
    if not frm and not to:
        return True, "", "", ""
    if not frm or not to:
        return False, frm, to, "起止日期要么都填，要么都留空（留空 = 全部）"
    try:
        d1 = dt.date.fromisoformat(frm)
        d2 = dt.date.fromisoformat(to)
    except ValueError:
        return False, frm, to, "日期格式：YYYY-MM-DD"
    if d2 < d1:
        return False, frm, to, "结束日期早于起始日期"
    return True, frm, to, ""


def batch_label(frm, to):
    if not frm and not to:
        return "all"
    return f"{frm}_{to}"


def _unique_batch(dest, label):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(dest, f"export-{label}-{stamp}")
    if not os.path.exists(base):
        return base
    i = 2
    while os.path.exists(f"{base}-{i}"):
        i += 1
    return f"{base}-{i}"


def _write_state(batch, payload):
    path = os.path.join(batch, STATE_NAME)
    os.makedirs(batch, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)   # 内部状态，隐藏
    except Exception:
        pass
    return path


def read_state(batch):
    try:
        with open(os.path.join(batch, STATE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_rows(project_dir):
    path = os.path.join(project_dir, "work", "rows_merged.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"缺少 {path}（先完整跑一次整理）")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError("rows_merged.json 不是列表")
    return rows


def load_concepts(project_dir):
    path = os.path.join(project_dir, "work", "concepts_merged.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------------- 项目锁：与「每周增量入库」编排互斥（两条编排写同一套项目文件）
# 协议：谁要动项目，谁持有命名互斥体 Local\douyin-fav-sync.<client|weekly>.<项目哈希>；
# 开跑前先查对方的锁，活跃即中止让路。互斥体随进程退出自动释放，无残留文件。
def _project_mutex_name(project, kind):
    """互斥体名：Local\\douyin-fav-sync.<kind>.<哈希>（哈希 = 规范化项目路径 sha256 前 12 位）。"""
    try:
        path = os.path.abspath(os.path.normpath(str(project or "").strip()))
    except (OSError, ValueError):
        return ""
    if not path or not str(project or "").strip():
        return ""
    h = hashlib.sha256(os.path.normcase(path).encode("utf-8", "replace")).hexdigest()[:12]
    return f"Local\\douyin-fav-sync.{kind}.{h}"


def _mutex_open(name):
    """互斥体对象是否存在（= 对方是否持锁）。只查存在，不等待、不取所有权。"""
    if not name or os.name != "nt":
        return False
    k32 = ctypes.windll.kernel32
    for access in (0x1F0001, 0x00100001):   # MUTEX_ALL_ACCESS → SYNCHRONIZE|MUTEX_QUERY_STATE
        handle = k32.OpenMutexW(access, False, name)
        if handle:
            k32.CloseHandle(handle)
            return True
    return False


def _weekly_lock_check(project):
    if _mutex_open(_project_mutex_name(project, "weekly")):
        return ("检测到每周增量任务正在运行（项目互斥体活跃）；两条编排并发写"
                "同一知识库会互相覆盖，本轮中止，等它结束后再试。")
    return ""


class ProjectLock:
    """项目写锁：同一项目同一时刻只允许一条编排动它。

    · `acquire()` 返回 `""` = 拿到；否则返回人话原因，调用方直接中止并原样提示。
    · `release()` 幂等；调用方用 `try/finally` 包住整段编排，异常路径也不会漏放。
    · 同进程重复 acquire 同一项目立即被挡（系统互斥体对同线程是同名递归成功，
      不能靠它判重入，另用进程内集合记账）。
    """

    _held = set()

    def __init__(self, project, kind="client"):
        self.name = _project_mutex_name(project, kind)
        self.handle = None
        self._owned = False

    def acquire(self):
        if os.name != "nt":
            return ""
        if not self.name:
            return ("项目路径无法规范化，拿不到项目锁；为避免两条编排并发写同一知识库，本轮中止。")
        if self.name in ProjectLock._held:
            return ("本程序已在跑另一轮整理（同一项目）；两条编排并发写同一知识库会互相覆盖，"
                    "本轮中止，等它结束后再试。")
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.CreateMutexW(None, False, self.name)
        if not handle:
            err = ctypes.get_last_error()
            return f"无法创建项目互斥体（err={err}）；为避免并发覆盖同一知识库，本轮中止。"
        self.handle = handle
        self._owned = True
        ProjectLock._held.add(self.name)
        return ""

    def release(self):
        if not self._owned:
            return
        self._owned = False
        ProjectLock._held.discard(self.name)
        handle, self.handle = self.handle, None
        if not handle:
            return
        try:
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False


# ---------------------------------------------------------------- 状态
def status(project_dir=None, cfg=None):
    cfg = cfg or config.load()
    project = (project_dir or cfg.get("project_dir") or "").strip()
    if not project or not detect.is_project_dir(project):
        cands = detect.candidate_project_dirs(cfg.get("project_dir"))
        if not project and cands:
            project = cands[0]
    project_ok = detect.is_project_dir(project)
    python = detect.resolve_python(project, cfg.get("python", "")) if project_ok else ""
    python_ok = bool(python) and os.path.isfile(python)
    cookie = detect.read_project_settings(project) if project_ok else {}
    cookie_ok = bool(cookie.get("has_cookie"))
    kb_dir = (cfg.get("kb_dir") or "").strip() or (detect.detect_kb_dir(project) if project_ok else "")
    kb_enabled = bool(cfg.get("kb_enabled", True))
    kb_ok, kb_error = detect.kb_ready(kb_dir)
    obsidian = detect.obsidian_info(cfg.get("obsidian_exe", ""))
    expect = (cfg.get("expect_sec_uid") or "").strip()
    missing = []
    if not project_ok:
        # 首启只报第一个缺口，别把依赖它的解释器/Cookie 一起报出来
        missing.append("项目目录")
    else:
        if not python_ok:
            missing.append("项目解释器")
        if not cookie_ok:
            missing.append("抖音登录 Cookie")
        if not expect:
            missing.append("账号确认")
        if kb_enabled and not kb_ok:
            missing.append("知识库目录")
    ready = not missing
    rows_path = os.path.join(project, "work", "rows_merged.json") if project_ok else ""
    rows_ok = bool(rows_path) and os.path.isfile(rows_path)
    rows_mtime = ""
    if rows_ok:
        try:
            rows_mtime = dt.datetime.fromtimestamp(
                os.path.getmtime(rows_path)).strftime("%Y-%m-%d %H:%M")
        except OSError:
            rows_mtime = ""
    kb_stats = {}
    if kb_ok and project_ok:
        try:
            kb_stats = kbreport.snapshot_stats(project, kb_dir)
        except Exception:
            kb_stats = {}
    warnings = []
    if kb_enabled and not obsidian.get("installed"):
        warnings.append("未检测到 Obsidian；Markdown 仍会写入，但不会自动打开")
    msg = ""
    if not ready:
        msg = "；".join(filter(None, [
            "缺少 " + "、".join(missing) if missing else "",
            kb_error if not kb_ok else "",
            (cookie.get("error") or "") if project_ok and not cookie_ok else "",
        ]))
    return {
        "ok": True, "ready": ready, "message": msg,
        "project_dir": project, "project_ok": project_ok,
        "python": python, "python_ok": python_ok,
        "cookie_ok": cookie_ok, "cookie_len": int(cookie.get("cookie_len") or 0),
        "account": {"nickname": cfg.get("expect_nickname", ""),
                    "sec_uid": expect,
                    "masked": detect.mask_sec_uid(expect)},
        "kb_dir": kb_dir, "kb_ok": kb_ok, "kb_error": kb_error,
        "kb_enabled": kb_enabled, "kb_stats": kb_stats,
        "obsidian": {"installed": bool(obsidian.get("installed")),
                     "exe": obsidian.get("exe", ""),
                     "vaults": obsidian.get("vaults") or [],
                     "message": obsidian.get("message", "")},
        "rows_ok": rows_ok, "rows_mtime": rows_mtime,
        "missing": missing, "warnings": warnings,
    }


# ---------------------------------------------------------------- 预检
def preflight(frm="", to="", project_dir=None):
    """只读。统计范围内的条目与待加工数量，不写任何文件。"""
    ok, frm, to, err = parse_range(frm, to)
    if not ok:
        return {"ok": False, "error": err}
    cfg = config.load()
    st = status(project_dir, cfg)
    project = st["project_dir"]
    if not st["project_ok"]:
        return {"ok": False, "error": "未找到抖音项目目录"}
    t0 = dt.datetime.now()
    try:
        rows = load_rows(project)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    picked = [r for r in rows if manifest.in_range(r, frm, to)]
    concepts = load_concepts(project)
    tdir = os.path.join(project, "work", "transcripts")
    by_type = {"视频": 0, "图集": 0}
    by_sub = {}
    ai = pending = gap = 0
    for r in picked:
        k = str(r.get("类型") or "")
        by_type["图集" if k == "图集" else "视频"] += 1
        a = str(r.get("AI相关") or "").strip()
        wid0 = str(r.get("作品ID") or "")
        tp = os.path.join(tdir, f"{wid0}.txt")
        ttext = ""
        if os.path.isfile(tp):
            try:
                ttext = open(tp, encoding="utf-8", errors="replace").read()
            except OSError:
                ttext = ""
        if a in ("是", "否"):
            name = subcat.classify(r, ttext)["子类别"]
            by_sub[name] = by_sub.get(name, 0) + 1
        wid = str(r.get("作品ID") or "")
        reasons = manifest.gap_reasons(
            r, "图集" if k == "图集" else "视频", concepts.get(wid), ttext)
        if a == "是":
            ai += 1
        elif a not in ("否",):
            pending += 1
        if reasons:
            gap += 1
    return {
        "ok": True, "from": frm, "to": to,
        "total": len(rows), "in_range": len(picked),
        "by_type": by_type,
        "by_sub": sorted(({"子类别": k, "条数": v} for k, v in by_sub.items()),
                         key=lambda x: -x["条数"]),
        "ai": ai, "ai_pending": pending, "gap": gap,
        "kb_dir": st["kb_dir"],
        "elapsed_ms": int((dt.datetime.now() - t0).total_seconds() * 1000),
    }


# ---------------------------------------------------------------- 整理
def sync(dest, frm="", to="", on_event=None, on_progress=None, cancel=None,
         project_dir=None):
    """采集 → 对比 → 重建 → 导出，写成一批交付。

    锁的范围就是这一整段：入口拿、`finally` 放（中途抛异常也不会漏放）；
    拿到锁后先查「每周增量入库」是否在跑，活跃即中止让路。
    """
    cfg = config.load()
    st = status(project_dir, cfg)
    if not st["ready"]:
        return {"ok": False, "error": ("环境未就绪：" + st["message"]) if st["message"]
                else "环境未就绪", "status": st}
    ok, frm, to, err = parse_range(frm, to)
    if not ok:
        return {"ok": False, "error": err}
    dest = os.path.normpath((dest or "").strip()) if (dest or "").strip() else ""
    if not dest:
        return {"ok": False, "error": "未选择交付目录"}
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": f"无法创建交付目录：{e}"}

    lock_err = _weekly_lock_check(st["project_dir"])
    if lock_err:
        return {"ok": False, "error": lock_err}
    lock = ProjectLock(st["project_dir"], "client")
    lock_err = lock.acquire()
    if lock_err:
        return {"ok": False, "error": lock_err}
    try:
        return _sync_locked(dest, frm, to, cfg, st, on_event, on_progress, cancel)
    finally:
        lock.release()


def _sync_locked(dest, frm, to, cfg, st, on_event, on_progress, cancel):
    """`sync` 的正体：调用方已校验参数并持项目锁，这里只做编排。"""
    project = st["project_dir"]
    python = st["python"]
    batch = _unique_batch(dest, batch_label(frm, to))
    logs = os.path.join(batch, LOG_DIR)
    os.makedirs(logs, exist_ok=True)
    state = {
        "version": 1, "app_version": VERSION, "stage": "check", "ok": False,
        "started_at": _now(), "finished_at": "", "error": "",
        "project_dir": project, "kb_dir": st["kb_dir"], "dest": dest, "batch": batch,
        "range": {"from": frm, "to": to},
        "account": {"nickname": cfg.get("expect_nickname", ""),
                    "sec_uid": detect.mask_sec_uid(cfg.get("expect_sec_uid", ""))},
        "logs": {},
    }
    _write_state(batch, state)

    def fail(stage, message, extra=None):
        state.update(stage=stage, ok=False, error=message, finished_at=_now())
        if extra:
            state.update(extra)
        _write_state(batch, state)
        return {"ok": False, "error": message, "batch_path": batch,
                "stage": stage, "state": state}

    def stopped():
        _emit(on_event, {"type": "phase", "name": "done"})
        return fail(state["stage"], "已停止本轮整理；已采集的原始数据保留在项目里，未生成交付。")

    # ---- 1 校验
    _emit(on_event, {"type": "phase", "name": "check"})
    _say(on_progress, "校验账号与项目…")
    raw = os.path.join(project, "output", "favorites_raw.json")
    if os.path.isfile(raw):
        backup = os.path.join(project, "work", "backup_favorites_raw_prev.json")
        try:
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(raw, backup)
            _emit(on_event, {"type": "stage", "name": "backup", "state": "done",
                             "message": f"已备份上一轮原始数据（{os.path.getsize(backup):,} B）"})
        except OSError as e:
            return fail("check", f"备份上一轮原始数据失败：{e}")
    if cancel is not None and cancel.is_set():
        return stopped()

    # ---- 2 采集
    _emit(on_event, {"type": "phase", "name": "collect"})
    _say(on_progress, "正在采集收藏（每页约 1.5 秒）…")
    collect_log = os.path.join(logs, "collect.log")

    def on_line(line):
        s = line.strip()
        if s.startswith("[collect] 第") and "页完成" in s:
            parts = s.replace("[collect] 第", "").replace("页完成", "").split(",")
            page = parts[0].strip()
            count = parts[1].replace("累计", "").replace("条", "").strip() if len(parts) > 1 else ""
            _emit(on_event, {"type": "page", "index": int(page) if page.isdigit() else 0,
                             "count": int(count) if count.isdigit() else 0})
            _say(on_progress, f"正在采集：第 {page} 页 · 累计 {count} 条")

    r = pipeline.run_script(python, os.path.join(project, "extract_favorites.py"),
                            ["--folders"], project, collect_log, on_line=on_line, cancel=cancel)
    state["logs"]["collect"] = collect_log
    if r.get("cancelled"):
        return stopped()
    info = pipeline.scan_stdout(r.get("lines") or [])
    if r["code"] != 0:
        tail = " / ".join((r.get("lines") or [])[-2:])
        return fail("collect", f"采集失败（exit {r['code']}）：{tail or r.get('error', '')}")

    acct = info.get("account") or {}
    expect = (cfg.get("expect_sec_uid") or "").strip()
    got = (acct.get("sec_uid") or "").strip()
    # 账号硬门 fail-closed：确认账号缺失、标识解析不到、标识不一致，
    # 三种情况一律中止，绝不在「没解析到」时静默放行（V0.1.6 / F-1）。
    if not expect:
        return fail("collect",
                    "账号未确认：请先在「初始化本机环境」里校验并采用账号；"
                    "已中止，未重建交付物。",
                    {"collect": {"account": acct, "total": info.get("total"),
                                 "gates_ok": False,
                                 "identity_reason": "account_not_confirmed"}})
    if not got:
        return fail("collect",
                    "账号无法核对：本轮采集日志没有给出可比的 sec_uid"
                    "（上游输出格式可能已变化，或 Cookie 已换号）；"
                    "已中止，未重建交付物。请确认采集脚本与登录态。",
                    {"collect": {"account": acct, "total": info.get("total"),
                                 "gates_ok": False,
                                 "identity_reason": "sec_uid_missing"}})
    if got != expect:
        return fail("collect",
                    f"账号不符：本轮采集到的是「{acct.get('nickname') or '未知'}」，"
                    f"与设置的账号不一致；已中止，未重建交付物。",
                    {"collect": {"account": acct, "total": info.get("total"),
                                 "gates_ok": False,
                                 "identity_reason": "mismatch"}})
    total = info.get("total")
    if total is None:
        try:
            total = len(json.load(open(raw, encoding="utf-8")))
        except (OSError, ValueError):
            total = 0
    state["collect"] = {"code": r["code"], "elapsed": r["elapsed"], "pages": info.get("pages"),
                        "total": total}
    _write_state(batch, state)
    state["collect"].update({
        "gates_ok": True,
        "account": {"nickname": acct.get("nickname", ""),
                    "sec_uid_masked": detect.mask_sec_uid(acct.get("sec_uid", "")),
                    "matched": bool(expect) and acct.get("sec_uid") == expect},
        "scope": {"from": frm, "to": to},
    })
    # 采集后、重建前抓基线：make_tables 会把 rows_merged 备份成 prev，
    # 一旦它跑过，「新增/取消」的旧集合就变了，所以必须在这里取。
    snap = kbreport.snapshot(project)
    state["ids"] = {
        "old": sorted(snap["old_ids"]),
        "new": sorted(snap["raw_ids"] - snap["old_ids"]),
        "removed": sorted(snap["old_ids"] - snap["raw_ids"]),
    }
    _write_state(batch, state)
    _emit(on_event, {"type": "stage", "name": "collect", "state": "done",
                     "message": f"{total} 条收藏 · {info.get('pages') or 0} 页"})
    if cancel is not None and cancel.is_set():
        return stopped()

    # ---- 3 对比
    _emit(on_event, {"type": "phase", "name": "diff"})
    _say(on_progress, "对比上一轮，算新增…")
    diff_log = os.path.join(logs, "diff.log")
    rd = pipeline.run_script(python, os.path.join(project, "weekly_prepare.py"),
                             [], project, diff_log, cancel=cancel)
    state["logs"]["diff"] = diff_log
    if rd.get("cancelled"):
        return stopped()
    if rd["code"] not in (0, 10):
        return fail("diff", f"对比新增失败（exit {rd['code']}）")
    new_count = len(state["ids"]["new"])
    if not new_count:
        for line in rd.get("lines") or []:
            if "发现新增" in line:
                token = line.split("发现新增", 1)[1].strip().split()[0]
                if token.isdigit():
                    new_count = int(token)
    state["diff"] = {"code": rd["code"], "new_count": new_count}
    _write_state(batch, state)
    _emit(on_event, {"type": "stage", "name": "diff", "state": "done",
                     "message": ("无新增" if new_count == 0 else f"新增 {new_count} 条")})

    # ---- 4 重建（出表 → 笔记 → 体检）
    _emit(on_event, {"type": "phase", "name": "rebuild"})
    kb_enabled = bool(cfg.get("kb_enabled", True))
    audit_rc, audit_lines = None, []
    steps = [("tables", "make_tables.py", "重建 Excel / CSV…")]
    if kb_enabled:
        steps += [("notes", "gen_obsidian.py", "重建知识库笔记…"),
                  ("audit", "audit_obsidian.py", "体检知识库…")]
    else:
        _emit(on_event, {"type": "stage", "name": "notes", "state": "skip"})
        _emit(on_event, {"type": "stage", "name": "audit", "state": "skip"})
    for key, script, label in steps:
        if cancel is not None and cancel.is_set():
            return stopped()
        _say(on_progress, label)
        _emit(on_event, {"type": "stage", "name": key, "state": "start"})
        log = os.path.join(logs, f"{key}.log")
        rr = pipeline.run_script(python, os.path.join(project, script), [], project,
                                 log, cancel=cancel)
        state["logs"][key] = log
        if rr.get("cancelled"):
            return stopped()
        if key == "audit":
            audit_rc, audit_lines = rr["code"], rr.get("lines") or []
        if rr["code"] != 0:
            _emit(on_event, {"type": "stage", "name": key, "state": "failed"})
            tail = " / ".join((rr.get("lines") or [])[-3:])
            return fail("rebuild", f"{script} 失败（exit {rr['code']}）：{tail}")
        _emit(on_event, {"type": "stage", "name": key, "state": "done"})
    state["rebuild"] = {"ok": True, "kb_enabled": kb_enabled}
    _write_state(batch, state)
    if cancel is not None and cancel.is_set():
        return stopped()

    # ---- 5 导出
    _emit(on_event, {"type": "phase", "name": "export"})
    _say(on_progress, "写出本批交付…")
    try:
        rows = load_rows(project)
        res = manifest.build(
            rows, batch, frm, to,
            transcripts_dir=os.path.join(project, "work", "transcripts"),
            concepts_map=load_concepts(project),
            on_item=lambda it: _emit(on_event, {"type": "item", "item": it}),
            on_gap=lambda g: _emit(on_event, {"type": "gap", "gap": g}),
            on_plan=lambda n: _emit(on_event, {"type": "plan", "total": n}))
    except (OSError, ValueError) as e:
        return fail("export", f"写出交付失败：{e}")
    if not res.get("ok"):
        return fail("export", res.get("error", "写出交付失败"))

    # ---- 6 入库报告 + 完成
    try:
        report = kbreport.build(
            project, st["kb_dir"], cfg, state.get("collect") or {},
            state.get("ids") or {}, rows, snap.get("prev_rows") or [],
            load_concepts(project), audit_rc, audit_lines,
            kb_enabled=kb_enabled, mode="sync")
        kbreport.write(batch, report,
                       append_to=os.path.join(batch, manifest.REPORT_NAME))
    except Exception as e:
        report = {"ok": False, "error": f"{type(e).__name__}: {e}", "rows": []}
    state.update(stage="done", ok=True, finished_at=_now(),
                 export={"total": res["total"], "stats": res["stats"],
                         "gaps": len(res["gaps"]), "gap_items": res["gaps"][:200]},
                 report=report)
    _write_state(batch, state)
    _emit(on_event, {"type": "phase", "name": "done"})
    _say(on_progress, "")
    return {"ok": True, "batch_path": batch, "total": res["total"],
            "stats": res["stats"], "gap_count": len(res["gaps"]),
            "gaps": res["gaps"], "new_count": new_count,
            "collect_total": total, "report": report, "state": state}


# ---------------------------------------------------------------- 只导出（不联网）
def export_only(dest, frm="", to="", on_event=None, on_progress=None, project_dir=None):
    """用项目里已有的 rows_merged.json 写一批交付；不采集、不重建、不联网。"""
    cfg = config.load()
    st = status(project_dir, cfg)
    if not st["project_ok"]:
        return {"ok": False, "error": "未找到抖音项目目录"}
    ok, frm, to, err = parse_range(frm, to)
    if not ok:
        return {"ok": False, "error": err}
    dest = os.path.normpath((dest or "").strip()) if (dest or "").strip() else ""
    if not dest:
        return {"ok": False, "error": "未选择交付目录"}
    try:
        rows = load_rows(st["project_dir"])
    except FileNotFoundError:
        return {"ok": False,
                "error": "还没有整理结果：请先点右上角「全仓同步」跑一次，再用「仅导出」"}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"读取整理结果失败：{e}"}
    os.makedirs(dest, exist_ok=True)
    batch = _unique_batch(dest, batch_label(frm, to))
    _emit(on_event, {"type": "phase", "name": "export"})
    _say(on_progress, "写出本批交付…")
    try:
        res = manifest.build(
            rows, batch, frm, to,
            transcripts_dir=os.path.join(st["project_dir"], "work", "transcripts"),
            concepts_map=load_concepts(st["project_dir"]),
            on_item=lambda it: _emit(on_event, {"type": "item", "item": it}),
            on_gap=lambda g: _emit(on_event, {"type": "gap", "gap": g}),
            on_plan=lambda n: _emit(on_event, {"type": "plan", "total": n}))
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"写出交付失败：{e}", "batch_path": batch}
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "写出交付失败"), "batch_path": batch}
    state = {
        "version": 1, "app_version": VERSION, "stage": "done", "ok": True,
        "started_at": _now(), "finished_at": _now(), "error": "",
        "project_dir": st["project_dir"], "kb_dir": st["kb_dir"], "dest": dest,
        "batch": batch, "range": {"from": frm, "to": to},
        "mode": "export_only",
        "export": {"total": res["total"], "stats": res["stats"],
                   "gaps": len(res["gaps"]), "gap_items": res["gaps"][:200]},
    }
    _write_state(batch, state)
    _emit(on_event, {"type": "phase", "name": "done"})
    return {"ok": True, "batch_path": batch, "total": res["total"],
            "stats": res["stats"], "gap_count": len(res["gaps"]),
            "gaps": res["gaps"], "new_count": 0, "state": state}


# ---------------------------------------------------------------- 续跑
def retry(batch_path, on_event=None, on_progress=None, cancel=None):
    """对已采集成功的批次，重跑重建 + 导出，写成**新的一批**（不重新采集）。

    · 不原地改写旧批次：旧批次保留为证据，新批次名带 `-r2`、`-r3`，绝不覆盖。
    · 采集阶段就中止的批次不能靠续跑补救 —— 那需要重新采集，直接点「⚠️ 全仓同步」。
    · 重建要动项目文件，所以与 `sync` 一样全程持项目锁（入口拿、`finally` 放）。
    """
    old = (batch_path or "").strip()
    state = read_state(old)
    if not state:
        return {"ok": False, "error": "批次目录里没有 _整理状态.json，无法续跑"}
    stage = state.get("stage")
    if stage == "done":
        return {"ok": False, "error": "这一批已经完成，无需续跑"}
    if not (state.get("collect") or {}).get("gates_ok"):
        return {"ok": False, "error": "这一批在采集阶段就中止了，需要重新点「⚠️ 全仓同步」"}
    # 旧版本（V0.1.5 及以前）可能在账号标识解析不到时仍把 gates_ok 置 True；
    # 这种批次的身份没有真正核对过，不允许靠续跑把数据重建进知识库（F-1）。
    old_acct = (state.get("collect") or {}).get("account") or {}
    if old_acct and old_acct.get("matched") is not True:
        return {"ok": False,
                "error": "这一批的账号身份未通过核对，不能续跑；请重新点「⚠️ 全仓同步」"}
    cfg = config.load()
    st = status(state.get("project_dir") or None, cfg)
    if not st["python_ok"]:
        return {"ok": False, "error": "项目解释器不可用"}
    lock_err = _weekly_lock_check(st["project_dir"])
    if lock_err:
        return {"ok": False, "error": lock_err}
    lock = ProjectLock(st["project_dir"], "client")
    lock_err = lock.acquire()
    if lock_err:
        return {"ok": False, "error": lock_err}
    try:
        return _retry_locked(old, state, cfg, st, on_event, on_progress, cancel)
    finally:
        lock.release()


def _retry_locked(old, state, cfg, st, on_event, on_progress, cancel):
    """`retry` 的正体：调用方已校验旧批次并持项目锁。"""
    project, python = st["project_dir"], st["python"]
    rng = state.get("range") or {}
    dest = os.path.normpath(state.get("dest") or os.path.dirname(old))
    batch = _unique_batch(dest, batch_label(rng.get("from", ""), rng.get("to", "")) + "-r")
    logs = os.path.join(batch, LOG_DIR)
    os.makedirs(logs, exist_ok=True)
    new_state = {
        "version": 1, "app_version": VERSION, "stage": "rebuild", "ok": False,
        "started_at": _now(), "finished_at": "", "error": "",
        "project_dir": project, "kb_dir": st["kb_dir"], "dest": dest, "batch": batch,
        "range": {"from": rng.get("from", ""), "to": rng.get("to", "")},
        "account": state.get("account") or {},
        "collect": state.get("collect") or {},
        "ids": state.get("ids") or {},
        "resumed_from": old,
        "logs": {},
    }
    _write_state(batch, new_state)

    def fail(message):
        new_state.update(stage="rebuild", ok=False, error=message, finished_at=_now())
        _write_state(batch, new_state)
        return {"ok": False, "error": message, "batch_path": batch,
                "stage": "rebuild", "state": new_state}

    def stopped():
        _emit(on_event, {"type": "phase", "name": "done"})
        return fail("已停止本轮整理；已采集的原始数据保留在项目里，未生成交付。")

    _emit(on_event, {"type": "phase", "name": "rebuild"})
    kb_enabled = bool(cfg.get("kb_enabled", True))
    audit_rc, audit_lines = None, []
    steps = [("tables", "make_tables.py", "重建 Excel / CSV…")]
    if kb_enabled:
        steps += [("notes", "gen_obsidian.py", "重建知识库笔记…"),
                  ("audit", "audit_obsidian.py", "体检知识库…")]
    else:
        _emit(on_event, {"type": "stage", "name": "notes", "state": "skip"})
        _emit(on_event, {"type": "stage", "name": "audit", "state": "skip"})
    for key, script, label in steps:
        if cancel is not None and cancel.is_set():
            return stopped()
        _say(on_progress, label)
        _emit(on_event, {"type": "stage", "name": key, "state": "start"})
        log = os.path.join(logs, f"{key}.log")
        rr = pipeline.run_script(python, os.path.join(project, script), [], project,
                                 log, cancel=cancel)
        new_state["logs"][key] = log
        if rr.get("cancelled"):
            return stopped()
        if key == "audit":
            audit_rc, audit_lines = rr["code"], rr.get("lines") or []
        if rr["code"] != 0:
            _emit(on_event, {"type": "stage", "name": key, "state": "failed"})
            tail = " / ".join((rr.get("lines") or [])[-3:])
            return fail(f"{script} 失败（exit {rr['code']}）：{tail}")
        _emit(on_event, {"type": "stage", "name": key, "state": "done"})
    if cancel is not None and cancel.is_set():
        return stopped()

    _emit(on_event, {"type": "phase", "name": "export"})
    _say(on_progress, "写出本批交付…")
    try:
        rows = load_rows(project)
        res = manifest.build(
            rows, batch, rng.get("from", ""), rng.get("to", ""),
            transcripts_dir=os.path.join(project, "work", "transcripts"),
            concepts_map=load_concepts(project),
            on_item=lambda it: _emit(on_event, {"type": "item", "item": it}),
            on_gap=lambda g: _emit(on_event, {"type": "gap", "gap": g}),
            on_plan=lambda n: _emit(on_event, {"type": "plan", "total": n}))
    except (OSError, ValueError) as e:
        return fail(f"写出交付失败：{e}")
    if not res.get("ok"):
        return fail(res.get("error", "写出交付失败"))
    try:
        report = kbreport.build(
            project, st["kb_dir"], cfg, new_state.get("collect") or {},
            new_state.get("ids") or {}, rows, [],
            load_concepts(project), audit_rc, audit_lines,
            kb_enabled=kb_enabled, mode="retry")
        kbreport.write(batch, report,
                       append_to=os.path.join(batch, manifest.REPORT_NAME))
    except Exception as e:
        report = {"ok": False, "error": f"{type(e).__name__}: {e}", "rows": []}
    new_state.update(stage="done", ok=True, finished_at=_now(),
                     export={"total": res["total"], "stats": res["stats"],
                             "gaps": len(res["gaps"]), "gap_items": res["gaps"][:200]},
                     report=report)
    _write_state(batch, new_state)
    _emit(on_event, {"type": "phase", "name": "done"})
    return {"ok": True, "batch_path": batch, "total": res["total"],
            "stats": res["stats"], "gap_count": len(res["gaps"]),
            "gaps": res["gaps"], "report": report, "resumed": True}
