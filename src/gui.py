# -*- coding: utf-8 -*-
"""主界面：先写清「导出到哪、导出哪段」，再给两个明确的动作（全仓同步 / 仅导出）。"""
import datetime as dt
import json
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config
import engine
import settings as settings_ui
import setup_env
from common import (
    APP_NAME, PHASES, VERSION, DeferredCall, app_dir, format_gap_rows,
    gap_heading, is_frozen, prefs_path,
)
from ui_kit import (
    ACCENT, BG, BORDER, CARD, CARD_LINE, CYAN, DONE_BG, ERR, ERR_BG, MUTED,
    PANEL, SURFACE, TEXT, WARN,
    CapsuleButton, DatePicker, PhaseBadge, ProgressBar, RoundedEntry, Tooltip,
    apply_icon, apply_theme, center, fonts,
)

W = 780
BASE_H = 326
PANEL_H = 372
HINT_H = 76

GROUPS = (("video", "视频"), ("album", "图集"), ("ai", "其中 · AI 笔记"))


def default_dest():
    if is_frozen():
        return os.path.join(os.path.expanduser("~"), "Documents", APP_NAME)
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


def _card(parent, title, title_font):
    """带标题的分区卡片，返回可放内容的 body。"""
    outer = tk.Frame(parent, bg=CARD, highlightbackground=CARD_LINE,
                     highlightthickness=1)
    inner = tk.Frame(outer, bg=CARD, padx=18, pady=14)
    inner.pack(fill="both", expand=True)
    tk.Label(inner, text=title, font=title_font,
             bg=CARD, fg=TEXT, anchor="w").pack(fill="x", pady=(0, 12))
    body = tk.Frame(inner, bg=CARD)
    body.pack(fill="both", expand=True)
    return outer, body


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
        self.rows_ok = False
        self.rows_mtime = ""
        self._env_seq = 0
        self.last_batch = ""
        # 日期范围提示的预检要读全量 rows + 转写稿，放后台线程，别卡住窗口（F-3）。
        # with_args 让回调知道这份结果对应哪段日期，供点击动作复用。
        self._range_call = DeferredCall(root, engine.preflight, self._on_preflight,
                                        with_args=True)
        self._last_preflight = None
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

        f = tk.Frame(root, bg=BG, padx=24, pady=18)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(6, weight=1)

        # 标题行
        head = tk.Frame(f, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="抖音收藏整理", font=(family, 16, "bold"),
                 bg=BG, fg=TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        self.btn = CapsuleButton(head, text="⚠️ 全仓同步", command=self.primary_action,
                                 primary=True, width=118, height=32,
                                 font=(family, 10, "bold"))
        self.btn.grid(row=0, column=1, sticky="e", padx=(0, 8))
        Tooltip(self.btn, lambda: "全量采集全部收藏后重建知识库，再导出所选范围；约 25 分钟",
                font=font_small)
        CapsuleButton(head, text="设置", command=self.open_settings, width=72,
                      height=32, font=font_small).grid(row=0, column=2, sticky="e")

        self.summary = tk.Label(f, text="正在读取知识库现状…", font=font_small,
                                bg=BG, fg=MUTED, anchor="w")
        self.summary.grid(row=1, column=0, sticky="w", pady=(2, 14))

        # 导出设置
        card, body = _card(f, "导出设置", (family, 11, "bold"))
        card.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        tk.Label(body, text="导出到", font=font_main, bg=CARD, fg=MUTED).grid(
            row=0, column=0, sticky="w", pady=(0, 12))
        self.dest = RoundedEntry(body, font=font_main, path=True, path_font=font_small)
        self.dest.grid(row=0, column=1, sticky="ew", padx=(14, 10), pady=(0, 12))
        CapsuleButton(body, text="浏览…", command=self.pick, width=88, height=36,
                      font=font_small).grid(row=0, column=2, pady=(0, 12))
        self.export_btn = CapsuleButton(body, text="仅导出", command=self.start_export,
                                        width=88, height=36, font=font_small)
        self.export_btn.grid(row=1, column=2, pady=(0, 2))
        self.export_hint = "用项目里已有的数据写批次，不采集、不联网，秒级完成"
        Tooltip(self.export_btn, lambda: self.export_hint, font=font_small)

        tk.Label(body, text="作品发布日期", font=font_main, bg=CARD, fg=MUTED).grid(
            row=1, column=0, sticky="w")
        rng = tk.Frame(body, bg=CARD)
        rng.grid(row=1, column=1, sticky="ew", padx=(14, 10))
        rng.columnconfigure(0, weight=1)
        rng.columnconfigure(2, weight=1)
        self.frm = RoundedEntry(rng, font=font_main, width=10, pxwidth=170,
                                placeholder="不限", panel_bg=CARD)
        self.to = RoundedEntry(rng, font=font_main, width=10, pxwidth=170,
                               placeholder="不限", panel_bg=CARD)
        self.frm.grid(row=0, column=0, sticky="ew")
        self.to.grid(row=0, column=2, sticky="ew")
        tk.Label(rng, text="—", font=font_main, bg=CARD, fg=MUTED).grid(
            row=0, column=1, padx=10)
        self._cal_from = DatePicker(self.frm, font=font_small, embedded=True,
                                    on_pick=self._schedule_range_check)
        self._cal_to = DatePicker(self.to, font=font_small, embedded=True,
                                  on_pick=self._schedule_range_check)
        self.frm.bind("<KeyRelease>", lambda _e: self._schedule_range_check())
        self.to.bind("<KeyRelease>", lambda _e: self._schedule_range_check())

        self.range_hint = tk.Label(body, text="留空表示全部；只影响导出的笔记，不影响采集",
                                   font=font_small, bg=CARD, fg=MUTED, anchor="w")
        self.range_hint.grid(row=2, column=1, sticky="w",
                             padx=(14, 10), pady=(6, 0))

        self.first_hint = tk.Label(
            f, text="首次使用：先做一次「全仓同步」（约 25 分钟）\n"
                    "完成后「仅导出」才可用",
            font=font_small, bg=BG, fg=WARN, anchor="w", justify="left")
        self.first_hint.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.first_hint.grid_remove()

        self.prog = ProgressBar(f, height=8)
        self.prog.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.prog.grid_remove()

        sf = tk.Frame(f, bg=BG)
        sf.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        sf.columnconfigure(0, weight=1)
        self.state = tk.Label(sf, text="", font=font_small, fg=MUTED, bg=BG,
                              anchor="w", wraplength=360, justify="left", takefocus=1)
        self.state.grid(row=0, column=0, sticky="w")
        self.info = tk.Label(sf, text="ⓘ", font=font_small, fg=WARN, bg=BG,
                             cursor="question_arrow", takefocus=1)
        self.info.grid(row=0, column=1, padx=(6, 0))
        self.info.grid_remove()
        self.report_btn = CapsuleButton(sf, text="入库报告", command=self.open_report,
                                        width=88, height=30, font=font_small)
        self.report_btn.grid(row=0, column=2, padx=(6, 0))
        self.report_btn.grid_remove()
        self.retry_btn = CapsuleButton(sf, text="续跑", command=self.start_retry,
                                       width=64, height=30, font=font_small)
        self.retry_btn.grid(row=0, column=3, padx=(6, 0))
        self.retry_btn.grid_remove()
        self.open_btn = CapsuleButton(sf, text="打开", command=self.open_result,
                                      width=64, height=30, font=font_small)
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
        self.panel.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
        self.panel.grid_remove()

        prefs = _load_prefs()
        cfg = config.load()
        self.dest.insert(0, cfg.get("dest") or prefs.get("dest") or default_dest())
        self.frm.insert(0, cfg.get("frm") or "")
        self.to.insert(0, cfg.get("to") or "")

        root.bind("<Return>", self._on_root_return)
        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Configure>", self._on_configure)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Destroy>",
                  lambda e: self._range_call.destroy()
                  if getattr(e, "widget", None) is root else None, add="+")
        self._after_id = root.after(60, self.poll)
        self.refresh_env()
        self.root.after(120, lambda: self._restore_last(prefs))
        self.root.after_idle(self.dest.reveal_end)
        self.root.after(500, self._schedule_range_check)

    # ---------------------------------------------------------------- 进度表
    def _build_panel(self, parent):
        p = tk.Frame(parent, bg=CARD, highlightbackground=CARD_LINE,
                     highlightthickness=1, padx=16, pady=14)
        p.columnconfigure(0, weight=1)
        p.rowconfigure(3, weight=1)

        hdr = tk.Frame(p, bg=CARD)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(6, weight=1)
        self.badges = {}
        for i, (key, label) in enumerate(PHASES):
            b = PhaseBadge(hdr, text=label, font=self.font_small, width=66, height=24)
            b.grid(row=0, column=i, padx=(0, 6))
            self.badges[key] = b
        CapsuleButton(hdr, text="收起", command=self.hide_panel,
                      width=58, height=24, font=self.font_small).grid(row=0, column=6, sticky="e")

        tbl = tk.Frame(p, bg=CARD)
        tbl.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        for j, c in enumerate(("类别", "总数", "已写出", "待加工")):
            tk.Label(tbl, text=c, font=self.font_small, fg=MUTED, bg=CARD,
                     width=12 if j else 16,
                     anchor="w" if j == 0 else "e").grid(row=0, column=j, padx=(0, 6))
        self.cell = {}
        for i, (g, name) in enumerate(GROUPS, 1):
            tk.Label(tbl, text=name, font=self.font_small, fg=TEXT, bg=CARD,
                     width=16, anchor="w").grid(row=i, column=0, sticky="w")
            for j, key in enumerate(("total", "ok", "gap"), 1):
                v = tk.Label(tbl, text="0", font=self.font_small, fg=TEXT, bg=CARD,
                             width=12, anchor="e")
                v.grid(row=i, column=j, padx=(0, 6))
                self.cell[(g, key)] = v

        gap_row = tk.Frame(p, bg=CARD)
        gap_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        gap_row.columnconfigure(0, weight=1)
        self.gap_title = tk.Label(gap_row, text="待加工 0", font=self.font_small,
                                  fg=MUTED, bg=CARD, anchor="w", justify="left",
                                  wraplength=560)
        self.gap_title.grid(row=0, column=0, sticky="w")
        self.patch_btn = CapsuleButton(gap_row, text="补加工", command=self.open_gaps,
                                       width=76, height=26, font=self.font_small)
        self.patch_btn.grid(row=0, column=1, sticky="e")
        self.patch_btn.grid_remove()
        self.tree = ttk.Treeview(p, columns=("name", "reason"), show="headings", height=4)
        self.tree.heading("name", text="条目")
        self.tree.heading("reason", text="缺什么")
        self.tree.column("name", width=400, anchor="w")
        self.tree.column("reason", width=260, anchor="w")
        sb = ttk.Scrollbar(p, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=3, column=0, sticky="nsew")
        sb.grid(row=3, column=1, sticky="ns")
        self._gap_full = {}
        self.tree.bind("<ButtonRelease-1>", self._open_gap)
        self.tree.bind("<Return>", self._open_gap)
        self.tree.bind("<Double-1>", self._open_gap)

        self.hint = tk.Frame(p, bg=ERR_BG, padx=10, pady=8)
        self.hint.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.hint_label = tk.Label(self.hint, text="", font=self.font_small,
                                   fg=TEXT, bg=ERR_BG, justify="left", anchor="w",
                                   wraplength=620)
        self.hint_label.pack(fill="x")
        self.hint.grid_remove()
        return p

    def resize(self):
        h = BASE_H
        if self.busy or self.prog.winfo_manager():
            h += 20
        if self.first_hint.winfo_manager():
            h += 40          # 两行提示 + 上边距；24 会把底部状态行裁掉
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
        state_w = max(200, int(event.width) - 340)
        hint_w = max(220, int(event.width) - 100)
        if int(self.state.cget("wraplength") or 0) != state_w:
            self.state.configure(wraplength=state_w)
        if int(self.hint_label.cget("wraplength") or 0) != hint_w:
            self.hint_label.configure(wraplength=hint_w)
        if int(self.gap_title.cget("wraplength") or 0) != hint_w:
            self.gap_title.configure(wraplength=hint_w)

    def show_panel(self):
        self.panel_visible = True
        self.panel.grid()
        self.resize()

    def hide_panel(self):
        self.panel_visible = False
        self.panel.grid_remove()
        self.resize()

    def set_phase(self, name, skip_before=False):
        order = [k for k, _ in PHASES]
        idx = order.index(name) if name in order else -1
        for i, (k, _) in enumerate(PHASES):
            if skip_before and idx >= 0 and i < idx:
                mode = "pending"
            elif name == "done" or (idx >= 0 and i < idx):
                mode = "done"
            elif i == idx:
                mode = "now"
            else:
                mode = "pending"
            self.badges[k].set_mode(mode)

    def refresh_table(self):
        for (g, key), lbl in self.cell.items():
            lbl.configure(text=f"{self.stats[g][key]:,}")
        n = len(self.gaps)
        self.gap_title.configure(text=gap_heading(n), fg=ERR if n else MUTED)
        if n:
            self.patch_btn.grid()
        else:
            self.patch_btn.grid_remove()
        self.tree.delete(*self.tree.get_children())
        self._gap_full = {}
        for title, reason, full in format_gap_rows(self.gaps):
            iid = self.tree.insert("", "end", values=(title, reason))
            self._gap_full[iid] = full
        self.dirty = False

    def open_gaps(self):
        """把待加工条目整理成一份可复制的待办，交给外部 AI 加工。"""
        if not self.gaps:
            return
        win = tk.Toplevel(self.root)
        win.title(f"待加工 · {len(self.gaps)} 条")
        win.configure(bg=BG)
        win.geometry("760x560")
        apply_icon(win)
        f = tk.Frame(win, bg=BG, padx=18, pady=14)
        f.pack(fill="both", expand=True)
        tk.Label(f, text=f"待加工 {len(self.gaps)} 条", font=(self.family, 13, "bold"),
                 bg=BG, fg=TEXT, anchor="w").pack(fill="x")
        tk.Label(f, text="这些条目缺 AI 判定 / 转写 / 介绍 / 概念；补齐后点「仅导出」刷新批次，"
                        "不必重新采集。", font=self.font_small, bg=BG, fg=MUTED,
                 anchor="w", justify="left").pack(fill="x", pady=(2, 10))
        box = tk.Text(f, font=self.font_small, bg=PANEL, fg=TEXT, relief="flat",
                      wrap="word", padx=10, pady=8)
        box.pack(fill="both", expand=True)
        lines = []
        for i, it in enumerate(self.gaps, 1):
            lines.append(f"{i}. [{it.get('序号','')}] {it.get('标题','')}")
            lines.append(f"   缺：{it.get('原因','')}")
            if it.get("作品链接"):
                lines.append(f"   作品：{it['作品链接']}")
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        row.columnconfigure(0, weight=1)

        def copy():
            try:
                win.clipboard_clear()
                win.clipboard_append("\n".join(lines))
                self.set_state("待加工清单已复制", CYAN)
            except tk.TclError:
                pass

        def open_work():
            project = config.load().get("project_dir", "")
            p = os.path.join(project, "work") if project else ""
            if p and os.path.isdir(p):
                os.startfile(p)

        CapsuleButton(row, text="复制清单", command=copy, width=92, height=32,
                      font=self.font_small).grid(row=0, column=1, padx=(0, 8))
        CapsuleButton(row, text="打开 work", command=open_work, width=96, height=32,
                      font=self.font_small).grid(row=0, column=2, padx=(0, 8))
        CapsuleButton(row, text="关闭", command=win.destroy, width=72, height=32,
                      font=self.font_small).grid(row=0, column=3)

    def _open_gap(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return "break"
        text = (self._gap_full or {}).get(sel[0], "")
        return self.show_full(text)

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
    def env_check(self, seq=0):
        self.q.put(("env", (engine.safe_call(engine.status), seq)))

    def refresh_env(self):
        self._env_seq += 1
        threading.Thread(target=self.env_check, args=(self._env_seq,), daemon=True).start()

    def _on_root_return(self, event):
        if event.widget is self.btn:
            self.primary_action()
        elif event.widget is self.export_btn:
            self.start_export()
        return None

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
            self.export_btn.configure(state="disabled")
        elif self.env_ready:
            self.btn.configure(text="⚠️ 全仓同步", command=self.start, state="normal")
            self.export_btn.configure(state="normal" if self.rows_ok else "disabled")
            if not self.rows_ok:
                self.export_hint = "还没有整理结果：先点右上角「全仓同步」跑一次"
            else:
                stamp = self.rows_mtime
                self.export_hint = (f"用现有数据写批次（截至 {stamp}），不采集、不联网，秒级完成"
                                    if stamp else "用项目里已有的数据写批次，不采集、不联网")
        else:
            self.btn.configure(text="初始化本机环境", command=self.open_setup_env,
                               state="normal")
            self.export_btn.configure(state="disabled")

    def apply_env(self, payload):
        self.env_ready = bool(payload.get("ready"))
        self.rows_ok = bool(payload.get("rows_ok"))
        self.rows_mtime = payload.get("rows_mtime") or ""
        missing = payload.get("missing") or []
        acct = (payload.get("account") or {}).get("nickname") or ""
        stats = payload.get("kb_stats") or {}
        if stats:
            self.summary.configure(
                text=f"知识库：{stats.get('total', 0):,} 收藏 · "
                     f"{stats.get('ai', 0):,} AI 笔记 · {stats.get('concepts', 0):,} 概念 · "
                     f"{stats.get('pairs', 0):,} 共现")
        else:
            self.summary.configure(text="尚未建立知识库；首次使用先做一次「全仓同步」")
        if self.env_ready:
            self.show_env("")
            if not self.busy:
                self.set_state(f"已就绪 · {acct}" if acct else "已就绪", CYAN)
        else:
            self.show_env(payload.get("message") or "环境未就绪")
            if not self.busy:
                self.set_state(("缺少 " + "、".join(missing)) if missing
                               else (payload.get("message") or "环境未就绪"), ERR)
        if self.env_ready and not self.rows_ok:
            self.first_hint.grid()
        else:
            self.first_hint.grid_remove()
        self.resize()
        if not self.busy:
            self._sync_primary()

    def open_setup_env(self):
        setup_env.open(self.root, on_done=self.refresh_env)

    def open_settings(self):
        settings_ui.open(self.root, on_done=self.refresh_env)

    def pick(self):
        d = filedialog.askdirectory(title="选择导出目录")
        if d:
            self.dest.delete(0, "end")
            self.dest.insert(0, os.path.normpath(d))
            self.dest.reveal_end()

    def set_state(self, text, color=MUTED):
        self.full_state = text
        self.state.configure(text=text if len(text) <= 56 else text[:53] + "…", fg=color)

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
            except OSError as e:
                self.set_state(f"无法打开目录：{e}", ERR)

    def open_report(self):
        if not self.report and self.last_batch:
            import kbreport
            self.report = kbreport.load(self.last_batch)
        if not self.report:
            return
        import report_ui
        report_ui.open(self.root, self.report, config.load().get("kb_dir", ""))

    def close(self):
        self._range_call.destroy()
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

    # ---------------------------------------------------------------- 范围
    def _range_values(self):
        frm, to = self.frm.get().strip(), self.to.get().strip()
        ok, frm, to, err = engine.parse_range(frm, to)
        return ok, frm, to, err

    def _schedule_range_check(self):
        try:
            if getattr(self, "_range_job", None):
                self.root.after_cancel(self._range_job)
        except (tk.TclError, ValueError):
            pass
        try:
            self._range_job = self.root.after(350, self._update_range_hint)
        except tk.TclError:
            pass

    def _update_range_hint(self):
        ok, frm, to, _err = self._range_values()
        if not ok:
            self.range_hint.configure(text="日期格式 YYYY-MM-DD；留空表示全部", fg=WARN)
            return
        # 只发请求，不在这里等结果；过期结果由 DeferredCall 丢弃。
        self._range_call.run(frm, to)

    def _on_preflight(self, pre, args=()):
        """后台预检结果的唯一落地点：仍在主线程更新文字。"""
        if not isinstance(pre, dict):
            return
        if pre.get("ok"):
            self._last_preflight = {"key": tuple(args[:2]), "at": time.time(),
                                    "data": pre}
        if not pre.get("ok"):
            self.range_hint.configure(
                text="留空表示全部；只影响导出的笔记，不影响采集", fg=MUTED)
            return
        n = int(pre.get("in_range") or 0)
        if n:
            by_type = pre.get("by_type") or {}
            self.range_hint.configure(
                text=f"范围内 {n:,} 条（视频 {by_type.get('视频', 0):,} · "
                     f"图集 {by_type.get('图集', 0):,}）；采集仍为全量", fg=CYAN)
        else:
            self.range_hint.configure(
                text="范围内 0 条：换一个日期，或留空导出全部", fg=WARN)

    def _preflight_cached(self, frm, to):
        """点动作按钮时复用刚算过的范围预检，避免再全量解析一次（F-3）。"""
        c = getattr(self, "_last_preflight", None)
        if c and c.get("key") == (frm, to) and time.time() - c.get("at", 0) < 30:
            return c["data"]
        return engine.safe_call(engine.preflight, frm, to)

    def _confirm_empty_range(self, n):
        return messagebox.askyesno(
            "范围内没有条目",
            f"所选作品发布日期范围内 0 条。\n\n"
            f"「⚠️ 全仓同步」仍会先采集全部收藏（约 25 分钟）、重建知识库，"
            f"最后写出一份没有明细的《导出报告》。\n"
            f"仍要继续吗？",
            parent=self.root)

    # ---------------------------------------------------------------- 执行
    def start(self):
        if self.busy:
            return
        if not self.env_ready:
            self.open_setup_env()
            return
        dest = self.dest.get().strip()
        ok, frm, to, err = self._range_values()
        if not dest:
            self.set_state("请先选导出目录", ERR)
            return
        if not ok:
            self.set_state(err, ERR)
            return
        pre = self._preflight_cached(frm, to)
        if pre.get("ok") and int(pre.get("in_range") or 0) == 0:
            if not self._confirm_empty_range(0):
                return

        self.busy = True
        self.cancel.clear()
        self.last_batch = ""
        self._last_preflight = None
        self.last_state = {}
        self.report = {}
        self.stats = _blank_stats()
        self.gaps = []
        self.dirty = True
        self.set_phase("check")
        self.report_btn.grid_remove()
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

    def start_export(self):
        if self.busy:
            return
        if not self.env_ready:
            self.open_setup_env()
            return
        dest = self.dest.get().strip()
        ok, frm, to, err = self._range_values()
        if not dest:
            self.set_state("请先选导出目录", ERR)
            return
        if not ok:
            self.set_state(err, ERR)
            return
        pre = self._preflight_cached(frm, to)
        if pre.get("ok") and int(pre.get("in_range") or 0) == 0:
            messagebox.showinfo(
                "范围内没有条目",
                "所选作品发布日期范围内 0 条，未生成批次。\n换一个日期，或留空导出全部。",
                parent=self.root)
            return

        self.busy = True
        self.cancel.clear()
        self.last_batch = ""
        self._last_preflight = None
        self.last_state = {}
        self.report = {}
        self.stats = _blank_stats()
        self.gaps = []
        self.dirty = True
        self.set_phase("export", skip_before=True)
        self.report_btn.grid_remove()
        self.open_btn.grid_remove()
        self._show_hint("")
        self.show_panel()
        self.prog.grid()
        self.prog.start()
        self._sync_primary()
        self.set_state("用现有数据写批次…")
        _save_prefs(dest=dest, frm=frm, to=to)

        def work():
            r = engine.safe_call(
                engine.export_only, dest, frm, to,
                on_event=lambda e: self.q.put(("event", e)),
                on_progress=lambda m: self.q.put(("progress", m)))
            self.q.put(("export_done", r))

        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if not self.busy:
            return
        if not messagebox.askyesno(APP_NAME, "停止本轮？已采集的原始数据会保留，但不会生成交付。",
                                   parent=self.root):
            return
        self.cancel.set()
        self.set_state("正在停止…", WARN)
        self.btn.configure(state="disabled", text="停止中…")
        self.export_btn.configure(state="disabled")

    def start_retry(self):
        if self.busy or not self.last_batch:
            return
        self.busy = True
        self.cancel.clear()
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
                on_progress=lambda m: self.q.put(("progress", m)),
                cancel=self.cancel)
            self.q.put(("retry_done", r))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, payload, mode="sync"):
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
            if mode == "sync":
                self.set_phase("done")
            else:
                self.badges["export"].set_mode("done")
                self.badges["done"].set_mode("done")
            self.dirty = True
            self.show_env("")
            self.report = payload.get("report") or {}
            if (self.report.get("rows") or []):
                self.report_btn.grid()
            total = int(payload.get("total") or 0)
            gaps = int(payload.get("gap_count") or 0)
            if mode == "export":
                self.set_state(f"导出完成 · {total:,} 条 · 待加工 {gaps:,}", CYAN)
            elif mode == "retry":
                self.set_state(f"续跑完成 · {total:,} 条 · 待加工 {gaps:,}", CYAN)
            else:
                new = int(payload.get("new_count") or 0)
                self.set_state(f"完成 · {total:,} 条 · 新增 {new:,} · 待加工 {gaps:,}", CYAN)
            self._show_hint(f"待加工 {gaps:,} 条：明细见批次《导出报告》的待加工一节；"
                            "补齐后点「仅导出」刷新批次。" if gaps else "")
        else:
            err = payload.get("error") or "操作失败"
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
        self._schedule_range_check()
        self.refresh_env()
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
            self.set_state("上次已完成；点「打开」查看批次", TEXT)
            self.refresh_table()
        elif (st.get("collect") or {}).get("gates_ok"):
            self.show_panel()
            self.set_state(st.get("error") or "上次未完成", WARN)
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
                    data, seq = payload if isinstance(payload, tuple) else (payload, None)
                    if seq is not None and seq != self._env_seq:
                        continue        # 丢弃过期的环境检查结果
                    self.apply_env(data)
                elif kind == "retry_done":
                    self._finish(payload, mode="retry")
                elif kind == "export_done":
                    self._finish(payload, mode="export")
                else:
                    self._finish(payload, mode="sync")
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
