# -*- coding: utf-8 -*-
"""设置页：路径、账号、MCP 接入与环境状态。

写入 MCP 配置只增改 douyin-fav-sync 一个键；写前备份、原子替换、解析失败不写。
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config
import detect
import mcp_config as mcpcfg
from common import APP_NAME, VERSION
from ui_kit import (
    BG, BORDER, CYAN, ERR, MUTED, PANEL, SURFACE, TEXT, WARN,
    CapsuleButton, RoundedEntry, ToggleSwitch, Tooltip, apply_icon, apply_theme,
    center, fonts,
)


class Settings:
    def __init__(self, root, font_main, font_small, family, on_done=None):
        self.root = root
        self.on_done = on_done
        self.font_main, self.font_small = font_main, font_small
        self.cfg = config.load()
        self.full_state = ""
        self.busy = False
        self._scan_q = queue.Queue()

        root.title(f"设置 · {APP_NAME} {VERSION}")
        root.resizable(True, True)
        root.configure(bg=BG)
        apply_icon(root)
        apply_theme(root)
        center(root, 780, 640)

        f = tk.Frame(root, bg=BG, padx=20, pady=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        self.project = self._row(f, 0, "项目目录", path=True)
        self._btn(f, 0, "自动发现", self.autodetect, width=78, col=2)
        self._btn(f, 0, "浏览…", self.pick_project, width=64, padx=(6, 0), col=3)

        self.kb = self._row(f, 1, "知识库", path=True)
        self._btn(f, 1, "浏览…", self.pick_kb, width=64, padx=(6, 0))

        self.account = self._row(f, 2, "账号")
        self._btn(f, 2, "查看完整", self.show_account, width=84)

        self.min_count = self._row(f, 3, "条数下限")
        self.min_count.insert(0, str(self.cfg.get("min_count", 0)))

        # Obsidian 对接：开关 + 状态 + 打开
        obs = detect.obsidian_info(self.cfg.get("obsidian_exe", ""))
        self.obsidian = obs
        kb_row = tk.Frame(f, bg=BG)
        kb_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(2, 6))
        kb_row.columnconfigure(1, weight=1)
        self.kb_switch = ToggleSwitch(
            kb_row, value=bool(self.cfg.get("kb_enabled", True)) and obs["installed"],
            command=lambda _v: self.refresh_obsidian())
        self.kb_switch.set_enabled(obs["installed"])
        self.kb_switch.grid(row=0, column=0, sticky="w")
        tk.Label(kb_row, text="整理后重建 Obsidian 知识库", font=self.font_main,
                 bg=BG, fg=TEXT).grid(row=0, column=1, sticky="w", padx=(10, 12))
        CapsuleButton(kb_row, text="打开知识库", command=self.open_kb, width=96,
                      height=30, font=self.font_small).grid(row=0, column=2, padx=(8, 0))
        self.obs_state = tk.Label(kb_row, text="", font=self.font_small, bg=BG,
                                  fg=MUTED, anchor="w", justify="left", wraplength=720)
        self.obs_state.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        tk.Label(f, text="MCP 配置", font=self.font_main, bg=BG, fg=MUTED).grid(
            row=5, column=0, sticky="nw", pady=(10, 6))
        box = tk.Frame(f, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.grid(row=5, column=1, columnspan=3, sticky="ew", pady=(10, 6))
        box.columnconfigure(0, weight=1)
        self.mcp_path = tk.Label(box, text=mcpcfg.mcp_json_path(), font=self.font_small,
                                 bg=PANEL, fg=MUTED, anchor="w")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.mcp_path.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))
        self.preview = tk.Text(box, height=7, font=("Consolas", 9), bg=SURFACE, fg=TEXT,
                               insertbackground=TEXT, relief="flat", wrap="none",
                               padx=8, pady=6)
        ysb = ttk.Scrollbar(box, orient="vertical", command=self.preview.yview)
        xsb = ttk.Scrollbar(box, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 0))
        ysb.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 0))
        xsb.grid(row=2, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.preview.insert("1.0", mcpcfg.fragment_text())
        self.preview.configure(state="disabled")

        row = tk.Frame(f, bg=BG)
        row.grid(row=6, column=0, columnspan=4, sticky="ew")
        for i, (label, cmd) in enumerate((("复制配置", self.copy_cfg),
                                          ("写入配置", self.write_cfg),
                                          ("测试连接", self.test_cfg))):
            CapsuleButton(row, text=label, command=cmd, width=88, height=30,
                          font=self.font_small).grid(row=0, column=i, padx=(0, 8))

        self.state = tk.Label(f, text="", font=self.font_small, bg=BG, fg=MUTED,
                              anchor="w", wraplength=700, justify="left", takefocus=1)
        self.state.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        Tooltip(self.state, lambda: self.full_state, font=self.font_small)

        foot = tk.Frame(f, bg=BG)
        foot.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        foot.columnconfigure(0, weight=1)
        CapsuleButton(foot, text="保存", command=self.save, primary=True, width=120,
                      height=38, font=(family, 10, "bold")).grid(row=0, column=1, padx=(0, 8))
        CapsuleButton(foot, text="关闭", command=self.close, width=88,
                      height=38, font=self.font_small).grid(row=0, column=2)

        self.project.insert(0, self.cfg.get("project_dir", ""))
        self.kb.insert(0, self.cfg.get("kb_dir", "") or detect.detect_kb_dir(self.cfg.get("project_dir", "")))
        acct = self.cfg.get("expect_nickname") or ""
        sec = detect.mask_sec_uid(self.cfg.get("expect_sec_uid", ""))
        self.account.insert(0, f"{acct}  {sec}".strip())
        self.account.entry.configure(state="readonly")   # 先写值再置只读，否则写不进去
        self._saved = self._snapshot()
        self.root.bind("<Escape>", lambda _e: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_obsidian()
        self.refresh_state()
        self.root.after(120, self._poll_scan)
        self.root.after_idle(self.project.reveal_end)
        self.root.after_idle(self.kb.reveal_end)

    # ---------------------------------------------------------------- 布局
    def _row(self, parent, row, label, path=False):
        tk.Label(parent, text=label, font=self.font_main, bg=BG, fg=MUTED).grid(
            row=row, column=0, sticky="w", pady=(0, 10))
        e = RoundedEntry(parent, font=self.font_main, path=path, path_font=self.font_small)
        e.grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=(0, 10))
        return e

    def _btn(self, parent, row, text, cmd, width=64, padx=(6, 0), col=2):
        btn = CapsuleButton(parent, text=text, command=cmd, width=width, height=36,
                            font=self.font_small)
        btn.grid(row=row, column=col, padx=padx, pady=(0, 10))
        return btn

    # ---------------------------------------------------------------- 状态
    def set_state(self, text, color=MUTED):
        self.full_state = text
        self.state.configure(text=text if len(text) <= 96 else text[:93] + "…", fg=color)

    def refresh_obsidian(self):
        self.obsidian = detect.obsidian_info(self.cfg.get("obsidian_exe", ""))
        ok = bool(self.obsidian.get("installed"))
        if not ok:
            self.kb_switch.set(False)
        self.kb_switch.set_enabled(ok)
        if ok:
            n = len(self.obsidian.get("vaults") or [])
            text = f"已检测到 Obsidian · 库 {n} 个"
            try:
                import engine
                st = engine.safe_call(engine.status)
                k = st.get("kb_stats") or {}
                if k:
                    text += (f" · 现状 {k['total']} 收藏 / AI {k['ai']} / "
                             f"{k['concepts']} 概念 / {k['pairs']} 共现")
            except Exception:
                pass
            self.obs_state.configure(text=text, fg=CYAN)
        else:
            self.obs_state.configure(text="未检测到 Obsidian：装好后重开设置即可启用", fg=WARN)

    def open_kb(self):
        kb = self.kb.get().strip()
        if not kb or not os.path.isdir(kb):
            self.set_state("知识库目录不可用", ERR)
            return
        if not detect.open_in_obsidian(kb):
            try:
                os.startfile(kb)
            except OSError:
                self.set_state("无法打开知识库", ERR)

    def refresh_state(self):
        st = detect.read_project_settings(self.project.get().strip()) if detect.is_project_dir(
            self.project.get().strip()) else {}
        py = detect.resolve_python(self.project.get().strip(), self.cfg.get("python", ""))
        kb_ok, kb_err = detect.kb_ready(self.kb.get().strip())
        kb_on = self.kb_switch.get()
        bits = []
        bits.append("项目就绪" if detect.is_project_dir(self.project.get().strip()) else "项目缺失")
        bits.append("解释器就绪" if py else "解释器缺失")
        bits.append("Cookie 已存在" if st.get("has_cookie") else "Cookie 缺失")
        if not kb_on:
            bits.append("知识库未启用")
        else:
            bits.append("知识库就绪" if kb_ok else f"知识库缺失（{kb_err}）")
        self.set_state(" · ".join(bits), CYAN if all(("缺失" not in b) for b in bits) else WARN)

    def _snapshot(self):
        return (self.project.get().strip(), self.kb.get().strip(),
                self.min_count.get().strip())

    def close(self):
        if self._snapshot() != getattr(self, "_saved", self._snapshot()):
            if not messagebox.askyesno(APP_NAME, "有未保存的更改，确定放弃并关闭？",
                                       parent=self.root):
                return
        self.root.destroy()

    def show_account(self):
        nick = self.cfg.get("expect_nickname", "") or "未设置"
        sec = self.cfg.get("expect_sec_uid", "") or "（未设置，请回到「初始化本机环境」校验并采用）"
        messagebox.showinfo("账号标识", f"{nick}\n{sec}", parent=self.root)

    # ---------------------------------------------------------------- 动作
    def autodetect(self):
        if self.busy:
            return
        cands = detect.candidate_project_dirs(self.project.get().strip())
        if cands:
            self._apply_project(cands[0])
            return
        self.busy = True
        self.set_state("正在常见位置查找 TikTokDownloader（最多几秒）…")

        def work():
            self._scan_q.put(detect.candidate_project_dirs(
                self.project.get().strip(), deep=True))

        threading.Thread(target=work, daemon=True).start()

    def _poll_scan(self):
        try:
            while True:
                self._scan_done(self._scan_q.get_nowait())
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            self.root.after(120, self._poll_scan)
        except tk.TclError:
            pass

    def _scan_done(self, hits):
        self.busy = False
        if not hits:
            self.set_state("没找到 TikTokDownloader；请用「浏览…」指定", WARN)
            return
        self._apply_project(hits[0])

    def _apply_project(self, path):
        self.project.delete(0, "end")
        self.project.insert(0, os.path.normpath(path))
        self.project.reveal_end()
        kb = detect.detect_kb_dir(path)
        if kb:
            self.kb.delete(0, "end")
            self.kb.insert(0, kb)
            self.kb.reveal_end()
        self.refresh_state()
        self.refresh_state()

    def pick_project(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择采集项目目录（需含 extract_favorites.py）")
        if d:
            self.project.delete(0, "end")
            self.project.insert(0, os.path.normpath(d))
            self.project.reveal_end()
            self.refresh_state()

    def pick_kb(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择 Obsidian 知识库目录")
        if d:
            self.kb.delete(0, "end")
            self.kb.insert(0, os.path.normpath(d))
            self.kb.reveal_end()
            self.refresh_state()

    def save(self):
        project = self.project.get().strip()
        kb = self.kb.get().strip()
        try:
            mn = int(self.min_count.get().strip() or 0)
        except ValueError:
            self.set_state("条数下限必须是整数", ERR)
            return
        if not detect.is_project_dir(project):
            self.set_state("项目目录里没有 extract_favorites.py", ERR)
            return
        py = detect.resolve_python(project, self.cfg.get("python", ""))
        if not py:
            self.set_state("项目里没有 .venv 解释器", ERR)
            return
        want_kb = self.kb_switch.get()
        if want_kb and not self.obsidian.get("installed"):
            self.set_state("未检测到 Obsidian，无法启用知识库重建", ERR)
            return
        if want_kb:
            kb_ok, kb_err = detect.kb_ready(kb)
            if not kb_ok:
                self.set_state(f"知识库不可用：{kb_err}", ERR)
                return
        self.cfg.update(project_dir=project, python=py, kb_dir=kb,
                        min_count=max(0, mn), kb_enabled=bool(want_kb),
                        obsidian_exe=self.obsidian.get("exe", "") or self.cfg.get("obsidian_exe", ""))
        config.save(self.cfg)
        self._saved = self._snapshot()
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass
        self.set_state("已保存", CYAN)
        self.refresh_state()

    def copy_cfg(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(mcpcfg.fragment_text())
            self.set_state("配置片段已复制；合并进 mcp.json 后需要在连接器管理里点「信任」才生效", CYAN)
        except tk.TclError as e:
            self.set_state(f"复制失败：{e}", ERR)

    def write_cfg(self):
        if self.busy:
            return
        r = mcpcfg.merge_into()
        if not r.get("ok"):
            self.set_state(r.get("error", "写入失败"), ERR)
            return
        tail = f"（保留其他 {r['preserved_count']} 个连接器）" if r.get("preserved_count") else ""
        self.set_state(f"{r['action']} douyin-fav-sync 成功{tail}；写入后需在连接器管理里点「信任」", CYAN)

    def test_cfg(self):
        if self.busy:
            return
        self.busy = True
        self.set_state("正在握手…")

        def work():
            r = mcpcfg.test_connection()
            self.root.after(0, lambda: self._test_done(r))

        threading.Thread(target=work, daemon=True).start()

    def _test_done(self, r):
        self.busy = False
        if r.get("ok"):
            self.set_state(
                f"握手通过 · 协议 {r.get('protocol')} · 工具 {len(r.get('tools') or [])} 个 · "
                f"ready={r.get('ready')} · {r.get('elapsed_ms')} ms", CYAN)
        else:
            self.set_state(f"握手失败：{r.get('error') or r.get('message') or '未知原因'}", ERR)


def open(parent=None, on_done=None):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    fm, fs, family = fonts(root)
    Settings(root, fm, fs, family, on_done=on_done)
    if parent is None:
        root.mainloop()
    return root
