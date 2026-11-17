# -*- coding: utf-8 -*-
"""初始化本机环境：项目目录 → 抖音账号 → 知识库目录，三项就绪后主按钮才变成「开始整理」。

对应 wx V0.4.3 的三步初始化（账号目录 / 数据库密钥 / 图片密钥）；
本项目把「密钥」换成「账号确认」——抖音这边登录态在项目自己的 Volume/settings.json 里，
客户端只需要读它是否存在，不复制、不保存 Cookie。
"""
import json
import os
import threading
import tkinter as tk
from tkinter import filedialog

import config
import detect
import pipeline
from common import APP_NAME, data_dir
from ui_kit import (
    BG, BORDER, CYAN, ERR, MUTED, PANEL, SURFACE, TEXT, WARN,
    CapsuleButton, RoundedEntry, ToggleSwitch, apply_icon, apply_theme, center, fonts,
)


class Setup:
    def __init__(self, root, font_main, font_small, family, on_done=None):
        self.root = root
        self.on_done = on_done
        self.font_main, self.font_small = font_main, font_small
        self.cfg = config.load()
        self.probed = {"nickname": "", "sec_uid": ""}
        self.busy = False

        root.title(f"初始化 {APP_NAME}")
        root.resizable(False, False)
        root.configure(bg=BG)
        apply_icon(root)
        apply_theme(root)
        center(root, 680, 424)

        f = tk.Frame(root, bg=BG, padx=20, pady=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        tk.Label(f, text="项目目录", font=font_main, bg=BG, fg=MUTED).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        self.project = RoundedEntry(f, font=font_main, path=True, path_font=font_small)
        self.project.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=(0, 10))
        self.project.insert(0, self.cfg.get("project_dir", ""))
        CapsuleButton(f, text="自动发现", command=self.autodetect, width=78, height=36,
                      font=font_small).grid(row=0, column=2, padx=(0, 6), pady=(0, 10))
        CapsuleButton(f, text="浏览…", command=self.pick_project, width=64, height=36,
                      font=font_small).grid(row=0, column=3, pady=(0, 10))

        tk.Label(f, text="抖音账号", font=font_main, bg=BG, fg=MUTED).grid(
            row=1, column=0, sticky="w", pady=(0, 10))
        self.account = RoundedEntry(f, font=font_main)
        self.account.grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=(0, 10))
        self.account.insert(0, self.cfg.get("expect_nickname", ""))
        self.account.set_readonly(True)
        self.verify_btn = CapsuleButton(f, text="校验账号", command=self.probe, width=78,
                                        height=36, font=font_small)
        self.verify_btn.grid(row=1, column=2, padx=(0, 6), pady=(0, 10))
        CapsuleButton(f, text="采用", command=self.adopt, width=64, height=36,
                      font=font_small).grid(row=1, column=3, pady=(0, 10))
        tk.Label(f, text="请先校验账号，再点采用", font=font_small, bg=BG, fg=MUTED,
                 anchor="w").grid(row=2, column=1, columnspan=3, sticky="w",
                                  padx=(12, 0), pady=(0, 8))

        tk.Label(f, text="知识库", font=font_main, bg=BG, fg=MUTED).grid(
            row=3, column=0, sticky="w", pady=(0, 14))
        self.kb = RoundedEntry(f, font=font_main, path=True, path_font=font_small)
        self.kb.grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=(0, 14))
        self.kb.insert(0, self.cfg.get("kb_dir", ""))
        CapsuleButton(f, text="浏览…", command=self.pick_kb, width=64, height=36,
                      font=font_small).grid(row=3, column=2, columnspan=2, pady=(0, 14))

        obs = detect.obsidian_info(self.cfg.get("obsidian_exe", ""))
        self.obsidian = obs
        kb_row = tk.Frame(f, bg=BG)
        kb_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        self.kb_switch = ToggleSwitch(kb_row,
                                      value=bool(self.cfg.get("kb_enabled", True)) and obs["installed"])
        self.kb_switch.set_enabled(obs["installed"])
        self.kb_switch.grid(row=0, column=0, sticky="w")
        tk.Label(kb_row, text="同时重建 Obsidian 知识库", font=font_main, bg=BG,
                 fg=TEXT).grid(row=0, column=1, sticky="w", padx=(10, 12))
        self.obs_state = tk.Label(kb_row, text="", font=font_small, bg=BG,
                                  fg=MUTED, anchor="w")
        self.obs_state.grid(row=0, column=2, sticky="ew")
        kb_row.columnconfigure(2, weight=1)
        self.refresh_obsidian()

        self.state = tk.Label(f, text="", font=font_small, bg=BG, fg=MUTED,
                              anchor="w", wraplength=620, justify="left")
        self.state.grid(row=5, column=0, columnspan=4, sticky="ew")
        self.done_btn = CapsuleButton(f, text="完成", command=self.commit, primary=True,
                                      height=40, font=(family, 10, "bold"))
        self.done_btn.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        root.bind("<Return>", lambda _e: self.commit())

        if self.cfg.get("project_dir"):
            self.after_project(quiet=True)
        self.refresh()
        self.root.after_idle(self.project.reveal_end)
        self.root.after_idle(self.kb.reveal_end)

    # ---------------------------------------------------------------- 动作
    def set_state(self, text, color=MUTED):
        self.state.configure(text=text, fg=color)

    def autodetect(self):
        cands = detect.candidate_project_dirs(self.project.get().strip())
        if not cands:
            self.set_state("没有自动找到项目目录，请手动选择含 extract_favorites.py 的目录", WARN)
            return
        self.project.delete(0, "end")
        self.project.insert(0, cands[0])
        self.project.reveal_end()
        self.after_project()

    def pick_project(self):
        d = filedialog.askdirectory(title="选择采集项目目录（需含 extract_favorites.py）")
        if d:
            self.project.delete(0, "end")
            self.project.insert(0, os.path.normpath(d))
            self.project.reveal_end()
            self.after_project()

    def pick_kb(self):
        d = filedialog.askdirectory(title="选择 Obsidian 知识库目录")
        if d:
            self.kb.delete(0, "end")
            self.kb.insert(0, os.path.normpath(d))
            self.kb.reveal_end()
            self.refresh()

    def after_project(self, quiet=False):
        project = self.project.get().strip()
        if not detect.is_project_dir(project):
            if not quiet:
                self.set_state("这个目录里没有 extract_favorites.py", ERR)
            return
        self.cfg["project_dir"] = project
        py = detect.resolve_python(project, self.cfg.get("python", ""))
        kb = detect.detect_kb_dir(project)
        if kb:
            self.kb.delete(0, "end")
            self.kb.insert(0, kb)
            self.kb.reveal_end()
        cookie = detect.read_project_settings(project)
        msg = f"已找到项目 · 解释器 {'就绪' if py else '缺失'}"
        msg += " · Cookie 已存在" if cookie.get("has_cookie") else " · Cookie 缺失，请先在项目里扫码登录"
        self.set_state(msg, CYAN if py and cookie.get("has_cookie") else WARN)
        self.refresh()

    def probe(self):
        if self.busy:
            return
        project = self.project.get().strip()
        py = detect.resolve_python(project, self.cfg.get("python", ""))
        if not detect.is_project_dir(project) or not py:
            self.set_state("先选对项目目录（需要 .venv 里的解释器）", ERR)
            return
        self.busy = True
        self.verify_btn.configure(state="disabled", text="校验中…")
        self.set_state("正在向抖音确认当前 Cookie 的账号身份…")

        def work():
            log = os.path.join(data_dir(), "_probe.log")
            r = pipeline.run_script(py, os.path.join(project, "probe_account.py"),
                                    [], project, log)
            info = pipeline.scan_stdout(r.get("lines") or [])
            self.root.after(0, lambda: self._probe_done(r, info))

        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, r, info):
        self.busy = False
        self.verify_btn.configure(state="normal", text="校验账号")
        acct = info.get("account") or {}
        if r["code"] == 0 and acct.get("sec_uid"):
            self.probed = acct
            self.account.set(acct.get("nickname") or acct["sec_uid"])
            self.set_state(f"校验通过：{acct.get('nickname')} · {acct['sec_uid'][:10]}…"
                           "（点「采用」写入设置）", CYAN)
            return
        tail = " / ".join((r.get("lines") or [])[-2:])
        self.set_state(f"校验失败：{tail or 'Cookie 可能已失效'}", ERR)

    def adopt(self):
        if not self.probed.get("sec_uid"):
            self.set_state("先点「校验账号」拿到当前账号，再点「采用」", WARN)
            return
        self.cfg["expect_sec_uid"] = self.probed["sec_uid"]
        self.cfg["expect_nickname"] = self.probed.get("nickname", "")
        self.account.set(self.probed.get("nickname") or self.probed["sec_uid"])
        self.set_state("已记录这个账号；以后采集到别的账号会自动中止，不重建交付物。", CYAN)
        self.refresh()

    def refresh_obsidian(self):
        ok = bool(self.obsidian.get("installed"))
        if not ok:
            self.kb_switch.set(False)
        self.kb_switch.set_enabled(ok)
        self.obs_state.configure(
            text=("已检测到 Obsidian" if ok else "未检测到 Obsidian；可先只用表格与批次交付"),
            fg=CYAN if ok else WARN)

    def refresh(self):
        project = self.project.get().strip()
        kb = self.kb.get().strip()
        cookie = detect.read_project_settings(project) if detect.is_project_dir(project) else {}
        kb_ok, kb_err = detect.kb_ready(kb)
        has_acct = bool(self.cfg.get("expect_sec_uid"))
        want_kb = self.kb_switch.get()
        ok = (detect.is_project_dir(project) and cookie.get("has_cookie") and has_acct
              and (kb_ok or not want_kb))
        self.done_btn.configure(state="normal" if ok else "disabled")
        if not kb_ok and kb:
            self.set_state(f"知识库：{kb_err}", WARN)

    def commit(self):
        project = self.project.get().strip()
        py = detect.resolve_python(project, self.cfg.get("python", ""))
        kb = self.kb.get().strip()
        cookie = detect.read_project_settings(project) if detect.is_project_dir(project) else {}
        want_kb = self.kb_switch.get()
        kb_ok, kb_err = detect.kb_ready(kb)
        problems = []
        if not detect.is_project_dir(project):
            problems.append("项目目录")
        if not py:
            problems.append("项目解释器")
        if not cookie.get("has_cookie"):
            problems.append("抖音 Cookie")
        if not self.cfg.get("expect_sec_uid"):
            problems.append("账号确认")
        if want_kb and not self.obsidian.get("installed"):
            problems.append("Obsidian（未检测到，无法启用知识库重建）")
        if want_kb and not kb_ok:
            problems.append("知识库（" + (kb_err or "未选择") + "）")
        if problems:
            self.set_state("还缺：" + "、".join(problems), ERR)
            return
        self.cfg.update(project_dir=project, python=py, kb_dir=kb,
                        kb_enabled=bool(want_kb),
                        obsidian_exe=self.obsidian.get("exe", "") or self.cfg.get("obsidian_exe", ""))
        config.save(self.cfg)
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass
        self.root.destroy()


def open(parent=None, on_done=None):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    fm, fs, family = fonts(root)
    Setup(root, fm, fs, family, on_done=on_done)
    if parent is None:
        root.mainloop()
    return root
