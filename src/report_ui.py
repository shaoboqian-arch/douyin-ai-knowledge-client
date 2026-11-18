# -*- coding: utf-8 -*-
"""入库报告窗口：原项目那张「环节 / 结果」表，在客户端里按同一口径展示。

只读。数据来自批次里的 `_入库报告.json`，不重新计算。
"""
import os
import tkinter as tk
from tkinter import filedialog, ttk

import detect
import kbreport
from common import APP_NAME
from ui_kit import (
    BG, BORDER, CARD_LINE, CYAN, ERR, FONT_FAMILY, MUTED, PANEL, SAND, TEXT, WARN,
    CapsuleButton, apply_icon, apply_theme, center, fonts,
)

ICON = {"ok": "✅", "warn": "⚠️", "skip": "➖"}
COLOR = {"ok": CYAN, "warn": WARN, "skip": MUTED}


class ReportWindow:
    def __init__(self, root, report, kb_dir="", font_main=None, font_small=None):
        self.root = root
        self.report = report or {}
        self.kb_dir = kb_dir
        self.font_main = font_main or (FONT_FAMILY, 10)
        self.font_small = font_small or (FONT_FAMILY, 9)
        self._result_labels = []

        root.title(f"入库报告 · {APP_NAME}")
        root.configure(bg=BG)
        root.resizable(True, True)
        apply_icon(root)
        apply_theme(root)
        center(root, 760, 520)

        f = tk.Frame(root, bg=BG, padx=18, pady=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        meta = self.report.get("scope") or {}
        scope = (f"{meta.get('from') or '最早'} ~ {meta.get('to') or '最新'}"
                 if (meta.get("from") or meta.get("to")) else "全部收藏")
        acct = (self.report.get("account") or {}).get("nickname") or ""
        tk.Label(f, text="入库报告", font=(self.font_main[0], 13, "bold"),
                 bg=BG, fg=TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        sub = (f"{self.report.get('generated_at', '')} · {scope}"
               + (f" · {acct}" if acct else "")
               + (f" · 续跑" if self.report.get("mode") == "retry" else ""))
        self.sub = tk.Label(f, text=sub, font=self.font_small, bg=BG, fg=MUTED,
                            anchor="w", justify="left", wraplength=700)
        self.sub.grid(row=1, column=0, sticky="ew", pady=(2, 12))

        wrap = tk.Frame(f, bg=PANEL, highlightbackground=CARD_LINE, highlightthickness=1)
        wrap.grid(row=2, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(wrap, bg=PANEL, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        body = tk.Frame(self._canvas, bg=PANEL, padx=18, pady=14)
        body.columnconfigure(1, weight=1)
        self._body_id = self._canvas.create_window((0, 0), window=body, anchor="nw")

        tk.Label(body, text="环节", font=(self.font_small[0], self.font_small[1], "bold"),
                 bg=PANEL, fg=MUTED, anchor="w").grid(
            row=0, column=0, sticky="nw", padx=(0, 16), pady=(0, 8))
        tk.Label(body, text="结果", font=(self.font_small[0], self.font_small[1], "bold"),
                 bg=PANEL, fg=MUTED, anchor="w").grid(
            row=0, column=1, sticky="w", pady=(0, 8))
        tk.Frame(body, bg=CARD_LINE, height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for i, item in enumerate(self.report.get("rows") or [], 2):
            state = item.get("状态")
            tk.Label(body, text=item.get("环节", ""), font=self.font_main, bg=PANEL,
                     fg=TEXT, anchor="nw", width=10).grid(
                row=i, column=0, sticky="nw", padx=(0, 16), pady=(0, 10))
            lbl = tk.Label(body, text=f"{ICON.get(state, '')} {item.get('结果', '')}",
                           font=self.font_main, bg=PANEL, fg=COLOR.get(state, TEXT),
                           anchor="nw", justify="left", wraplength=560)
            lbl.grid(row=i, column=1, sticky="ew", pady=(0, 10))
            self._result_labels.append(lbl)

        body.bind("<Configure>", self._on_body)
        self._canvas.bind("<Configure>", self._on_canvas)
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

        foot = tk.Frame(f, bg=BG)
        foot.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        foot.columnconfigure(0, weight=1)
        self.state = tk.Label(foot, text="", font=self.font_small, bg=BG, fg=MUTED,
                              anchor="w", justify="left", wraplength=360)
        self.state.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        CapsuleButton(foot, text="复制", command=self.copy, width=72, height=34,
                      font=self.font_small).grid(row=0, column=1, padx=(0, 8))
        CapsuleButton(foot, text="存为 md", command=self.save_md, width=88, height=34,
                      font=self.font_small).grid(row=0, column=2, padx=(0, 8))
        kb_ok = bool(kb_dir and os.path.isdir(kb_dir))
        col = 3
        if kb_ok:
            CapsuleButton(foot, text="打开知识库", command=self.open_kb, primary=True,
                          width=104, height=34, font=self.font_small).grid(
                row=0, column=col, padx=(0, 8))
            col += 1
        CapsuleButton(foot, text="关闭", command=self.close, primary=not kb_ok,
                      width=72, height=34, font=self.font_small).grid(row=0, column=col)

        root.bind("<Configure>", self._on_root, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _on_body(self, _event=None):
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas(self, event):
        try:
            self._canvas.itemconfigure(self._body_id, width=max(1, event.width))
            wrap = max(200, int(event.width) - 140)
            for lbl in self._result_labels:
                if int(lbl.cget("wraplength") or 0) != wrap:
                    lbl.configure(wraplength=wrap)
        except tk.TclError:
            pass

    def _on_root(self, event):
        if event.widget is not self.root:
            return
        wrap = max(240, int(event.width) - 60)
        try:
            if int(self.sub.cget("wraplength") or 0) != wrap:
                self.sub.configure(wraplength=wrap)
        except tk.TclError:
            pass

    def _wheel(self, event):
        try:
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta:
                self._canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_wheel(self, _event=None):
        self._canvas.bind_all("<MouseWheel>", self._wheel)

    def _unbind_wheel(self, _event=None):
        self._canvas.unbind_all("<MouseWheel>")

    def close(self):
        self._unbind_wheel()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def set_state(self, text, color=MUTED):
        try:
            self.state.configure(text=text or "", fg=color)
        except tk.TclError:
            pass

    def copy(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(kbreport.render_md(self.report))
            self.set_state("已复制到剪贴板", CYAN)
        except tk.TclError as e:
            self.set_state(f"复制失败：{e}", ERR)

    def save_md(self):
        p = filedialog.asksaveasfilename(
            title="保存入库报告", defaultextension=".md",
            filetypes=[("Markdown", "*.md")],
            initialfile="入库报告.md")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(kbreport.render_md(self.report))
            self.set_state("已保存", CYAN)
        except OSError as e:
            self.set_state(f"保存失败：{e}", ERR)

    def open_kb(self):
        if detect.open_in_obsidian(self.kb_dir):
            return
        try:
            os.startfile(self.kb_dir)
        except OSError as e:
            self.set_state(f"无法打开知识库：{e}", ERR)


def open(parent=None, report=None, kb_dir=""):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    fm, fs, _family = fonts(root)
    ReportWindow(root, report, kb_dir, fm, fs)
    if parent is None:
        root.mainloop()
    return root
