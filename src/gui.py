# -*- coding: utf-8 -*-
"""主界面：选交付目录 + 发布时间范围 → 开始整理。

常驻可见元素只有四个：交付目录、发布时间范围、开始整理、状态行。
进度表在点「开始整理」后按需展开；待加工清单与续跑按钮只在需要时出现。
"""
import datetime as dt
import json
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config
import engine
import settings as settings_ui
import setup_env
from common import APP_NAME, PHASES, VERSION, app_dir, is_frozen, prefs_path
from ui_kit import (
    ACCENT, BG, BORDER, CYAN, DONE_BG, ERR, ERR_BG, MUTED, ON_ACCENT, PANEL,
    SURFACE, TEXT, WARN,
    CapsuleButton, DatePicker, PhaseBadge, ProgressBar, RoundedEntry, Tooltip,
    apply_icon, apply_theme, center, fonts,
)

W = 640
BASE_H = 286
PANEL_H = 286
HINT_H = 88

GROUPS = (("video", "视频"), ("album", "图集"), ("ai", "其中 · AI 笔记"))


def default_dest():
    if is_frozen():
        base = os.path.join(os.path.expanduser("~"), "Documents")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.dirname(app_dir()), "整理输出")


def _load_prefs():
    try:
        with open(prefs_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_prefs(**kw):
    try:
        cur = _load_prefs()
        cur.update({k: v for k, v in kw.items() if v is not None})
        os.makedirs(os.path.dirname(prefs_path()), exist_ok=True)
        with open(prefs_path(), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
    except OSError:
        pass


def _blank_stats():
    return {g: {"total": 0, "ok": 0, "gap": 0} for g, _ in GROUPS}


class App:
    def __init__(self, root, font_main, font_small, family):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.dirty = False
        self.panel_visible = False
        self.hint_visible = False
        self.full_state = ""
        self.env_message = ""
        self.env_ready = False
        self.last_batch = ""
        self.last_state = {}
        self.report = {}
        self.stats = _blank_stats()
        self.gaps = []
        self.font_main = font_main
        self.font_small = font_small
        self.family = family

        root.title(f"{APP_NAME}  {VERSION}")
        root.resizable(True, True)
        root.minsize(W, BASE_H)
        root.configure(bg=BG)
        apply_icon(root)
        apply_theme(root)
        center(root, W, BASE_H)

        f = tk.Frame(root, bg=BG, padx=20, pady=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(5, weight=1)

        tk.Label(f, text="交付到", font=font_main, bg=BG, fg=MUTED).grid(
            row=0, column=0, sticky="w", pady=(2, 12))
        self.dest = RoundedEntry(f, font=font_main)
        self.dest.grid(row=0, column=1, sticky="ew", pady=(2, 12), padx=(12, 8))
        CapsuleButton(f, text="浏览…", command=self.pick, width=84, height=36,
                      font=font_small).grid(row=0, column=2, pady=(2, 12))

        tk.Label(f, text="发布时间", font=font_main, bg=BG, fg=MUTED).grid(
            row=1, column=0, sticky="w", pady=(0, 18))
        rng = tk.Frame(f, bg=BG)
        rng.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(0, 18))
        rng.columnconfigure(0, weight=1)
        rng.columnconfigure(3, weight=1)
        self.frm = RoundedEntry(rng, font=font_main, width=10, pxwidth=160, placeholder="不限")
        self.to = RoundedEntry(rng, font=font_main, width=10, pxwidth=160, placeholder="不限")
        self.frm.grid(row=0, column=0, sticky="ew")
        self._cal_from = DatePicker(self.frm, font=font_small)
        CapsuleButton(rng, text="▾", command=self._cal_from.toggle, width=28, height=36,
                      font=font_small).grid(row=0, column=1, padx=(4, 0))
        tk.Label(rng, text="  —  ", font=font_main, bg=BG, fg=MUTED).grid(row=0, column=2)
        self.to.grid(row=0, column=3, sticky="ew")
        self._cal_to = DatePicker(self.to, font=font_small)
        CapsuleButton(rng, text="▾", command=self._cal_to.toggle, width=28, height=36,
                      font=font_small).grid(row=0, column=4, padx=(4, 0))

        self.btn = CapsuleButton(f, text="开始整理", command=self.primary_action, primary=True,
                                 height=42, font=(family, 11, "bold"))
        self.btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        CapsuleButton(f, text="设置", command=self.open_settings, width=84, height=42,
                      font=font_small).grid(row=2, column=2)

        self.prog = ProgressBar(f, height=8)
        self.prog.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.prog.grid_remove()

        sf = tk.Frame(f, bg=BG)
        sf.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        sf.columnconfigure(0, weight=1)
        self.state = tk.Label(sf, text="", font=font_small, fg=MUTED, bg=BG,
                              anchor="w", wraplength=320, justify="left", takefocus=1)
        self.state.grid(row=0, column=0, sticky="w")
        self.info = tk.Label(sf, text="ⓘ", font=font_small, fg=WARN, bg=BG,
                             cursor="question_arrow", takefocus=1)
        self.info.grid(row=0, column=1, padx=(6, 0))
        self.info.grid_remove()
        self.report_btn = CapsuleButton(sf, text="入库报告", command=self.open_report,
                                        width=84, height=28, font=font_small)
        self.report_btn.grid(row=0, column=2, padx=(6, 0))
        self.report_btn.grid_remove()
        self.retry_btn = CapsuleButton(sf, text="续跑", command=self.start_retry,
                                       width=64, height=28, font=font_small)
        self.retry_btn.grid(row=0, column=3, padx=(6, 0))
        self.retry_btn.grid_remove()
        self.open_btn = CapsuleButton(sf, text="打开", command=self.open_result,
                                      width=64, height=28, font=font_small)
        self.open_btn.grid(row=0, column=4, padx=(6, 0))
        self.open_btn.grid_remove()
        Tooltip(self.state, lambda: self.full_state, font=font_small)
        Tooltip(self.info, lambda: self.env_message, font=font_small)
        for w, getter in ((self.state, lambda: self.full_state),
                          (self.info, lambda: self.env_message)):
            w.bind("<Button-1>", lambda _e, g=getter: self.show_full(g()))
            w.bind("<Return>", lambda _e, g=getter: self.show_full(g()))
            w.bind("<space>", lambda _e, g=getter: self.show_full(g()))

        self.panel = self._build_panel(f)
        self.panel.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        self.panel.grid_remove()

        prefs = _load_prefs()
        cfg = config.load()
        self.dest.insert(0, cfg.get("dest") or prefs.get("dest") or default_dest())
        self.frm.insert(0, cfg.get("frm") or "")
        self.to.insert(0, cfg.get("to") or "")

        root.bind("<Return>", lambda _e: self.primary_action())
        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Configure>", self._on_configure)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._after_id = root.after(60, self.poll)
        threading.Thread(target=self.env_check, daemon=True).start()
        self.root.after(120, lambda: self._restore_last(prefs))

    # ---------------------------------------------------------------- 进度表
    def _build_panel(self, parent):
        p = tk.Frame(parent, bg=BG, highlightbackground=BORDER,
                     highlightthickness=1, padx=12, pady=10)
        p.columnconfigure(0, weight=1)
        p.rowconfigure(3, weight=1)

        hdr = tk.Frame(p, bg=BG)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(6, weight=1)
        self.badges = {}
        for i, (key, label) in enumerate(PHASES):
            b = PhaseBadge(hdr, text=label, font=self.font_small, width=68, height=24)
            b.grid(row=0, column=i, padx=(0, 6))
            self.badges[key] = b
        CapsuleButton(hdr, text="收起", command=self.hide_panel,
                      width=60, height=24, font=self.font_small).grid(row=0, column=6, sticky="e")

        tbl = tk.Frame(p, bg=BG)
        tbl.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        for j, c in enumerate(("类别", "总数", "已写出", "待加工")):
            tk.Label(tbl, text=c, font=self.font_small, fg=MUTED, bg=BG,
                     width=12 if j else 16,
                     anchor="w" if j == 0 else "e").grid(row=0, column=j, padx=(0, 6))
        self.cell = {}
        for i, (g, name) in enumerate(GROUPS, 1):
            tk.Label(tbl, text=name, font=self.font_small, fg=TEXT, bg=BG,
                     width=16, anchor="w").grid(row=i, column=0, sticky="w")
            for j, key in enumerate(("total", "ok", "gap"), 1):
                v = tk.Label(tbl, text="0", font=self.font_small, fg=TEXT, bg=BG,
                             width=12, anchor="e")
                v.grid(row=i, column=j, padx=(0, 6))
                self.cell[(g, key)] = v

        self.gap_title = tk.Label(p, text="待加工 0", font=self.font_small,
                                  fg=MUTED, bg=BG, anchor="w")
        self.gap_title.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 4))
        self.tree = ttk.Treeview(p, columns=("name", "reason"), show="headings", height=4)
        self.tree.heading("name", text="条目")
        self.tree.heading("reason", text="缺什么")
        self.tree.column("name", width=320, anchor="w")
        self.tree.column("reason", width=210, anchor="w")
        sb = ttk.Scrollbar(p, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=3, column=0, sticky="nsew")
        sb.grid(row=3, column=1, sticky="ns")

        self.hint = tk.Frame(p, bg=ERR_BG, padx=10, pady=8)
        self.hint.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.hint_label = tk.Label(self.hint, text="", font=self.font_small,
                                   fg=TEXT, bg=ERR_BG, justify="left", anchor="w",
                                   wraplength=540)
        self.hint_label.pack(fill="x")
        self.hint.grid_remove()
        return p

    def resize(self):
        h = BASE_H
        if self.busy or self.prog.winfo_manager():
            h += 20
        if self.panel_visible:
            h += PANEL_H
            if self.hint_visible:
                h += HINT_H
        self.root.minsize(W, h)
        self.root.update_idletasks()
        w = max(W, int(self.root.winfo_width() or W))
        cur_h = int(self.root.winfo_height() or 0)
        if cur_h < h or not self.panel_visible:
            self.root.geometry(f"{w}x{h}")

    def _on_configure(self, event):
        if event.widget is not self.root:
            return
        state_w = max(160, int(event.width) - 300)
        hint_w = max(200, int(event.width) - 80)
        if int(self.state.cget("wraplength") or 0) != state_w:
            self.state.configure(wraplength=state_w)
        if int(self.hint_label.cget("wraplength") or 0) != hint_w:
            self.hint_label.configure(wraplength=hint_w)

    def show_panel(self):
        self.panel_visible = True
        self.panel.grid()
        self.resize()

    def hide_panel(self):
        self.panel_visible = False
        self.panel.grid_remove()
        self.resize()

    def set_phase(self, name):
        order = [k for k, _ in PHASES]
        idx = order.index(name) if name in order else -1
        for i, (k, _) in enumerate(PHASES):
            mode = "done" if (name == "done" or (idx >= 0 and i < idx)) else (
                "now" if i == idx else "pending")
            self.badges[k].set_mode(mode)

    def refresh_table(self):
        for (g, key), lbl in self.cell.items():
            lbl.configure(text=str(self.stats[g][key]))
        n = len(self.gaps)
        self.gap_title.configure(text=f"待加工 {n}", fg=ERR if n else MUTED)
        self.tree.delete(*self.tree.get_children())
        for it in self.gaps[-200:]:
            self.tree.insert("", "end", values=(
                str(it.get("标题") or it.get("序号") or "")[:70], it.get("原因") or ""))
        self.dirty = False

    def handle_event(self, e):
        typ = e.get("type")
        if typ == "phase":
            self.set_phase(e.get("name", ""))
        elif typ == "plan":
            total = int(e.get("total") or 0)
            if total:
                self.prog.set_progress(0, total)
        elif typ == "item":
            it = e.get("item") or {}
            g = it.get("group") if it.get("group") in ("video", "album") else "video"
            self.stats[g]["total"] += 1
            self.stats[g]["ok" if it.get("ok") else "gap"] += 1
            if it.get("ai"):
                self.stats["ai"]["total"] += 1
                self.stats["ai"]["ok" if it.get("ok") else "gap"] += 1
            if self.prog._mode == "determinate":
                self.prog.set_progress(self.prog._value + 1, self.prog._maximum)
            self.dirty = True
        elif typ == "gap":
            self.gaps.append(e.get("gap") or {})
            self.dirty = True
        elif typ == "stage":
            name, state = e.get("name"), e.get("state")
            if name in self.badges:
                if state == "failed":
                    self.badges[name].set_mode("failed")
                elif state == "skip":
                    self.badges[name].set_mode("done")

    # ---------------------------------------------------------------- 环境
    def env_check(self):
        self.q.put(("env", engine.safe_call(engine.status)))

    def refresh_env(self):
        threading.Thread(target=self.env_check, daemon=True).start()

    def primary_action(self):
        if self.busy:
            self.stop()
            return
        if self.env_ready:
            self.start()
        else:
            self.open_setup_env()

    def _sync_primary(self):
        if self.busy:
            self.btn.configure(text="停止", command=self.stop, state="normal")
        elif self.env_ready:
            self.btn.configure(text="开始整理", command=self.start, state="normal")
        else:
            self.btn.configure(text="初始化本机环境", command=self.open_setup_env, state="normal")

    def apply_env(self, payload):
        self.env_ready = bool(payload.get("ready"))
        missing = payload.get("missing") or []
        acct = (payload.get("account") or {}).get("nickname") or ""
        if self.env_ready:
            self.show_env("")
            if not self.busy:
                self.set_state(f"已就绪 · {acct}" if acct else "", CYAN)
        else:
            self.show_env(payload.get("message") or "环境未就绪")
            if not self.busy:
                self.set_state(("缺少 " + "、".join(missing)) if missing
                               else (payload.get("message") or "环境未就绪"), ERR)
        if not self.busy:
            self._sync_primary()

    def open_setup_env(self):
        setup_env.open(self.root, on_done=self.refresh_env)

    def open_settings(self):
        settings_ui.open(self.root, on_done=self.refresh_env)

    def pick(self):
        d = filedialog.askdirectory(title="选择交付目录")
        if d:
            self.dest.delete(0, "end")
            self.dest.insert(0, os.path.normpath(d))

    def set_state(self, text, color=MUTED):
        self.full_state = text
        self.state.configure(text=text if len(text) <= 52 else text[:49] + "…", fg=color)

    def show_env(self, message):
        self.env_message = message
        if message:
            self.info.grid()
        else:
            self.info.grid_remove()

    def show_full(self, text):
        text = (text or "").strip()
        if not text:
            return "break"
        try:
            messagebox.showinfo("详情", text, parent=self.root)
        except tk.TclError:
            pass
        return "break"

    def open_result(self):
        if self.last_batch and os.path.isdir(self.last_batch):
            try:
                os.startfile(self.last_batch)
            except OSError:
                pass

    def open_report(self):
        if not self.report and self.last_batch:
            import kbreport
            self.report = kbreport.load(self.last_batch)
        if not self.report:
            return
        import report_ui
        report_ui.open(self.root, self.report, config.load().get("kb_dir", ""))

    def close(self):
        if self.busy:
            if not messagebox.askyesno(APP_NAME, "整理还在进行，关闭会中止本轮且不生成交付。确定停止并退出？",
                                       parent=self.root):
                return
            self.cancel.set()
            self.busy = False
            self.set_state("正在停止…", WARN)
            self.root.after(400, self.root.destroy)
            return
        try:
            for aid in self.root.tk.call("after", "info"):
                self.root.after_cancel(aid)
        except (tk.TclError, TypeError):
            pass
        self.root.destroy()

    # ---------------------------------------------------------------- 执行
    def start(self):
        if self.busy:
            return
        if not self.env_ready:
            self.open_setup_env()
            return
        dest = self.dest.get().strip()
        frm, to = self.frm.get().strip(), self.to.get().strip()
        if not dest:
            self.set_state("请选择交付目录", ERR)
            return
        ok, frm, to, err = engine.parse_range(frm, to)
        if not ok:
            self.set_state(err, ERR)
            return

        self.busy = True
        self.cancel.clear()
        self.last_batch = ""
        self.last_state = {}
        self.report = {}
        self.stats = _blank_stats()
        self.gaps = []
        self.dirty = True
        self.set_phase("check")
        self.open_btn.grid_remove()
        self._show_hint("")
        self.show_panel()
        self.prog.grid()
        self.prog.start()
        self._sync_primary()
        self.set_state("校验账号与项目…")
        _save_prefs(dest=dest, frm=frm, to=to)

        def work():
            r = engine.safe_call(
                engine.sync, dest, frm, to,
                on_event=lambda e: self.q.put(("event", e)),
                on_progress=lambda m: self.q.put(("progress", m)),
                cancel=self.cancel)
            self.q.put(("done", r))

        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if not self.busy:
            return
        if not messagebox.askyesno(APP_NAME, "停止本轮整理？已采集的原始数据会保留，但不会生成交付。",
                                   parent=self.root):
            return
        self.cancel.set()
        self.set_state("正在停止…", WARN)
        self.btn.configure(state="disabled", text="停止中…")

    def start_retry(self):
        if self.busy or not self.last_batch:
            return
        self.busy = True
        self.stats = _blank_stats()
        self.gaps = []
        self.dirty = True
        self.retry_btn.configure(state="disabled", text="续跑中…")
        self.prog.grid()
        self.prog.start()
        self.show_panel()
        self.set_phase("rebuild")
        self.set_state("重跑重建与导出（不重新采集）…")
        self._sync_primary()
        batch = self.last_batch

        def work():
            r = engine.safe_call(
                engine.retry, batch,
                on_event=lambda e: self.q.put(("event", e)),
                on_progress=lambda m: self.q.put(("progress", m)))
            self.q.put(("retry_done", r))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, payload, retried=False):
        self.busy = False
        self.prog.stop()
        self.prog.grid_remove()
        self._sync_primary()
        self.retry_btn.configure(state="normal", text="续跑")
        if payload.get("ok"):
            self.last_batch = payload.get("batch_path") or self.last_batch
            self.last_state = payload.get("state") or {}
            _save_prefs(last_batch=self.last_batch)
            if self.last_batch:
                self.open_btn.grid()
            if payload.get("stats"):
                self.stats = payload["stats"]
            if payload.get("gaps") is not None:
                self.gaps = payload["gaps"]
            self.set_phase("done")
            self.dirty = True
            self.show_env("")
            self.report = payload.get("report") or {}
            if (self.report.get("rows") or []):
                self.report_btn.grid()
            total = int(payload.get("total") or 0)
            new = int(payload.get("new_count") or 0)
            gaps = int(payload.get("gap_count") or 0)
            head = "续跑完成" if retried else "完成"
            self.set_state(f"{head} · {total} 条 · 新增 {new} · 待加工 {gaps}", CYAN)
            self._show_hint(f"待加工 {gaps} 条：明细见 _待加工.csv；补齐后重新整理。" if gaps else "")
        else:
            err = payload.get("error") or "整理失败"
            self.set_state(err, ERR)
            batch = payload.get("batch_path")
            st = payload.get("state") or {}
            if batch:
                self.last_batch = batch
                self.last_state = st
                _save_prefs(last_batch=batch)
                self.open_btn.grid()
            if batch and (st.get("collect") or {}).get("gates_ok") and st.get("stage") != "done":
                self._show_hint("这一批在重建阶段中止，已采集的数据可用「续跑」重试，不必重新采集。")
                self.retry_btn.grid()
            else:
                self._show_hint("")
                self.retry_btn.grid_remove()
        self.resize()

    def _show_hint(self, text):
        self.hint_visible = bool(text)
        if text:
            self.hint_label.configure(text=text)
            self.hint.grid()
        else:
            self.hint.grid_remove()
        self.resize()

    def _restore_last(self, prefs):
        batch = (prefs or {}).get("last_batch") or ""
        if not batch or not os.path.isdir(batch):
            return
        st = engine.read_state(batch)
        if not st:
            return
        self.last_batch = batch
        self.last_state = st
        self.open_btn.grid()
        try:
            import kbreport
            rep = st.get("report") or kbreport.load(batch)
            if rep.get("rows"):
                self.report = rep
                self.report_btn.grid()
        except Exception:
            pass
        if st.get("ok"):
            exp = st.get("export") or {}
            if exp.get("stats"):
                self.stats = exp["stats"]
            self.dirty = True
            self.set_phase("done")
            self.show_panel()
            self.set_state("上次整理已完成；可直接打开查看", TEXT)
            self.refresh_table()
        elif (st.get("collect") or {}).get("gates_ok"):
            self.show_panel()
            self.set_state(st.get("error") or "上次整理未完成", WARN)
            self._show_hint("上次在重建阶段中止，可用「续跑」重试，不必重新采集。")
            self.retry_btn.grid()
        self.resize()

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "progress":
                    if payload:
                        self.set_state(payload)
                elif kind == "event":
                    self.handle_event(payload)
                elif kind == "env":
                    self.apply_env(payload)
                elif kind == "retry_done":
                    self._finish(payload, retried=True)
                else:
                    self._finish(payload, retried=False)
        except queue.Empty:
            pass
        if self.dirty:
            self.refresh_table()
        try:
            if not self.root.winfo_exists():
                return
            self._after_id = self.root.after(60 if self.busy else 140, self.poll)
        except tk.TclError:
            return


def run():
    try:
        root = tk.Tk()
        apply_theme(root)
        fm, fs, family = fonts(root)
        App(root, fm, fs, family)
        root.mainloop()
        return 0
    except Exception as e:
        try:
            from common import data_dir
            log = os.path.join(data_dir(), "startup-error.log")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            messagebox.showerror(APP_NAME, f"启动失败：{type(e).__name__}: {e}\n详情已写入：{log}")
        except Exception:
            pass
        raise
