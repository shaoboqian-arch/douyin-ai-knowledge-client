# -*- coding: utf-8 -*-
"""单实例互斥：主界面只允许一个窗口；重复启动弹海岛浅色提示。

机制：命名互斥体（Local\\douyin-fav-sync.app-instance）。
· 拿到互斥体 → 正常启动；进程退出时 Windows 自动回收，无需显式清理。
· 互斥体已存在 → 第二个实例把已有窗口带到前台，弹提示后退出。
· 互斥体创建失败（权限等意外）→ 放行启动，守护不能挡住应用本身。
只作用于主界面路径：--mcp（服务，允许与主界面并存）、--cli（一次性命令）、
安装向导都不受限。
"""
import ctypes
import os

from common import APP_NAME, MCP_SERVER_NAME, VERSION

MUTEX_NAME = f"Local\\{MCP_SERVER_NAME}.app-instance"
_ERROR_ALREADY_EXISTS = 183
_HANDLE = None


def acquire():
    """尝试成为唯一实例。返回 True=可以启动；False=已有实例在跑。"""
    global _HANDLE
    if os.name != "nt":
        return True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        k32.CloseHandle(handle)
        return False
    _HANDLE = handle
    return True


def release():
    """显式释放互斥体（门禁测试用；正常进程退出会自动回收）。"""
    global _HANDLE
    if _HANDLE:
        try:
            ctypes.WinDLL("kernel32").CloseHandle(_HANDLE)
        except Exception:
            pass
        _HANDLE = None


def raise_existing(title):
    """把已在运行的主窗口还原并带到前台（尽力而为，找不到就跳过）。"""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)               # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def run_already_running_dialog(raised=False):
    """「已在运行」提示窗：与主界面同一套海岛浅色（BG / 卡片 / 胶囊按钮）。

    用户点「知道了」（或 Esc / 关窗）后进程退出。第二个实例的黑色控制台
    已由 hide_console 按独占规则处理，双击启动时不会看见。
    """
    import tkinter as tk
    import ui_kit

    root = tk.Tk()
    root.title(f"{APP_NAME} 已在运行")
    root.resizable(False, False)
    root.configure(bg=ui_kit.BG)
    ui_kit.apply_icon(root)
    ui_kit.apply_theme(root)
    fm, fs, family = ui_kit.fonts(root)
    ui_kit.center(root, 420, 192)

    f = tk.Frame(root, bg=ui_kit.BG, padx=24, pady=20)
    f.pack(fill="both", expand=True)
    card = tk.Frame(f, bg=ui_kit.CARD,
                    highlightbackground=ui_kit.CARD_LINE, highlightthickness=1)
    card.pack(fill="both", expand=True)
    inner = tk.Frame(card, bg=ui_kit.CARD, padx=18, pady=16)
    inner.pack(fill="both", expand=True)

    tk.Label(inner, text="已经在运行了", font=(family, 12, "bold"),
             bg=ui_kit.CARD, fg=ui_kit.TEXT, anchor="w").pack(fill="x")
    if raised:
        note = ("已经有一个「抖音收藏整理」窗口在运行，已帮你带到前台。\n"
                "不用重复打开；用完那个窗口直接关就行。")
    else:
        note = ("已经有一个「抖音收藏整理」窗口在运行。\n"
                "不用重复打开；需要的话去任务栏找「抖音收藏整理」。")
    tk.Label(inner, text=note, font=fs, bg=ui_kit.CARD, fg=ui_kit.MUTED,
             justify="left", anchor="w").pack(fill="x", pady=(6, 14))
    row = tk.Frame(inner, bg=ui_kit.CARD)
    row.pack(fill="x")
    row.columnconfigure(0, weight=1)
    ui_kit.CapsuleButton(row, text="知道了", command=root.destroy,
                         primary=True, width=108, height=36,
                         font=(family, 10, "bold")).grid(row=0, column=1)

    root.bind("<Return>", lambda _e: root.destroy())
    root.bind("<Escape>", lambda _e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return 0
