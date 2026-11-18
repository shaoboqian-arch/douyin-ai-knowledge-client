# -*- coding: utf-8 -*-
"""海岛风格自绘控件：胶囊按钮、圆角输入、阶段微标、进度条，以及 DPI / 居中 / 字体 / 图标 / Tooltip。

配色对照 animal-island / 微信收藏导出 V0.4.4：羊皮纸底 #f8f8f0，字 #794f27，薄荷主色 #19c8b9。
不改系统窗口圆角框，只把内部画成海岛风格。字体仍用 Microsoft YaHei UI 回退。
所有正文与辅助文字都按 WCAG AA 调过对比度（见 tests/verify_ui.py 的对比度断言）。
"""
import calendar
import ctypes
import datetime as dt
import os
import sys
import time

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
except ImportError:  # 无桌面环境时仍可跑配色对比度等纯计算测试
    tk = None
    tkfont = None
    ttk = None

from common import pointer_inside

# 海岛配色（与微信收藏导出 V0.4.4 同一套 token）
BG = "#f8f8f0"
TEXT = "#794f27"
# MUTED 原为 #9f927d：配 BG 只有 2.86:1、配 SAND 2.51:1，达不到 AA。
# 加深到 #6f6455 → BG 5.42:1、SAND 4.75:1，仍属同一支灰棕。
MUTED = "#6f6455"
MINT = "#19c8b9"
MINT_HI = "#50b9ab"
MINT_BG = "#e6f9f6"
# 非文本元素（进度条填充、日历箭头 hover）要用深薄荷：MINT 对 TRACK 只有 1.63:1，
# 低于 WCAG 非文本 3:1；MINT_DEEP 对 TRACK 4.68:1、对 SAND 4.95:1，仍是同一支色。
MINT_DEEP = "#0b6f66"
# 薄荷主按钮上的字：米白 #f8f8f0 只有 1.97:1（悬停 2.22:1），改用深棕 6.45:1（悬停 5.72:1）。
ON_MINT = "#3f2a12"
SAND = "#f0e8d8"
BORDER = "#dcd8d1"
# 错误红原为 #e05a5a（3.40:1），加深到 6.15:1；ERR_BG 只是底色，不动。
ERR = "#b02a1f"
ERR_BG = "#fdeeee"
WHITE = "#ffffff"
PAPER = "#fffef8"
GREEN = "#1a7f37"
# 警告用暗橙 #9a4d00：对 BG 5.73:1、对 SAND 5.02:1，浅底上达到 AA。
WARN = "#9a4d00"
TRACK = "#e8e2d6"

# 旧名字别名，少改其它页面的 import / 引用
ACCENT = MINT
ACCENT_HI = MINT_HI
ON_ACCENT = ON_MINT
CYAN = GREEN  # 成功/状态不再用亮青，浅底上对比不够
DONE_BG = MINT_BG
PANEL = PAPER
SURFACE = SAND
# 0.1.3/0.1.4 分区卡片用的名字；浅色里卡片用纸面，描边用统一边线
CARD = PAPER
CARD_LINE = BORDER

# 字体族唯一真源：fonts() 探测到系统可用的 CJK 字体后写入；所有控件的默认字体都读它，
# 避免「一部分走 fonts()、一部分写死字体名」造成同一窗口里两套字族。
FONT_FAMILY = "Microsoft YaHei UI"


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
    global FONT_FAMILY
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    fam = next((n for n in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Segoe UI")
                if n in fams), "TkDefaultFont")
    FONT_FAMILY = fam
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
    """浅色海岛底 + ttk 控件跟着走，避免白/深色控件裂开。"""
    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
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
        style.configure("TButton", background=SAND, foreground=TEXT,
                        bordercolor=BORDER, focusthickness=1)
        style.map("TButton", background=[("active", TRACK)])
        style.configure("TEntry", fieldbackground=WHITE, foreground=TEXT,
                        insertcolor=TEXT, bordercolor=BORDER)
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE,
                        foreground=TEXT, bordercolor=BORDER, rowheight=28)
        style.map("Treeview", background=[("selected", MINT)],
                  foreground=[("selected", ON_MINT)])
        style.configure("Treeview.Heading", background=SAND, foreground=MUTED,
                        bordercolor=BORDER, relief="flat", padding=(8, 6))
        style.map("Treeview.Heading",
                  background=[("active", TRACK)],
                  foreground=[("active", TEXT)])
        for name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(name, background=SAND, troughcolor=BG, bordercolor=BG,
                            arrowcolor=MUTED, darkcolor=SAND, lightcolor=SAND,
                            relief="flat", width=12)
            style.map(name, background=[("active", BORDER)],
                      arrowcolor=[("active", TEXT)])
        style.configure("TProgressbar", troughcolor=TRACK, background=MINT)
    except tk.TclError:
        pass


def _hex_rgb(color):
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lerp_color(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    ra, ga, ba = _hex_rgb(a)
    rb, gb, bb = _hex_rgb(b)
    return "#{:02x}{:02x}{:02x}".format(
        int(ra + (rb - ra) * t),
        int(ga + (gb - ga) * t),
        int(ba + (bb - ba) * t),
    )


def _bezier_xy(s, p1, p2):
    u = 1.0 - s
    x = 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s * s * s
    y = 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s * s * s
    return x, y


def ease_out(t):
    """cubic-bezier(0.23, 1, 0.32, 1)，用于 UI 出现与位移。"""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    lo, hi = 0.0, 1.0
    p1, p2 = (0.23, 1.0), (0.32, 1.0)
    for _ in range(14):
        mid = (lo + hi) / 2.0
        x, _y = _bezier_xy(mid, p1, p2)
        if x < t:
            lo = mid
        else:
            hi = mid
    _x, y = _bezier_xy((lo + hi) / 2.0, p1, p2)
    return y


def prefers_reduced_motion():
    """跟随系统「窗口内动画」开关；关了就只留颜色，不做位移。"""
    if os.name != "nt":
        return False
    try:
        val = ctypes.c_int(1)
        # SPI_GETCLIENTAREAANIMATION = 0x1042
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(val), 0)
        return val.value == 0
    except Exception:
        return False


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


if tk is None:
    # 无 tkinter 时到此为止：token、对比度与缓动仍可导入。
    pass
else:

    def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return canvas.create_polygon(pts, smooth=True, splinesteps=12, **kw)


    class Tooltip:
        """仅鼠标悬停时出现的完整文本，用来替代常驻的解释性文字。"""

        def __init__(self, widget, text_func, font=None):
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
                         background=SAND, foreground=TEXT,
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
        """胶囊按钮。主界面、设置页、安装向导共用同一套悬停/按下力学：

        悬停抬起并拉出阴影，按下缩小并收回阴影；颜色只是伴随变化，不是唯一反馈。
        松开时若指针已离开矩形，则取消点击。
        """

        _HOVER_MS = 140
        _PRESS_MS = 100

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
            self._key_held = False       # 键盘自动重复去重（F-4）
            self._font = font or (FONT_FAMILY, 10, "bold" if primary else "normal")
            self._box_w, self._box_h = width, height
            self._lift = 0.0
            self._press = 0.0
            self._lift_from = 0.0
            self._press_from = 0.0
            self._lift_to = 0.0
            self._press_to = 0.0
            self._anim_id = None
            self._anim_t0 = 0.0
            self._anim_dur = self._HOVER_MS / 1000.0
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)
            self.bind("<FocusIn>", self._on_focus_in)
            self.bind("<FocusOut>", self._on_focus_out)
            self.bind("<space>", self._on_key)
            self.bind("<Return>", self._on_key)
            self.bind("<KeyRelease-space>", self._on_key_release)
            self.bind("<KeyRelease-Return>", self._on_key_release)
            self.bind("<Configure>", lambda _e: self._draw())
            self.bind("<Destroy>", self._cancel_anim, add="+")
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
                if self._state == "disabled":
                    self._hover = False
                    self._lift = self._press = 0.0
                    self._lift_to = self._press_to = 0.0
                    self._cancel_anim()
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

        def _cancel_anim(self, _e=None):
            if self._anim_id is not None:
                try:
                    self.after_cancel(self._anim_id)
                except (tk.TclError, ValueError):
                    pass
                self._anim_id = None

        def _retarget(self, duration_ms):
            self._lift_from, self._press_from = self._lift, self._press
            if prefers_reduced_motion():
                self._lift, self._press = self._lift_to, self._press_to
                self._cancel_anim()
                self._draw()
                return
            if abs(self._lift - self._lift_to) < 0.01 and abs(self._press - self._press_to) < 0.01:
                self._lift, self._press = self._lift_to, self._press_to
                self._cancel_anim()
                self._draw()
                return
            self._anim_t0 = time.perf_counter()
            self._anim_dur = max(0.06, duration_ms / 1000.0)
            self._cancel_anim()
            self._tick()

        def _tick(self):
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            t = (time.perf_counter() - self._anim_t0) / self._anim_dur
            p = ease_out(t)
            if t >= 1:
                self._lift, self._press = self._lift_to, self._press_to
                self._anim_id = None
                self._draw()
                return
            self._lift = self._lift_from + (self._lift_to - self._lift_from) * p
            self._press = self._press_from + (self._press_to - self._press_from) * p
            self._draw()
            try:
                self._anim_id = self.after(8, self._tick)
            except tk.TclError:
                self._anim_id = None

        def _draw(self):
            self.delete("all")
            w = int(self.winfo_width() or self._box_w)
            h = int(self.winfo_height() or self._box_h)
            if w < 8 or h < 8:
                return
            disabled = self._state == "disabled"
            lift = 0.0 if disabled else self._lift
            press = 0.0 if disabled else self._press
            if disabled:
                fill, fg, border = SAND, MUTED, BORDER
                shadow = None
            elif self._primary:
                fill = _lerp_color(MINT, MINT_HI, lift)
                if press:
                    fill = _lerp_color(fill, "#14b3a5", press)
                fg, border = ON_MINT, fill
                # 中性暖灰影，避免薄荷影和浅填充叠在一起看不清抬起。
                shadow = _lerp_color("#c9bfb0", "#9e9282", lift)
            else:
                fill = _lerp_color(SAND, "#f7f1e6", lift)
                if press:
                    fill = _lerp_color(fill, "#e8dfcf", press)
                fg, border = TEXT, BORDER
                shadow = "#b8aea0"

            # 预留上下空位：悬停抬起约 4px，阴影落到按钮下面。
            pad_top, pad_bot = 5.0, 7.0
            shift_y = -4.0 * lift + 2.0 * press
            scale = 1.0 - 0.05 * press
            x1, y1, x2, y2 = 1.0, pad_top + shift_y, w - 1.0, h - pad_bot + shift_y
            if scale < 0.999:
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                bw, bh = (x2 - x1) * scale, (y2 - y1) * scale
                x1, x2 = cx - bw / 2.0, cx + bw / 2.0
                y1, y2 = cy - bh / 2.0, cy + bh / 2.0
            r = max(2.0, (y2 - y1) / 2.0)
            shadow_dy = (3.0 + 4.0 * lift) * (1.0 - press) if self._primary else (5.0 * lift * (1.0 - press))
            if shadow and shadow_dy > 0.4 and not disabled:
                _round_rect(self, x1, y1 + shadow_dy, x2, y2 + shadow_dy, r,
                            fill=shadow, outline="")
                _round_rect(self, x1, y1, x2, y2, r, fill=fill, outline="")
            else:
                _round_rect(self, x1, y1, x2, y2, r, fill=fill, outline=border)
            self.create_text((x1 + x2) / 2.0, (y1 + y2) / 2.0, text=self._text,
                             fill=fg, font=self._font)
            # 焦点环只给键盘，避免鼠标按下时被描边抢走「按下收回」的观感。
            if self._focus and not disabled and press < 0.2:
                _round_rect(self, x1 + 1, y1 + 1, x2 - 1, y2 - 1, max(1.0, r - 1),
                            fill="", outline=TEXT, width=2)

        def _on_enter(self, _e=None):
            if self._state == "disabled":
                return
            self._hover = True
            self._lift_to = 1.0
            if self._press_to < 0.5:
                self._press_to = 0.0
            self._retarget(self._HOVER_MS)

        def _on_leave(self, _e=None):
            self._hover = False
            self._lift_to = 0.0
            self._press_to = 0.0
            self._retarget(self._HOVER_MS)

        def _on_focus_in(self, _e=None):
            self._focus = True
            self._draw()

        def _on_focus_out(self, _e=None):
            self._focus = False
            self._key_held = False       # 焦点中途移走，别把按钮锁在「已按下」
            self._draw()

        def _on_key(self, _e=None):
            if self._state == "disabled":
                return "break"
            # 长按空格/回车时系统会连发 KeyPress；只认第一次，松开才重置，
            # 避免 busy 时在「全仓同步 → 停止确认」之间反复触发（F-4）。
            if self._key_held:
                return "break"
            self._key_held = True
            self._press_to = 1.0
            self._lift_to = 0.0
            self._retarget(self._PRESS_MS)

            def _bounce():
                self._press_to = 0.0
                self._lift_to = 1.0 if self._hover else 0.0
                self._retarget(self._PRESS_MS)

            try:
                self.after(self._PRESS_MS, _bounce)
            except tk.TclError:
                pass
            if self._command:
                self._command()
            return "break"

        def _on_key_release(self, _e=None):
            self._key_held = False
            return "break"

        def _on_press(self, _e=None):
            if self._state == "disabled":
                return
            # 鼠标按下不抢焦点，避免焦点环盖住按下收回的观感。
            self._press_to = 1.0
            self._lift_to = 0.0
            self._retarget(self._PRESS_MS)

        def _on_release(self, event=None):
            if self._state == "disabled":
                return
            was_pressed = self._press_to > 0.5 or self._press > 0.5
            w = int(self.winfo_width() or self._box_w)
            h = int(self.winfo_height() or self._box_h)
            inside = bool(event is not None and pointer_inside(event.x, event.y, w, h))
            self._hover = inside
            self._press_to = 0.0
            self._lift_to = 1.0 if inside else 0.0
            self._retarget(self._PRESS_MS)
            if was_pressed and inside and self._command:
                self._command()


    class RoundedEntry(tk.Frame):
        """圆角输入框，对外代理 get / insert / delete / bind。

        path=True 时：失焦把视野停在路径尾部，并用 tooltip 给出完整路径。
        回车默认截在输入框内，不冒泡到窗口级绑定。
        """

        def __init__(self, master, font=None, width=20, pxwidth=None, placeholder="",
                     path=False, path_font=None, panel_bg=BG, **kw):
            self._placeholder = placeholder
            self._path_mode = False
            self._right_inset = 14
            self._panel_bg = panel_bg
            super().__init__(master, bg=panel_bg, highlightthickness=0)
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
            self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=panel_bg)
            self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
            self.entry = tk.Entry(
                self, font=font, width=width, bd=0, highlightthickness=0,
                relief="flat", bg=WHITE, fg=TEXT, insertbackground=TEXT,
                readonlybackground=WHITE, disabledbackground=WHITE,
                disabledforeground=MUTED, selectbackground=MINT,
                selectforeground=ON_MINT, **kw)
            self.entry.place(x=14, y=5, width=self._min_w - 28, height=26)
            self._ph = tk.Label(self, text=placeholder, bg=WHITE, fg=MUTED, font=font,
                                cursor="xterm")
            self._ph.bind("<Button-1>", lambda _e: self.entry.focus_set())
            self._canvas.bind("<Configure>", self._on_resize)
            self.entry.bind("<FocusIn>", lambda _e: self._on_focus(True))
            self.entry.bind("<FocusOut>", lambda _e: self._on_focus(False))
            self.entry.bind("<KeyRelease>", lambda _e: self._sync_placeholder())
            self.entry.bind("<Return>", lambda _e: "break")
            self.entry.bind("<KP_Enter>", lambda _e: "break")
            self._focus = False
            self._hover = False
            for w in (self, self._canvas, self.entry, self._ph):
                w.bind("<Enter>", self._on_enter, add="+")
                w.bind("<Leave>", self._on_leave, add="+")
            tk.Frame.bind(self, "<Configure>", self._on_resize, add="+")
            if path:
                self.enable_path_view(path_font)

        def set_right_inset(self, px):
            try:
                self._right_inset = max(14, int(px))
            except (TypeError, ValueError):
                self._right_inset = 14
            self._on_resize()

        def enable_path_view(self, font=None):
            if self._path_mode:
                return
            self._path_mode = True
            Tooltip(self.entry, self.get, font=font or (FONT_FAMILY, 9))
            self.entry.bind("<FocusOut>", lambda _e: self.reveal_end(), add="+")
            try:
                self.after_idle(self.reveal_end)
            except tk.TclError:
                pass

        def reveal_end(self, _event=None):
            try:
                self.entry.xview_moveto(1)
            except tk.TclError:
                pass

        def _on_resize(self, _event=None):
            w = max(self._min_w, int(self.winfo_width() or self._min_w))
            inner = max(20, w - 14 - self._right_inset)
            self.entry.place_configure(x=14, y=5, width=inner, height=26)
            self._sync_placeholder()
            self._draw()
            if self._path_mode:
                try:
                    if self.entry.focus_get() is not self.entry:
                        self.reveal_end()
                except tk.TclError:
                    self.reveal_end()

        def _on_enter(self, _e=None):
            self._hover = True
            self._draw()

        def _on_leave(self, _e=None):
            # 移到内部 Entry / 占位符 / 嵌入按钮时 Frame 会先 Leave，看指针还在不在整块里。
            try:
                x, y = self.winfo_pointerxy()
                if (self.winfo_rootx() <= x <= self.winfo_rootx() + self.winfo_width()
                        and self.winfo_rooty() <= y <= self.winfo_rooty() + self.winfo_height()):
                    return
            except tk.TclError:
                pass
            self._hover = False
            self._draw()

        def _on_focus(self, focus):
            self._draw(focus=focus)
            self._sync_placeholder()
            if not focus and self._path_mode:
                self.reveal_end()

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
            if self._focus:
                outline, width = MINT, 2
            elif self._hover:
                outline, width = "#c8bfb0", 1
            else:
                outline, width = BORDER, 1
            _round_rect(c, 1, 1, w - 1, h - 1, h / 2, fill=WHITE, outline=outline, width=width)

        def get(self):
            return self.entry.get()

        def insert(self, index, text):
            out = self.entry.insert(index, text)
            self._sync_placeholder()
            if self._path_mode:
                try:
                    if self.entry.focus_get() is not self.entry:
                        self.reveal_end()
                except tk.TclError:
                    self.reveal_end()
            return out

        def delete(self, first, last=None):
            out = self.entry.delete(first, last)
            self._sync_placeholder()
            return out

        def set(self, text):
            """写入文本；只读框会临时解开再锁上。"""
            state = str(self.entry.cget("state") or "normal")
            if state != "normal":
                self.entry.configure(state="normal")
            self.delete(0, "end")
            self.insert(0, text or "")
            if state != "normal":
                self.entry.configure(state=state)

        def set_readonly(self, readonly=True):
            self.entry.configure(state="readonly" if readonly else "normal")

        def bind(self, seq, func, add=None):
            return self.entry.bind(seq, func, add)


    class ToggleSwitch(tk.Canvas):
        """开关：开=薄荷，关=浅沙描边；圆点带内边距与投影，支持悬停/键盘/焦点环。"""

        W, H = 44, 24

        def __init__(self, master, value=False, command=None, width=None, height=None, **kw):
            super().__init__(master, width=width or self.W, height=height or self.H,
                             highlightthickness=0, bd=0, bg=kw.pop("bg", BG),
                             cursor="hand2", takefocus=1, **kw)
            self._value = bool(value)
            self._command = command
            self._enabled = True
            self._focus = False
            self._hover = False
            self.bind("<Button-1>", self._toggle)
            self.bind("<space>", self._toggle)
            self.bind("<Return>", self._toggle)
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<FocusIn>", self._on_focus_in)
            self.bind("<FocusOut>", self._on_focus_out)
            self.bind("<Configure>", lambda _e: self._draw())
            self._draw()

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
            w = int(self.winfo_width() or self.W)
            h = int(self.winfo_height() or self.H)
            if w < 10 or h < 10:
                return
            r = h / 2

            if not self._enabled:
                track, outline = SAND, BORDER
                knob, knob_line, shadow = MUTED, BORDER, TRACK
            elif self._value:
                track = MINT_HI if self._hover else MINT
                outline = MINT
                knob, knob_line, shadow = WHITE, MINT_BG, TRACK
            else:
                track = TRACK if self._hover else SAND
                outline = BORDER
                knob, knob_line, shadow = WHITE, BORDER, TRACK

            _round_rect(self, 1, 1, w - 1, h - 1, r - 1, fill=track, outline=outline)

            d = h - 8                      # 圆点直径：上下各留 4px
            y = 4
            x = (w - d - 4) if self._value else 4
            # 投影：先画一层偏暗的圆，再叠主体，视觉上有厚度
            self.create_oval(x, y + 1, x + d, y + 1 + d, fill=shadow, outline="")
            self.create_oval(x, y, x + d, y + d, fill=knob, outline=knob_line)
            if self._focus and self._enabled:
                _round_rect(self, 1, 1, w - 1, h - 1, r - 1, fill="", outline=TEXT, width=1)


    class CheckBox(tk.Canvas):
        """标准复选框：方框 + 勾，支持键盘空格/回车与禁用态。0.1.4 起知识库开关改用本控件。"""

        SIZE = 20

        def __init__(self, master, value=False, command=None, size=None, **kw):
            self._size = int(size or self.SIZE)
            super().__init__(master, width=self._size, height=self._size,
                             highlightthickness=0, bd=0, bg=kw.pop("bg", BG),
                             cursor="hand2", takefocus=1, **kw)
            self._value = bool(value)
            self._command = command
            self._enabled = True
            self._focus = False
            self.bind("<Button-1>", self._toggle)
            self.bind("<space>", self._toggle)
            self.bind("<Return>", self._toggle)
            self.bind("<FocusIn>", lambda _e: self._set_focus(True))
            self.bind("<FocusOut>", lambda _e: self._set_focus(False))
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

        def _set_focus(self, focus):
            self._focus = bool(focus)
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
            n = self._size
            if self._value and self._enabled:
                fill, outline = MINT, MINT
            elif not self._enabled:
                fill, outline = SAND, BORDER
            else:
                fill, outline = WHITE, BORDER
            _round_rect(self, 2, 2, n - 2, n - 2, 5, fill=fill, outline=outline)
            if self._value:
                # 薄荷底上白勾只有约 2:1，用深棕才能达到 AA
                color = ON_MINT if self._enabled else MUTED
                self.create_line(n * 0.28, n * 0.52, n * 0.44, n * 0.68,
                                 n * 0.73, n * 0.32, fill=color, width=2,
                                 capstyle="round", joinstyle="round")
            if self._focus:
                _round_rect(self, 1, 1, n - 1, n - 1, 6, fill="", outline=TEXT, width=1)


    class PhaseBadge(tk.Canvas):
        """阶段胶囊微标：pending / now / done / failed。"""

        def __init__(self, master, text="", font=None, width=70, height=24, **kw):
            super().__init__(master, width=width, height=height, highlightthickness=0,
                             bd=0, bg=BG, **kw)
            self._text = text
            self._font = font or (FONT_FAMILY, 9)
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
                fill, fg = MINT, ON_MINT
            elif self._mode == "done":
                fill, fg = MINT_BG, TEXT
            elif self._mode == "failed":
                fill, fg = ERR_BG, ERR
            else:
                fill, fg = SAND, MUTED
            _round_rect(self, 1, 1, w - 1, h - 1, h / 2, fill=fill, outline="")
            self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)


    class ProgressBar(tk.Canvas):
        """薄荷进度条；determinate 与 indeterminate 两种。"""

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
                _round_rect(self, x, y1, x + span, y2, (y2 - y1) / 2,
                            fill=MINT_DEEP, outline="")
            else:
                ratio = min(1.0, self._value / float(self._maximum or 1))
                if ratio > 0:
                    _round_rect(self, 0, y1, max(8, int(w * ratio)), y2,
                                (y2 - y1) / 2, fill=MINT_DEEP, outline="")


    class DatePicker:
        """日历弹层，选中后把 YYYY-MM-DD 写回输入框；点弹层外或 Esc 关闭。

        embedded=True 时把「▾」收进圆角输入框尾部，不再单独占一列。
        翻月是同方向滑入滑出（约 220ms，可打断），星期行和左右键不动。
        """

        _SLIDE_MS = 220

        def __init__(self, entry, font=None, embedded=False, on_pick=None):
            self.entry = entry
            self.font = font or (FONT_FAMILY, 9)
            self.on_pick = on_pick
            self.win = None
            self._trigger = None
            self._slide_job = None
            self._root = None
            self._root_click_id = None
            self._pages = []
            if embedded:
                self._embed()

        def _embed(self):
            host = self.entry
            if not isinstance(host, RoundedEntry):
                return
            host.set_right_inset(36)
            self._trigger = CapsuleButton(
                host, text="▾", command=self.toggle, width=26, height=28,
                font=self.font, bg=WHITE)
            self._trigger.place(relx=1, x=-31, y=4, width=26, height=28)

        def toggle(self, _event=None):
            if self.win is not None:
                self.close()
                return
            self.open()

        def close(self):
            self._cancel_slide()
            try:
                if self._root is not None and self._root_click_id:
                    self._root.unbind("<Button-1>", self._root_click_id)
            except (tk.TclError, KeyError, ValueError):
                pass
            self._root_click_id = None
            if self.win is not None:
                try:
                    self.win.destroy()
                except tk.TclError:
                    pass
                self.win = None
            self._pages = []

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
            self._body = tk.Frame(self.win, bg=BG, padx=8, pady=8)
            self._body.pack(padx=1, pady=1)
            self._build_chrome()
            self.win.update_idletasks()
            self._show_month(self._year, self._month, animate=False)
            # 焦点在弹层内部移动（Tab 到「清除」）不能关窗；外部失焦才关（F-6）。
            self.win.bind("<Tab>", self._on_tab)
            self.win.bind("<Escape>", self._on_escape)
            # 点弹层外的任何地方就关：在应用根窗口挂 Button-1（bindtags 保证
            # 只抓主窗口里的点击，弹层自己的点击不会进这里）。
            # 不用 FocusOut 猜「焦点去哪了」——WM 焦点抖动会让它时灵时不灵。
            self._root = widget
            try:
                self._root_click_id = self._root.bind("<Button-1>", self._on_click, add="+")
            except (tk.TclError, AttributeError):
                self._root_click_id = None
            self.win.focus_set()

        def _on_click(self, event=None):
            """应用根窗口上的 Button-1：点到弹层外就关。

            点在弹层自己的控件上不会进这里（bindtags 走弹层 toplevel）；
            点在宿主输入框（含「▾」）上也算还在控件里，开/关交给触发器自己。
            """
            if self.win is None or event is None:
                return
            try:
                x, y = event.x_root, event.y_root
                wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
                ww, wh = self.win.winfo_width(), self.win.winfo_height()
                ex, ey = self.entry.winfo_rootx(), self.entry.winfo_rooty()
                ew, eh = self.entry.winfo_width(), self.entry.winfo_height()
            except (tk.TclError, AttributeError):
                return
            if ex <= x < ex + ew and ey <= y < ey + eh:
                return
            if not (wx <= x < wx + ww and wy <= y < wy + wh):
                self.close()

        def _on_tab(self, _e=None):
            """弹层里唯一可聚焦的动作是「清除」，Tab 直接送过去。"""
            if self.win is None:
                return "break"
            try:
                self._clear_btn.focus_set()
            except (tk.TclError, AttributeError):
                pass
            return "break"

        def _on_escape(self, _e=None):
            self.close()
            return "break"

        def _cell_size(self):
            try:
                fnt = tkfont.Font(font=self.font)
                cw = max(28, fnt.measure("00") + 12)
                ch = max(22, fnt.metrics("linespace") + 8)
            except (tk.TclError, TypeError, ValueError):
                cw, ch = 30, 24
            return cw, ch

        def _build_chrome(self):
            cw, ch = self._cell_size()
            self._stage_w = cw * 7
            # 日期格有 pady=1、ipady=1，6 行要加上这些间距，避免最后一周被裁切。
            self._stage_h = ch * 6 + 4 * 6
            head = tk.Frame(self._body, bg=BG)
            head.pack(fill="x")
            self._arrow(head, "‹", -1).pack(side="left")
            self._title_stage = tk.Frame(head, bg=BG, width=self._stage_w - 64, height=28)
            self._title_stage.pack(side="left", expand=True, fill="both")
            self._title_stage.pack_propagate(False)
            self._arrow(head, "›", 1).pack(side="right")
            days = tk.Frame(self._body, bg=BG)
            days.pack(pady=(6, 0))
            for i, name in enumerate("一二三四五六日"):
                tk.Label(days, text=name, bg=BG, fg=MUTED, font=self.font,
                         width=3).grid(row=0, column=i)
            self._stage = tk.Frame(self._body, bg=BG, width=self._stage_w,
                                   height=self._stage_h)
            self._stage.pack()
            self._stage.pack_propagate(False)
            foot = tk.Frame(self._body, bg=BG)
            foot.pack(fill="x", pady=(8, 0))
            self._clear_btn = CapsuleButton(
                foot, text="清除 / 回到不限", command=self._clear,
                width=168, height=28, font=self.font, bg=BG)
            self._clear_btn.pack()

        def _make_grid(self, year, month):
            grid = tk.Frame(self._stage, bg=BG, width=self._stage_w, height=self._stage_h)
            selected = self._current()
            today = dt.date.today()
            weeks = calendar.Calendar(0).monthdayscalendar(year, month)
            while len(weeks) < 6:
                weeks.append([0] * 7)
            for r, week in enumerate(weeks[:6]):
                for c, day in enumerate(week):
                    cell = tk.Label(grid, text="" if day == 0 else str(day),
                                    bg=BG, fg=TEXT, font=self.font, width=3)
                    cell.grid(row=r, column=c, padx=1, pady=1, ipady=1)
                    if day == 0:
                        continue
                    d = dt.date(year, month, day)
                    if d == selected:
                        cell.configure(bg=MINT, fg=ON_MINT, cursor="hand2")
                    elif d == today:
                        cell.configure(bg=MINT_BG, fg=TEXT, cursor="hand2")
                    else:
                        cell.configure(cursor="hand2")
                    cell._rest_bg = cell.cget("bg")
                    cell._rest_fg = cell.cget("fg")
                    if d != selected:
                        def _enter(_e, w=cell):
                            if w.cget("bg") != MINT:
                                w.configure(bg=SAND)

                        def _leave(_e, w=cell):
                            w.configure(bg=w._rest_bg, fg=w._rest_fg)

                        cell.bind("<Enter>", _enter)
                        cell.bind("<Leave>", _leave)
                    cell.bind("<Button-1>", lambda _e, dd=d: self._pick(dd))
            return grid

        def _make_title(self, year, month):
            return tk.Label(self._title_stage, text=f"{year}-{month:02d}",
                            bg=BG, fg=TEXT, font=self.font)

        def _cancel_slide(self):
            if self._slide_job is not None:
                try:
                    if self.win is not None:
                        self.win.after_cancel(self._slide_job)
                except (tk.TclError, ValueError):
                    pass
                self._slide_job = None

        def _clear_pages(self, keep=None):
            kept = []
            for item in self._pages:
                if keep is not None and item is keep:
                    kept.append(item)
                    continue
                for part in (item.get("grid"), item.get("title")):
                    try:
                        part.destroy()
                    except (tk.TclError, AttributeError):
                        pass
            self._pages = kept

        def _place_page(self, page, x):
            page["grid"].place(x=int(x), y=0, width=self._stage_w, height=self._stage_h)
            tw = int(self._title_stage.winfo_width())
            if tw <= 1:
                tw = self._stage_w - 64
            page["title"].place(x=int(x * tw / max(1, self._stage_w)), y=0,
                                width=tw, height=28)
            page["x"] = x

        def _show_month(self, year, month, animate=False, direction=1):
            if self.win is None:
                return
            incoming = {
                "grid": self._make_grid(year, month),
                "title": self._make_title(year, month),
                "x": 0,
            }
            if not animate or prefers_reduced_motion() or not self._pages:
                self._cancel_slide()
                self._clear_pages()
                self._pages = [incoming]
                self._title_stage.update_idletasks()
                self._place_page(incoming, 0)
                return
            outgoing = self._pages[-1]
            self._cancel_slide()
            # 打断：丢掉更早的页，从当前偏移继续滑向新的一个月。
            self._clear_pages(keep=outgoing)
            start = outgoing.get("x", 0)
            incoming_start = start + direction * self._stage_w
            self._place_page(incoming, incoming_start)
            self._pages = [outgoing, incoming]
            t0 = time.perf_counter()
            dur = self._SLIDE_MS / 1000.0

            def tick():
                if self.win is None:
                    return
                t = (time.perf_counter() - t0) / dur
                p = ease_out(t)
                if t >= 1:
                    self._place_page(incoming, 0)
                    self._clear_pages(keep=incoming)
                    self._pages = [incoming]
                    self._slide_job = None
                    return
                out_x = start + (-direction * self._stage_w - start) * p
                in_x = incoming_start + (0 - incoming_start) * p
                self._place_page(outgoing, out_x)
                self._place_page(incoming, in_x)
                try:
                    self._slide_job = self.win.after(8, tick)
                except tk.TclError:
                    self._slide_job = None

            tick()

        def _arrow(self, parent, text, delta):
            """月份切换箭头：纯文字标签，不参与焦点，避免出现按钮焦点框（0.1.4）。"""
            lb = tk.Label(parent, text=text, bg=BG, fg=TEXT, font=(self.font[0], 12),
                          width=2, cursor="hand2", takefocus=0)
            lb.bind("<Button-1>", lambda _e: self._shift(delta))
            lb.bind("<Enter>", lambda _e: lb.configure(bg=SAND, fg=MINT_DEEP))
            lb.bind("<Leave>", lambda _e: lb.configure(bg=BG, fg=TEXT))
            return lb

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
            self._show_month(y, m, animate=True, direction=1 if delta > 0 else -1)

        def _pick(self, day):
            try:
                self.entry.delete(0, "end")
                self.entry.insert(0, day.isoformat())
            except tk.TclError:
                pass
            self.close()
            self._notify_pick()

        def _clear(self):
            try:
                self.entry.delete(0, "end")
            except tk.TclError:
                pass
            self.close()
            # 程序化 delete 不会触发 KeyRelease；范围提示必须靠这里刷新（F-7）。
            self._notify_pick()

        def _notify_pick(self):
            if self.on_pick:
                try:
                    self.on_pick()
                except Exception:
                    pass
