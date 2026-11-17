# -*- coding: utf-8 -*-
"""安装器：装到 %LOCALAPPDATA%\\抖音收藏整理，创建快捷方式与卸载项。

- 不需要管理员权限。
- 不碰任何交付目录与抖音项目数据。
- 卸载只删本安装器写入的文件与快捷方式，不递归删目录、不动导出结果。
"""
import base64
import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

from common import APP_NAME, EXE_NAME, VERSION, app_dir, is_frozen
from ui_kit import (
    BG, CYAN, ERR, MUTED,
    CapsuleButton, RoundedEntry, Tooltip, apply_icon, apply_theme, center, fonts,
)

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DouyinFavSync"


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, APP_NAME)


def _ps(script):
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
            capture_output=True, timeout=45)
        return r.returncode, r.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def desktop_dir():
    rc, out = _ps("[Environment]::GetFolderPath('Desktop')")
    return out if rc == 0 and out and os.path.isdir(out) else os.path.join(
        os.path.expanduser("~"), "Desktop")


def start_menu_dir():
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "Microsoft", "Windows", "Start Menu", "Programs")


def make_shortcut(lnk, target, workdir):
    s = ("$shell = New-Object -ComObject WScript.Shell\n"
         f"$lnk = $shell.CreateShortcut('{lnk}')\n"
         f"$lnk.TargetPath = '{target}'\n"
         f"$lnk.WorkingDirectory = '{workdir}'\n"
         f"$lnk.Description = '{APP_NAME}'\n"
         "$lnk.Save()\n")
    return _ps(s)[0] == 0


def write_uninstall_item(exe):
    try:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "douyin-fav-sync")
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, os.path.dirname(exe))
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{exe}" --uninstall')
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        return True
    except OSError:
        return False


def install(dest, no_shortcut=False, progress=None):
    def say(m):
        if progress:
            progress(m)

    dest = os.path.abspath(dest)
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        return False, f"无法创建目录：{e}", dest

    exe = os.path.join(dest, EXE_NAME)
    say("正在复制程序…")
    if is_frozen():
        try:
            if os.path.abspath(sys.executable) != os.path.abspath(exe):
                shutil.copy2(sys.executable, exe)
        except OSError as e:
            return False, f"复制程序失败：{e}", dest
    else:
        with open(os.path.join(dest, "源码运行.txt"), "w", encoding="utf-8") as f:
            f.write("源码态验证：未生成 exe；正式安装包由 build.py 构建。\n")

    import mcp_config
    entry = dict(mcp_config.server_entry())
    entry["command"] = exe
    with open(os.path.join(dest, "mcp配置.json"), "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"douyin-fav-sync": entry}}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(dest, "版本.txt"), "w", encoding="utf-8") as f:
        f.write(f"{APP_NAME} V{VERSION}\n安装时间 {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    with open(os.path.join(dest, "说明.md"), "w", encoding="utf-8") as f:
        f.write(
            f"# {APP_NAME} V{VERSION}\n\n"
            "首次运行点主按钮「初始化本机环境」：选项目目录 → 校验抖音账号并采用 → 确认知识库目录"
            "（没装 Obsidian 可关掉知识库重建）。\n\n"
            "完成后先点右上角「⚠️ 全仓同步」跑一次全量采集（约 25 分钟）。\n"
            "之后选导出目录与作品发布日期（留空表示全部），点日期右侧的「仅导出」即可用现有数据出批次，"
            "不采集、不联网。\n\n"
            "每轮新建带时间戳的批次目录，绝不覆盖已有文件；计数、子类别分布、待加工、明细与入库结果"
            "都在批次里的《导出报告.md》。\n\n"
            "MCP：把 mcp配置.json 里 douyin-fav-sync 这一个键合并进 `~/.workbuddy/mcp.json` 已有的 "
            "mcpServers（不要整份覆盖），保存后到连接器管理页点「信任」；接入后调用 dy_status 验证。\n")

    if not no_shortcut:
        say("正在创建快捷方式…")
        try:
            d = desktop_dir()
            os.makedirs(d, exist_ok=True)
            make_shortcut(os.path.join(d, f"{APP_NAME}.lnk"), exe, dest)
            d2 = start_menu_dir()
            os.makedirs(d2, exist_ok=True)
            make_shortcut(os.path.join(d2, f"{APP_NAME}.lnk"), exe, dest)
        except OSError:
            pass
        write_uninstall_item(exe)

    say("已安装")
    return True, "已安装", dest


def uninstall(notify=True):
    for d in (desktop_dir(), start_menu_dir()):
        p = os.path.join(d, f"{APP_NAME}.lnk")
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass

    d = app_dir()
    for name in ("mcp配置.json", "版本.txt", "说明.md", "源码运行.txt",
                 "prefs.json", "settings.json"):
        p = os.path.join(d, name)
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
    exe_left = False
    p = os.path.join(d, EXE_NAME)
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        exe_left = True
    try:
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    except OSError:
        pass

    msg = "已卸载，交付目录与知识库未删除"
    if exe_left:
        msg += f"；程序正在运行无法自删，退出后可手动删除 {d}"
    if notify:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, f"卸载 {APP_NAME}", 0x40)
        except Exception:
            pass
    return True, msg


class SetupUI:
    def __init__(self, root, font_main, font_small, family, preset=None, no_shortcut=False):
        self.root = root
        self.no_shortcut = no_shortcut
        self.busy = False
        self.full_state = ""
        self._q = queue.Queue()
        self._poll_job = None
        root.title(f"安装 {APP_NAME} V{VERSION}")
        root.resizable(False, False)
        root.configure(bg=BG)
        apply_icon(root)
        apply_theme(root)
        center(root, 600, 210)

        f = tk.Frame(root, bg=BG, padx=20, pady=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        tk.Label(f, text="安装位置", font=font_main, bg=BG, fg=MUTED).grid(
            row=0, column=0, sticky="w", pady=(2, 14))
        self.dest = RoundedEntry(f, font=font_main, path=True, path_font=font_small)
        self.dest.grid(row=0, column=1, sticky="ew", padx=12, pady=(2, 14))
        self.dest.insert(0, preset or default_dir())
        self.dest.bind("<Return>", self._on_return)
        CapsuleButton(f, text="浏览…", command=self.pick, width=84, height=36,
                      font=font_small).grid(row=0, column=2, pady=(2, 14))

        self.btn = CapsuleButton(f, text="安装", command=self.go, primary=True,
                                 height=42, font=(family, 10, "bold"))
        self.btn.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.state = tk.Label(f, text="", font=font_small, bg=BG, fg=MUTED,
                              anchor="w", wraplength=470, justify="left")
        self.state.grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 0))
        Tooltip(self.state, lambda: self.full_state, font=font_small)
        root.bind("<Return>", lambda _e: self.go())
        root.after_idle(self.dest.reveal_end)
        root.bind("<Destroy>", self._cancel_poll)
        self._poll_job = root.after(120, self._poll)

    def _on_return(self, _event=None):
        self.go()
        return "break"

    def set_state(self, text, color=MUTED):
        self.full_state = text
        self.state.configure(text=text if len(text) <= 76 else text[:73] + "…",
                             fg=color)

    def pick(self):
        d = filedialog.askdirectory(title="选择安装位置")
        if d:
            self.dest.delete(0, "end")
            self.dest.insert(0, os.path.normpath(d))
            self.dest.reveal_end()

    def go(self):
        if self.busy:
            return
        self.busy = True
        self.btn.configure(state="disabled", text="安装中…")
        self.set_state("正在安装…")
        dest = self.dest.get().strip()

        def work():
            # 子线程只投结果，界面全部由主线程轮询取走（tkinter 不保证跨线程 after 安全）
            ok, msg, _d = install(dest, self.no_shortcut)
            self._q.put((ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                ok, msg = self._q.get_nowait()
                try:
                    self.done(ok, msg)
                except tk.TclError:
                    return
        except queue.Empty:
            pass
        try:
            if not self.root.winfo_exists():
                return
            self._poll_job = self.root.after(120, self._poll)
        except tk.TclError:
            return

    def _cancel_poll(self, _e=None):
        try:
            if getattr(self, "_poll_job", None):
                self.root.after_cancel(self._poll_job)
        except (tk.TclError, ValueError):
            pass
        self._poll_job = None

    def done(self, ok, msg):
        self.busy = False
        self.set_state(msg, CYAN if ok else ERR)
        self.btn.configure(text="完成", state="normal", command=self.root.destroy)


def run(preset=None, no_shortcut=False):
    root = tk.Tk()
    apply_theme(root)
    fm, fs, family = fonts(root)
    SetupUI(root, fm, fs, family, preset, no_shortcut)
    root.mainloop()
    return 0
