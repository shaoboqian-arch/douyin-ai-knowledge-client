# -*- coding: utf-8 -*-
"""入库报告窗口：原项目那张「环节 / 结果」表，在客户端里按同一口径展示。

只读。数据来自批次里的 `_入库报告.json`，不重新计算。
"""
import json
import os
import tkinter as tk
from tkinter import filedialog

import detect
import kbreport
from common import APP_NAME
from ui_kit import (
    BG, BORDER, CYAN, ERR, MUTED, PANEL, SURFACE, TEXT, WARN,
    CapsuleButton, apply_icon, apply_theme, center, fonts,
)

ICON = {"ok": "✅", "warn": "⚠️", "skip": "➖"}
COLOR = {"ok": CYAN, "warn": WARN, "skip": MUTED}


class ReportWindow:
    def __init__(self, root, report, kb_dir="", font_main=None, font_small=None):
        self.root = root
        self.report = report or {}
        self.kb_dir = kb_dir
        self.font_main = font_main or ("Microsoft YaHei UI", 10)
        self.font_small = font_small or ("Microsoft YaHei UI", 9)

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
        tk.Label(f, text=f"入库报告", font=(self.font_main[0], 13, "bold"),
                 bg=BG, fg=TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        sub = (f"{self.report.get('generated_at', '')} · {scope}"
               + (f" · {acct}" if acct else "")
               + (f" · 续跑" if self.report.get("mode") == "retry" else ""))
        tk.Label(f, text=sub, font=self.font_small, bg=BG, fg=MUTED,
                 anchor="w").grid(row=1, column=0, sticky="w", pady=(2, 12))

        body = tk.Frame(f, bg=PANEL, highlightbackground=BORDER, highlightthickness=1,
                        padx=14, pady=12)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        tk.Label(body, text="环节", font=self.font_small, bg=PANEL, fg=MUTED,
                 anchor="w").grid(row=0, column=0, sticky="nw", padx=(0, 16), pady=(0, 8))
        tk.Label(body, text="结果", font=self.font_small, bg=PANEL, fg=MUTED,
                 anchor="w").grid(row=0, column=1, sticky="w", pady=(0, 8))
        for i, item in enumerate(self.report.get("rows") or [], 1):
            state = item.get("状态")
            tk.Label(body, text=item.get("环节", ""), font=self.font_main, bg=PANEL,
                     fg=TEXT, anchor="nw", width=10).grid(
                row=i, column=0, sticky="nw", padx=(0, 16), pady=(0, 10))
            tk.Label(body, text=f"{ICON.get(state, '')} {item.get('结果', '')}",
                     font=self.font_main, bg=PANEL, fg=COLOR.get(state, TEXT),
                     anchor="nw", justify="left", wraplength=560).grid(
                row=i, column=1, sticky="ew", pady=(0, 10))

        foot = tk.Frame(f, bg=BG)
        foot.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        foot.columnconfigure(0, weight=1)
        CapsuleButton(foot, text="复制", command=self.copy, width=72, height=32,
                      font=self.font_small).grid(row=0, column=1, padx=(0, 8))
        CapsuleButton(foot, text="存为 md", command=self.save_md, width=88, height=32,
                      font=self.font_small).grid(row=0, column=2, padx=(0, 8))
        if kb_dir and os.path.isdir(kb_dir):
            CapsuleButton(foot, text="打开知识库", command=self.open_kb, width=100,
                          height=32, font=self.font_small).grid(row=0, column=3, padx=(0, 8))
        CapsuleButton(foot, text="关闭", command=root.destroy, width=72, height=32,
                      font=self.font_small).grid(row=0, column=4)

    def copy(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(kbreport.render_md(self.report))
        except tk.TclError:
            pass

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
        except OSError:
            pass

    def open_kb(self):
        if not detect.open_in_obsidian(self.kb_dir):
            try:
                os.startfile(self.kb_dir)
            except OSError:
                pass


def open(parent=None, report=None, kb_dir=""):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    fm, fs, _family = fonts(root)
    ReportWindow(root, report, kb_dir, fm, fs)
    if parent is None:
        root.mainloop()
    return root
