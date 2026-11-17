# -*- coding: utf-8 -*-
"""设置页：按「采集来源 / 知识库 / 高级」分区，一屏看清每个值是干什么的。"""
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import config
import detect
import mcp_config as mcpcfg
from common import APP_NAME, VERSION, DeferredCall
from ui_kit import (
    ACCENT, BG, BORDER, CARD, CARD_LINE, CYAN, ERR, MUTED, PANEL, SURFACE, TEXT, WARN,
    CapsuleButton, CheckBox, RoundedEntry, Tooltip, apply_icon, apply_theme,
    center, fonts,
)


def _card(parent, title, title_font, sub_font, subtitle=""):
    outer = tk.Frame(parent, bg=CARD, highlightbackground=CARD_LINE,
                     highlightthickness=1)
    inner = tk.Frame(outer, bg=CARD, padx=18, pady=14)
    inner.pack(fill="both", expand=True)
    head = tk.Frame(inner, bg=CARD)
    head.pack(fill="x", pady=(0, 12))
    tk.Label(head, text=title, font=title_font,
             bg=CARD, fg=TEXT, anchor="w").pack(side="left")
    if subtitle:
        tk.Label(head, text=subtitle, font=sub_font,
                 bg=CARD, fg=MUTED, anchor="w").pack(side="left", padx=(10, 0))
    body = tk.Frame(inner, bg=CARD)
    body.pack(fill="both", expand=True)
    return outer, body


class Settings:
    def __init__(self, root, font_main, font_small, family, on_done=None):
        self.root = root
        self.on_done = on_done
        self.font_main, self.font_small = font_main, font_small
        self.cfg = config.load()
        self.full_state = ""
        self.busy = False
        self._scan_q = queue.Queue()
        self.mcp_open = False
        # 库现状要 os.walk 全库并解析两份 JSON，别在 UI 线程里做（F-9）。
        self._status_call = DeferredCall(root, engine_status, self._on_status)

        root.title(f"设置 · {APP_NAME} {VERSION}")
        root.resizable(True, True)
        root.configure(bg=BG)
        apply_icon(root)
        apply_theme(root)
        center(root, 880, 790)

        f = tk.Frame(root, bg=BG, padx=24, pady=18)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)

        tk.Label(f, text="设置", font=(family, 16, "bold"), bg=BG, fg=TEXT,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 14))

        # ---- 采集来源
        src_card, src = _card(f, "采集来源", (family, 11, "bold"), self.font_small)
        src_card.grid(row=2, column=0, sticky="ew")
        src.columnconfigure(1, weight=1)

        self._label(src, 0, "项目目录")
        self.project = self._entry(src, 0)
        Tooltip(self.project.entry, self.project.get, font=self.font_small)
        self._btn(src, 0, "自动发现", self.autodetect, width=84, col=2)
        self._btn(src, 0, "浏览…", self.pick_project, width=72, col=3, padx=(8, 0))
        self._hint(src, 1, "需包含 extract_favorites.py 与 .venv")

        self._label(src, 2, "抖音账号")
        self.account = self._entry(src, 2)
        self._btn(src, 2, "查看完整", self.show_account, width=84, col=2)
        self._btn(src, 2, "重新校验", self.reverify, width=84, col=3, padx=(8, 0))
        self._hint(src, 3, "采集后核对 sec_uid；不一致会中止，不重建知识库")

        self._label(src, 4, "条数下限")
        count_row = tk.Frame(src, bg=CARD)
        count_row.grid(row=4, column=1, sticky="w", padx=(14, 8), pady=(0, 2))
        self.min_count = RoundedEntry(count_row, font=self.font_main, width=8,
                                      pxwidth=140, panel_bg=CARD)
        self.min_count.pack(side="left")
        self.min_count.insert(0, str(self.cfg.get("min_count", 0)))
        tk.Label(count_row, text="条", font=self.font_main, bg=CARD, fg=MUTED).pack(
            side="left", padx=(8, 0))
        self._hint(src, 5, "低于此数视为账号异常并中止")

        # ---- 知识库
        kb_card, kb = _card(f, "知识库", (family, 11, "bold"), self.font_small, "可选")
        kb_card.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        kb.columnconfigure(1, weight=1)

        sw_row = tk.Frame(kb, bg=CARD)
        sw_row.grid(row=0, column=0, columnspan=4, sticky="ew")
        self.kb_switch = CheckBox(
            sw_row, value=bool(self.cfg.get("kb_enabled", True)),
            command=lambda _v: self.refresh_state(), bg=CARD)
        self.kb_switch.grid(row=0, column=0)
        kb_label = tk.Label(sw_row, text="同步重建 Obsidian 知识库", font=font_main,
                            bg=CARD, fg=TEXT, cursor="hand2")
        kb_label.grid(row=0, column=1, sticky="w", padx=(8, 12))
        kb_label.bind("<Button-1>", lambda _e: self.kb_switch._toggle())
        self.obs_state = tk.Label(sw_row, text="", font=self.font_small, bg=CARD,
                                  fg=MUTED, anchor="e")
        self.obs_state.grid(row=0, column=2, sticky="e")
        sw_row.columnconfigure(2, weight=1)

        self._label(kb, 1, "库目录")
        self.kb = self._entry(kb, 1)
        Tooltip(self.kb.entry, self.kb.get, font=self.font_small)
        self._btn(kb, 1, "浏览…", self.pick_kb, width=72, col=2)
        self._btn(kb, 1, "打开", self.open_kb, width=64, col=3, padx=(8, 0))

        self.kb_stats = tk.Label(kb, text="", font=self.font_small, bg=CARD, fg=MUTED,
                                 anchor="w")
        self.kb_stats.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # ---- 高级（MCP）
        adv_card, adv = _card(f, "高级", (family, 11, "bold"), self.font_small)
        adv_card.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        adv.columnconfigure(0, weight=1)
        head = tk.Frame(adv, bg=CARD)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="MCP 接入", font=font_main,
                 bg=CARD, fg=TEXT).grid(row=0, column=0, sticky="w")
        self.mcp_toggle = CapsuleButton(head, text="展开", command=self.toggle_mcp,
                                        width=64, height=28, font=self.font_small)
        self.mcp_toggle.grid(row=0, column=1, sticky="e")

        self.mcp_body = tk.Frame(adv, bg=CARD)
        self.mcp_body.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.mcp_body.columnconfigure(0, weight=1)
        tk.Label(self.mcp_body, text=mcpcfg.mcp_json_path(), font=self.font_small,
                 bg=CARD, fg=MUTED, anchor="w").grid(row=0, column=0, sticky="ew")
        self.preview = tk.Text(self.mcp_body, height=6, font=("Consolas", 9),
                               bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                               relief="flat", wrap="none", padx=8, pady=6)
        self.preview.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        self.preview.insert("1.0", mcpcfg.fragment_text())
        self.preview.configure(state="disabled")
        row = tk.Frame(self.mcp_body, bg=CARD)
        row.grid(row=2, column=0, sticky="w")
        for i, (label, cmd) in enumerate((("复制配置", self.copy_cfg),
                                          ("写入配置", self.write_cfg),
                                          ("测试连接", self.test_cfg))):
            CapsuleButton(row, text=label, command=cmd, width=88, height=30,
                          font=self.font_small).grid(row=0, column=i, padx=(0, 8))
        self.mcp_body.grid_remove()

        # ---- 状态 + 底部
        self.state = tk.Label(f, text="", font=self.font_small, bg=BG, fg=MUTED,
                              anchor="w", wraplength=820, justify="left", takefocus=1)
        self.state.grid(row=5, column=0, sticky="sw", pady=(12, 0))
        Tooltip(self.state, lambda: self.full_state, font=self.font_small)

        foot = tk.Frame(f, bg=BG)
        foot.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        foot.columnconfigure(0, weight=1)
        CapsuleButton(foot, text="保存", command=self.save, primary=True, width=120,
                      height=40, font=(family, 10, "bold")).grid(row=0, column=1, padx=(0, 10))
        CapsuleButton(foot, text="关闭", command=self.close, width=88,
                      height=40, font=self.font_small).grid(row=0, column=2)

        self.project.insert(0, self.cfg.get("project_dir", ""))
        self.kb.insert(0, self.cfg.get("kb_dir", "") or
                       detect.detect_kb_dir(self.cfg.get("project_dir", "")))
        acct = self.cfg.get("expect_nickname") or ""
        sec = detect.mask_sec_uid(self.cfg.get("expect_sec_uid", ""))
        self.account.insert(0, f"{acct}  {sec}".strip())
        self.account.entry.configure(state="readonly")

        self.root.bind("<Escape>", lambda _e: self.close())
        self.root.bind("<Destroy>", self._cancel_poll)
        self.refresh_obsidian()
        self.refresh_state()
        self._poll_job = self.root.after(120, self._poll_scan)

    # ---------------------------------------------------------------- 组件
    def _label(self, parent, row, text):
        tk.Label(parent, text=text, font=self.font_main, bg=CARD, fg=MUTED,
                 anchor="w", width=10).grid(row=row, column=0, sticky="w", pady=(0, 2))

    def _entry(self, parent, row, path=False, width=24, pxwidth=240):
        e = RoundedEntry(parent, font=self.font_main, width=width, pxwidth=pxwidth,
                         path=path, path_font=self.font_small, panel_bg=CARD)
        e.grid(row=row, column=1, sticky="ew", padx=(14, 8), pady=(0, 2))
        return e

    def _btn(self, parent, row, text, cmd, width=72, col=2, padx=(0, 0)):
        btn = CapsuleButton(parent, text=text, command=cmd, width=width, height=34,
                            font=self.font_small)
        btn.grid(row=row, column=col, padx=padx, pady=(0, 2))
        return btn

    def _hint(self, parent, row, text):
        tk.Label(parent, text=text, font=self.font_small, bg=CARD, fg=MUTED,
                 anchor="w", justify="left").grid(row=row, column=1, columnspan=3,
                                                   sticky="w", padx=(14, 0),
                                                   pady=(0, 12))

    # ---------------------------------------------------------------- 状态
    def set_state(self, text, color=MUTED):
        self.full_state = text
        self.state.configure(text=text if len(text) <= 104 else text[:101] + "…", fg=color)

    def obsidian_installed(self):
        return bool(detect.find_obsidian(self.cfg.get("obsidian_exe", "")))

    def refresh_obsidian(self):
        exe = detect.find_obsidian(self.cfg.get("obsidian_exe", ""))
        if not exe:
            self.kb_switch.set(False)
            self.kb_switch.set_enabled(False)
            self.obs_state.configure(text="未检测到 Obsidian", fg=WARN)
            return
        self.kb_switch.set_enabled(True)
        n = len(detect.obsidian_vaults())
        self.obs_state.configure(text=f"Obsidian 已安装 · 库 {n} 个", fg=CYAN)

    def refresh_state(self):
        project = self.project.get().strip()
        kb = self.kb.get().strip()
        cookie = detect.read_project_settings(project) if detect.is_project_dir(project) else {}
        py = detect.resolve_python(project, self.cfg.get("python", ""))
        kb_ok, kb_err = detect.kb_ready(kb)
        kb_on = self.kb_switch.get()
        bits = ["项目就绪" if detect.is_project_dir(project) else "项目缺失",
                "解释器就绪" if py else "解释器缺失",
                "Cookie 已存在" if cookie.get("has_cookie") else "Cookie 缺失"]
        if kb_on:
            bits.append("知识库就绪" if kb_ok else f"知识库缺失（{kb_err}）")
        else:
            bits.append("知识库未启用")
        ok = all(("缺失" not in b and "未启用" not in b) for b in bits)
        self.set_state(" · ".join(bits), CYAN if ok else WARN)

        self._status_call.run()

    def _on_status(self, result):
        """库现状统计在后台算完，回主线程再写标签。"""
        if not isinstance(result, dict):
            return
        stats = result.get("kb_stats") or {}
        try:
            if stats:
                self.kb_stats.configure(
                    text=f"库现状：{stats.get('total', 0):,} 收藏 · {stats.get('ai', 0):,} AI 笔记 · "
                         f"{stats.get('concepts', 0):,} 概念 · {stats.get('pairs', 0):,} 共现")
            else:
                self.kb_stats.configure(text="库现状：尚未生成（同步一次后出现）")
        except tk.TclError:
            pass

    def show_account(self):
        nick = self.cfg.get("expect_nickname") or "未设置"
        sec = self.cfg.get("expect_sec_uid") or "（未设置，点「重新校验」走一遍初始化）"
        messagebox.showinfo(
            "当前账号",
            f"昵称：{nick}\n\n唯一标识（sec_uid）\n{sec}\n\n"
            f"采集后会用这个标识核对；不一致会中止，不重建知识库。",
            parent=self.root)

    # ---------------------------------------------------------------- 动作
    def toggle_mcp(self):
        self.mcp_open = not self.mcp_open
        if self.mcp_open:
            self.mcp_body.grid()
            self.mcp_toggle.configure(text="收起")
        else:
            self.mcp_body.grid_remove()
            self.mcp_toggle.configure(text="展开")
        self.root.update_idletasks()
        h = 790 + (230 if self.mcp_open else 0)
        w = max(880, int(self.root.winfo_width() or 880))
        self.root.geometry(f"{w}x{h}")

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
            self._scan_q.put(("scan", detect.candidate_project_dirs(
                self.project.get().strip(), deep=True)))

        threading.Thread(target=work, daemon=True).start()

    def _cancel_poll(self, _e=None):
        # 子控件销毁也会经 bindtags 冒到 toplevel，别因此提前停掉后台调用。
        if _e is not None and getattr(_e, "widget", None) is not self.root:
            return
        self._status_call.destroy()
        try:
            if getattr(self, "_poll_job", None):
                self.root.after_cancel(self._poll_job)
        except (tk.TclError, ValueError):
            pass
        self._poll_job = None

    def _poll_scan(self):
        try:
            while True:
                kind, payload = self._scan_q.get_nowait()
                if kind == "scan":
                    self._scan_done(payload)
                elif kind == "test":
                    self._test_done(payload)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            self._poll_job = self.root.after(120, self._poll_scan)
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

    def pick_project(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择抖音采集项目目录（含 extract_favorites.py）")
        if d:
            self._apply_project(d)

    def pick_kb(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择 Obsidian 知识库目录")
        if d:
            self.kb.delete(0, "end")
            self.kb.insert(0, os.path.normpath(d))
            self.kb.reveal_end()
            self.refresh_state()

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

    def reverify(self):
        import setup_env
        setup_env.open(self.root, on_done=self.reload)

    def _dirty(self):
        try:
            mn = int(self.min_count.get().strip() or 0)
        except ValueError:
            return True
        return (self.project.get().strip() != (self.cfg.get("project_dir") or "")
                or self.kb.get().strip() != (self.cfg.get("kb_dir") or "")
                or mn != int(self.cfg.get("min_count") or 0)
                or bool(self.kb_switch.get()) != bool(self.cfg.get("kb_enabled", True)))

    def close(self):
        if self._dirty() and not messagebox.askyesno(
                APP_NAME, "有未保存的更改，确定关闭？", parent=self.root):
            return
        self.root.destroy()

    def reload(self):
        self.cfg = config.load()
        self.refresh_obsidian()
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
        if want_kb and not self.obsidian_installed():
            self.set_state("未检测到 Obsidian，无法启用知识库重建", ERR)
            return
        if want_kb:
            kb_ok, kb_err = detect.kb_ready(kb)
            if not kb_ok:
                self.set_state(f"知识库不可用：{kb_err}", ERR)
                return
        self.cfg.update(project_dir=project, python=py, kb_dir=kb,
                        min_count=max(0, mn), kb_enabled=bool(want_kb),
                        obsidian_exe=detect.find_obsidian(self.cfg.get("obsidian_exe", "")))
        config.save(self.cfg)
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
            self.set_state("配置片段已复制；合并后在连接器管理里点「信任」才生效", CYAN)
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
        self.set_state(f"{r['action']} douyin-fav-sync 成功{tail}；需在连接器管理里点「信任」", CYAN)

    def test_cfg(self):
        if self.busy:
            return
        self.busy = True
        self.set_state("正在握手…")

        def work():
            r = mcpcfg.test_connection()
            self._scan_q.put(("test", r))

        threading.Thread(target=work, daemon=True).start()

    def _test_done(self, r):
        self.busy = False
        if r.get("ok"):
            self.set_state(
                f"握手通过 · 协议 {r.get('protocol')} · 工具 {len(r.get('tools') or [])} 个 · "
                f"ready={r.get('ready')} · {r.get('elapsed_ms')} ms", CYAN)
        else:
            self.set_state(f"握手失败：{r.get('error') or r.get('message') or '未知原因'}", ERR)


def engine_status():
    import engine
    return engine.safe_call(engine.status)


def open(parent=None, on_done=None):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    fm, fs, family = fonts(root)
    Settings(root, fm, fs, family, on_done=on_done)
    if parent is None:
        root.mainloop()
    return root
