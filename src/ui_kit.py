# -*- coding: utf-8 -*-
"""深色自绘控件：胶囊按钮、圆角输入、阶段微标、进度条，以及 DPI / 居中 / 字体 / 图标 / Tooltip。

配色取抖音品牌色：近黑底 + 品牌红 #FE2C55 + 青 #25F4EE。
所有正文与辅助文字都按 WCAG AA 调过对比度（见 tests/verify_ui.py 的对比度断言）。
"""
import calendar
import ctypes
import datetime as dt
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#0e1014"
PANEL = "#151922"
SURFACE = "#1c2130"
TEXT = "#e8edf5"
MUTED = "#9aa5b6"        # 对 BG 8.0:1、对 SURFACE 6.4:1
ACCENT = "#fe2c55"
ACCENT_HI = "#ff4d6d"
ON_ACCENT = "#170409"    # 品牌红上的字用近黑：5.5:1（白字只有 3.7:1）
CYAN = "#25f4ee"
DONE_BG = "#0e2f33"
BORDER = "#2a3140"
ERR = "#ff7a7a"
ERR_BG = "#2a1216"
WARN = "#ffb020"
TRACK = "#232a38"
WHITE = "#ffffff"


def enable_dpi():
    """进程级 DPI 感知，必须在创建任何 Tk 根窗口之前调用。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def center(root, width, height):
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")


def fonts(root):
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    fam = next((n for n in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Segoe UI")
                if n in fams), "TkDefaultFont")
    return (fam, 10), (fam, 9), fam


def icon_path():
    m = getattr(sys, "_MEIPASS", None)
    p = os.path.join(m, "app.ico") if m else os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    return p if os.path.isfile(p) else ""


def apply_icon(root):
    p = icon_path()
    if not p:
        return
    try:
        root.iconbitmap(p)
    except (tk.TclError, OSError):
        pass


def apply_theme(root):
    """深色底 + ttk 控件跟着走，避免出现白底原生控件。"""
    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    for name in ("TFrame", "TLabel", "TLabelframe", "TLabelframe.Label"):
        try:
            style.configure(name, background=BG, foreground=TEXT)
        except tk.TclError:
            pass
    try:
        style.configure("TButton", background=SURFACE, foreground=TEXT,
                        bordercolor=BORDER, focusthickness=1)
        style.map("TButton", background=[("active", BORDER)])
        style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                        insertcolor=TEXT, bordercolor=BORDER)
        style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                        foreground=TEXT, bordercolor=BORDER, rowheight=22)
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", ON_ACCENT)])
        style.configure("Treeview.Heading", background=PANEL, foreground=MUTED,
                        bordercolor=BORDER, relief="flat")
        for name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(name, background=PANEL, troughcolor=BG, bordercolor=BG,
                            arrowcolor=MUTED, darkcolor=PANEL, lightcolor=PANEL,
                            relief="flat", width=12)
            style.map(name, background=[("active", BORDER)],
                      arrowcolor=[("active", TEXT)])
        style.configure("TProgressbar", troughcolor=TRACK, background=ACCENT)
    except tk.TclError:
        pass


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, splinesteps=12, **kw)


def contrast(fg, bg):
    """WCAG 对比度，测试里直接调用；也用于自检配色。"""
    def lum(hex_color):
        c = hex_color.lstrip("#")
        vals = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in vals]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


class Tooltip:
    """仅鼠标悬停时出现的完整文本，用来替代常驻的解释性文字。"""

    def __init__(self, widget, text_func, font=("Microsoft YaHei UI", 9)):
        self.widget = widget
        self.text_func = text_func
        self.font = font
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, _event=None):
        try:
            text = self.text_func()
        except Exception:
            return
        if not text or self.tip:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=text, justify="left", wraplength=460,
                     background=PANEL, foreground=TEXT,
                     relief="solid", borderwidth=1, font=self.font,
                     highlightbackground=BORDER, padx=10, pady=8).pack()
        except (tk.TclError, OSError):
            self.tip = None

    def hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except (tk.TclError, OSError):
                pass
            self.tip = None


class CapsuleButton(tk.Canvas):
    """胶囊按钮。primary=品牌红主按钮，否则深色次按钮。"""

    def __init__(self, master, text="", command=None, primary=False,
                 width=80, height=36, font=None, **kw):
        self._bg = kw.pop("bg", None) or getattr(master, "cget", lambda _k: BG)("bg") or BG
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bd=0, bg=self._bg, cursor="hand2", takefocus=1, **kw)
        self._text = text
        self._command = command
        self._primary = primary
        self._state = "normal"
        self._hover = False
        self._focus = False
        self._font = font or ("Microsoft YaHei UI", 10, "bold" if primary else "normal")
        self._box_w, self._box_h = width, height
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<space>", self._on_key)
        self.bind("<Return>", self._on_key)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def configure(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            self._state = kw.pop("state")
            try:
                super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
            except tk.TclError:
                pass
        if kw:
            super().configure(**kw)
        self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)

    def _palette(self):
        if self._state == "disabled":
            return SURFACE, MUTED, BORDER, None
        if self._primary:
            fill = ACCENT_HI if self._hover else ACCENT
            return fill, ON_ACCENT, fill, ACCENT_HI
        fill = "#242b3b" if self._hover else SURFACE
        return fill, TEXT, BORDER, None

    def _draw(self):
        self.delete("all")
        w = int(self.winfo_width() or self._box_w)
        h = int(self.winfo_height() or self._box_h)
        fill, fg, border, shadow = self._palette()
        r = h / 2
        if shadow and self._state != "disabled":
            _round_rect(self, 1, 3, w - 1, h - 1, r, fill=shadow, outline="")
            _round_rect(self, 1, 1, w - 1, h - 3, r, fill=fill, outline="")
        else:
            _round_rect(self, 1, 1, w - 1, h - 1, r, fill=fill, outline=border)
        self.create_text(w / 2, h / 2 - (1 if shadow else 0), text=self._text,
                         fill=fg, font=self._font)
        if self._focus and self._state != "disabled":
            _round_rect(self, 3, 3, w - 3, h - 3, max(2, r - 2),
                        fill="", outline=CYAN, width=2)

    def _on_enter(self, _e=None):
        self._hover = True
        self._draw()

    def _on_leave(self, _e=None):
        self._hover = False
        self._draw()

    def _on_focus_in(self, _e=None):
        self._focus = True
        self._draw()

    def _on_focus_out(self, _e=None):
        self._focus = False
        self._draw()

    def _on_key(self, _e=None):
        if self._state != "disabled" and self._command:
            self._command()
        return "break"

    def _on_press(self, _e=None):
        self.focus_set()
        if self._state != "disabled":
            self._hover = False
            self._draw()

    def _on_release(self, _e=None):
        self._hover = True
        self._draw()
        if self._state != "disabled" and self._command:
            self._command()


class RoundedEntry(tk.Frame):
    """圆角输入框，对外代理 get / insert / delete / bind。"""

    def __init__(self, master, font=None, width=20, pxwidth=None, placeholder="", **kw):
        self._placeholder = placeholder
        super().__init__(master, bg=BG, highlightthickness=0)
        self._height = 36
        if pxwidth:
            self._min_w = int(pxwidth)
        else:
            try:
                fnt = tkfont.Font(font=font) if font else tkfont.nametofont("TkDefaultFont")
                self._min_w = max(120, fnt.measure("0") * int(width) + 36)
            except (tk.TclError, TypeError, ValueError):
                self._min_w = max(120, int(width or 20) * 9 + 36)
        self.configure(width=self._min_w, height=self._height)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=BG)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.entry = tk.Entry(
            self, font=font, width=width, bd=0, highlightthickness=0,
            relief="flat", bg=SURFACE, fg=TEXT, insertbackground=CYAN,
            readonlybackground=SURFACE, disabledbackground=SURFACE,
            disabledforeground=MUTED, selectbackground=ACCENT,
            selectforeground=ON_ACCENT, **kw)
        self.entry.place(x=14, y=5, width=self._min_w - 28, height=26)
        self._ph = tk.Label(self, text=placeholder, bg=SURFACE, fg=MUTED, font=font,
                            cursor="xterm")
        self._ph.bind("<Button-1>", lambda _e: self.entry.focus_set())
        self._canvas.bind("<Configure>", self._on_resize)
        self.entry.bind("<FocusIn>", lambda _e: self._on_focus(True))
        self.entry.bind("<FocusOut>", lambda _e: self._on_focus(False))
        self.entry.bind("<KeyRelease>", lambda _e: self._sync_placeholder())
        self._focus = False
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, _event=None):
        w = max(self._min_w, int(self.winfo_width() or self._min_w))
        self.entry.place_configure(x=14, y=5, width=max(20, w - 28), height=26)
        self._sync_placeholder()
        self._draw()

    def _on_focus(self, focus):
        self._draw(focus=focus)
        self._sync_placeholder()

    def _sync_placeholder(self):
        if not self._placeholder:
            return
        try:
            show = (not self.entry.get()) and self.entry.focus_get() is not self.entry
            if show:
                self._ph.place(x=14, y=6)
            else:
                self._ph.place_forget()
        except (tk.TclError, KeyError):
            pass

    def _draw(self, event=None, focus=None):
        if focus is not None:
            self._focus = focus
        c = self._canvas
        c.delete("all")
        w = int(c.winfo_width() or self.winfo_width() or self._min_w)
        h = int(c.winfo_height() or self._height)
        if w < 4 or h < 4:
            return
        outline = ACCENT if self._focus else BORDER
        _round_rect(c, 1, 1, w - 1, h - 1, h / 2, fill=SURFACE, outline=outline)

    def get(self):
        return self.entry.get()

    def insert(self, index, text):
        out = self.entry.insert(index, text)
        self._sync_placeholder()
        return out

    def delete(self, first, last=None):
        out = self.entry.delete(first, last)
        self._sync_placeholder()
        return out

    def bind(self, seq, func, add=None):
        return self.entry.bind(seq, func, add)


class ToggleSwitch(tk.Canvas):
    """带轨道的开关：开=品牌红，关=深灰。支持键盘空格/回车。"""

    def __init__(self, master, value=False, command=None, width=48, height=26, **kw):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bd=0, bg=BG, cursor="hand2", takefocus=1, **kw)
        self._value = bool(value)
        self._command = command
        self._enabled = True
        self.bind("<Button-1>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def get(self):
        return self._value

    def set(self, value):
        self._value = bool(value)
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        try:
            self.configure(cursor="hand2" if enabled else "arrow")
        except tk.TclError:
            pass
        self._draw()

    def _toggle(self, _e=None):
        if not self._enabled:
            return "break"
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)
        return "break"

    def _draw(self):
        self.delete("all")
        w = int(self.winfo_width() or 48)
        h = int(self.winfo_height() or 26)
        r = h / 2
        fill = (ACCENT if self._value else BORDER) if self._enabled else SURFACE
        _round_rect(self, 1, 1, w - 1, h - 1, r, fill=fill, outline="")
        knob = h - 8
        cx = (w - knob - 4) if self._value else 4
        self.create_oval(cx, 4, cx + knob, 4 + knob, fill=TEXT if self._enabled else MUTED,
                         outline="")


class PhaseBadge(tk.Canvas):
    """阶段胶囊微标：pending / now / done / failed。"""

    def __init__(self, master, text="", font=None, width=70, height=24, **kw):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bd=0, bg=BG, **kw)
        self._text = text
        self._font = font or ("Microsoft YaHei UI", 9)
        self._mode = "pending"
        self._box_w, self._box_h = width, height
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def set_mode(self, mode):
        self._mode = mode if mode in ("pending", "now", "done", "failed") else "pending"
        self._draw()

    def _draw(self):
        self.delete("all")
        w = int(self.winfo_width() or self._box_w)
        h = int(self.winfo_height() or self._box_h)
        if self._mode == "now":
            fill, fg = ACCENT, ON_ACCENT
        elif self._mode == "done":
            fill, fg = DONE_BG, CYAN
        elif self._mode == "failed":
            fill, fg = ERR_BG, ERR
        else:
            fill, fg = SURFACE, MUTED
        _round_rect(self, 1, 1, w - 1, h - 1, h / 2, fill=fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)


class ProgressBar(tk.Canvas):
    """品牌红进度条；determinate 与 indeterminate 两种。"""

    def __init__(self, master, height=8, **kw):
        super().__init__(master, height=height + 4, highlightthickness=0, bd=0, bg=BG, **kw)
        self._h = height
        self._value = 0
        self._maximum = 100
        self._mode = "determinate"
        self._job = None
        self._pulse = 0
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def start(self, interval=14):
        self._mode = "indeterminate"
        if self._job:
            try:
                self.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
        self._pulse = 0
        self._tick(max(int(interval), 8))

    def stop(self):
        self._mode = "determinate"
        if self._job:
            try:
                self.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
            self._job = None
        self._draw()

    def set_progress(self, index, total):
        self._mode = "determinate"
        try:
            self._value = max(0, int(index))
            self._maximum = max(1, int(total) if total else 1)
        except (TypeError, ValueError):
            return
        if self._job:
            try:
                self.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
            self._job = None
        self._draw()

    def _tick(self, interval):
        self._pulse = (self._pulse + 3) % 120
        self._draw()
        try:
            self._job = self.after(interval, lambda: self._tick(interval))
        except tk.TclError:
            self._job = None

    def _draw(self):
        self.delete("all")
        w = int(self.winfo_width() or 100)
        h = int(self.winfo_height() or (self._h + 4))
        y1, y2 = 2, h - 2
        _round_rect(self, 0, y1, w, y2, (y2 - y1) / 2, fill=TRACK, outline="")
        if self._mode == "indeterminate":
            span = max(24, int(w * 0.28))
            travel = max(1, w - span)
            x = int((self._pulse / 120.0) * travel)
            _round_rect(self, x, y1, x + span, y2, (y2 - y1) / 2, fill=ACCENT, outline="")
        else:
            ratio = min(1.0, self._value / float(self._maximum or 1))
            if ratio > 0:
                _round_rect(self, 0, y1, max(8, int(w * ratio)), y2,
                            (y2 - y1) / 2, fill=ACCENT, outline="")


class DatePicker:
    """日历弹层，选中后把 YYYY-MM-DD 写回输入框；Esc 只关日历。"""

    def __init__(self, entry, font=None):
        self.entry = entry
        self.font = font or ("Microsoft YaHei UI", 9)
        self.win = None

    def toggle(self, _event=None):
        if self.win is not None:
            self.close()
            return
        self.open()

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None

    def _current(self):
        raw = ""
        try:
            raw = self.entry.get().strip()
        except Exception:
            pass
        try:
            return dt.datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return dt.date.today()

    def open(self):
        self.close()
        widget = self.entry.winfo_toplevel() if hasattr(self.entry, "winfo_toplevel") else self.entry
        host = self.entry
        try:
            x = host.winfo_rootx()
            y = host.winfo_rooty() + host.winfo_height() + 4
        except tk.TclError:
            return
        cur = self._current()
        self._year, self._month = cur.year, cur.month
        self.win = tk.Toplevel(widget)
        self.win.wm_overrideredirect(True)
        self.win.configure(bg=BORDER)
        self.win.wm_geometry(f"+{x}+{y}")
        self._body = tk.Frame(self.win, bg=PANEL, padx=8, pady=8)
        self._body.pack(padx=1, pady=1)
        self._render(cur)
        self.win.bind("<FocusOut>", lambda _e: self.close())
        self.win.bind("<Escape>", self._on_escape)
        self.win.focus_set()

    def _on_escape(self, _e=None):
        self.close()
        return "break"

    def _render(self, selected):
        for w in self._body.winfo_children():
            w.destroy()
        head = tk.Frame(self._body, bg=PANEL)
        head.pack(fill="x")
        tk.Button(head, text="‹", bd=0, bg=PANEL, fg=TEXT, font=self.font,
                  activebackground=SURFACE, activeforeground=TEXT,
                  command=lambda: self._shift(-1), cursor="hand2").pack(side="left")
        tk.Label(head, text=f"{self._year}-{self._month:02d}", bg=PANEL, fg=TEXT,
                 font=self.font).pack(side="left", expand=True)
        tk.Button(head, text="›", bd=0, bg=PANEL, fg=TEXT, font=self.font,
                  activebackground=SURFACE, activeforeground=TEXT,
                  command=lambda: self._shift(1), cursor="hand2").pack(side="right")
        grid = tk.Frame(self._body, bg=PANEL)
        grid.pack(pady=(6, 0))
        for i, name in enumerate("一二三四五六日"):
            tk.Label(grid, text=name, bg=PANEL, fg=MUTED, font=self.font, width=3).grid(row=0, column=i)
        weeks = calendar.Calendar(0).monthdayscalendar(self._year, self._month)
        today = dt.date.today()
        for r, week in enumerate(weeks, 1):
            for c, day in enumerate(week):
                if day == 0:
                    tk.Label(grid, text="", bg=PANEL, width=3).grid(row=r, column=c)
                    continue
                d = dt.date(self._year, self._month, day)
                bg, fg = PANEL, TEXT
                if d == selected:
                    bg, fg = ACCENT, ON_ACCENT
                elif d == today:
                    bg, fg = DONE_BG, CYAN
                btn = tk.Label(grid, text=str(day), bg=bg, fg=fg, font=self.font,
                               width=3, cursor="hand2")
                btn.grid(row=r, column=c, padx=1, pady=1)
                btn.bind("<Button-1>", lambda _e, dd=d: self._pick(dd))

    def _shift(self, delta):
        m = self._month + delta
        y = self._year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        self._year, self._month = y, m
        self._render(self._current())

    def _pick(self, day):
        try:
            self.entry.delete(0, "end")
            self.entry.insert(0, day.isoformat())
        except tk.TclError:
            pass
        self.close()
