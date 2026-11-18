# -*- coding: utf-8 -*-
"""公共常量与路径解析（源码运行 / PyInstaller 冻结两种形态都可用）。"""
import os
import queue
import sys
import threading

VERSION = "0.1.8"          # 唯一版本真源：构建 / 界面 / MCP / 测试都从这里读
APP_NAME = "抖音收藏整理"
MCP_SERVER_NAME = "douyin-fav-sync"
EXE_NAME = "抖音收藏整理.exe"

# 主界面进度表的三个分组（互斥：视频 / 图集 / 两者中 AI 相关的那部分）
GROUPS = (("video", "视频"), ("album", "图集"), ("ai", "其中 · AI 笔记"))

# 阶段与 wx V0.4.3 的「读取 → 导出 → 清单 → 完成」一一对应：
# 校验 → 采集 → 对比 → 重建 → 导出 → 完成
PHASES = (
    ("check", "校验"),
    ("collect", "采集"),
    ("diff", "对比"),
    ("rebuild", "重建"),
    ("export", "导出"),
    ("done", "完成"),
)

def is_frozen():
    return bool(getattr(sys, "frozen", False))


def meipass():
    return getattr(sys, "_MEIPASS", None)


def src_dir():
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """程序所在目录（冻结时 = exe 所在目录；源码时 = src/）。"""
    return os.path.dirname(sys.executable) if is_frozen() else src_dir()


def data_dir():
    """可写的程序数据目录（设置、上次目标文件夹）。"""
    if is_frozen():
        d = app_dir()
    else:
        d = os.path.join(src_dir(), "_data")
    os.makedirs(d, exist_ok=True)
    return d


def prefs_path():
    env = os.environ.get("DYSYNC_PREFS")
    if env:
        return env
    return os.path.join(data_dir(), "prefs.json")


def settings_path():
    # 测试与多实例可用 DYSYNC_SETTINGS 指定另一份设置，避免碰本机真实配置
    env = os.environ.get("DYSYNC_SETTINGS")
    if env:
        return env
    return os.path.join(data_dir(), "settings.json")


def ensure_vendor():
    """源码态把 build/vendor 加进 sys.path（冻结态依赖已打进 exe）。"""
    if is_frozen():
        return False
    v = os.path.join(os.path.dirname(src_dir()), "build", "vendor")
    if os.path.isdir(v) and v not in sys.path:
        sys.path.insert(0, v)
        return True
    return False


def clip_text(text, limit):
    """把多行收成单行；超长时截断并加上省略号。"""
    text = " ".join(str(text or "").split())
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def format_gap_rows(gaps, limit=200, title_width=70, reason_width=40):
    """待加工表行：返回 (显示标题, 显示原因, 详情全文)，只取最近 limit 条。"""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 200
    items = list(gaps or [])[-max(0, limit):]
    prepared = []
    for it in items:
        title = clip_text(str(it.get("标题") or it.get("序号") or ""), 10 ** 9)
        reason = clip_text(str(it.get("原因") or ""), 10 ** 9)
        prepared.append((title, reason, it))
    counts = {}
    for title, _reason, _it in prepared:
        counts[title] = counts.get(title, 0) + 1
    rows = []
    for title, reason, it in prepared:
        display = title
        seq = it.get("序号")
        if title and counts.get(title, 0) > 1 and seq not in (None, ""):
            display = f"{title}（{seq}）"
        parts = [display]
        if reason:
            parts.append(f"缺什么：{reason}")
        link = clip_text(str(it.get("作品链接") or ""), 10 ** 9)
        if link:
            parts.append(f"作品：{link}")
        advice = clip_text(str(it.get("建议") or ""), 10 ** 9)
        if advice:
            parts.append(f"建议：{advice}")
        rows.append((clip_text(display, title_width),
                     clip_text(reason, reason_width), "\n".join(parts)))
    return rows


def gap_heading(n, shown=200):
    """待加工表标题。超过 shown 条时写明界面只列最近 shown 条。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    try:
        shown = int(shown)
    except (TypeError, ValueError):
        shown = 200
    if n > shown:
        return f"待加工 {n:,}（只显示最近 {shown} 条，全集见批次里的《导出报告》）"
    return f"待加工 {n:,}"


def pointer_inside(x, y, width, height):
    """松开时指针是否仍在按钮矩形内（用于取消拖出后的点击）。"""
    try:
        x, y, width, height = float(x), float(y), float(width), float(height)
    except (TypeError, ValueError):
        return False
    return 0 <= x <= width and 0 <= y <= height


def console_is_ours(console_pids, my_pid, my_exe, parent_pid, parent_exe):
    """控制台是否只属于本程序树（自身＋同一 exe 的父引导器）。

    单文件 exe 双击启动：控制台上挂着自己和父引导器（同一 exe）→ 属于我们 → 藏；
    从终端启动：控制台上还挂着终端/shell（exe 路径不同）→ 不属于 → 不藏，
    否则会把用户的终端窗口一起藏掉。
    判定用 exe 路径而不是进程数：onefile 是引导器＋应用双进程，只数个数
    永远数出 2，是「黑窗藏不掉」的根因。
    """
    pids = {p for p in (console_pids or ()) if p}
    if not pids:
        return False
    allowed = {my_pid}
    if (parent_pid and parent_pid not in allowed and parent_exe
            and my_exe
            and os.path.normcase(parent_exe) == os.path.normcase(my_exe)):
        allowed.add(parent_pid)
    return pids <= allowed


class DeferredCall:
    """把同步函数放到后台线程，只把最后一次结果交回 Tk 主线程。

    日期预检与库现状统计都要读全量 rows／转写稿／笔记目录，放在 UI 线程会卡住窗口。
    结果用队列 + after 轮询取回（子线程绝不碰 Tk）；窗口销毁后停止回调。
    """

    def __init__(self, root, fn, on_done, poll_ms=30, with_args=False):
        self.root = root
        self.fn = fn
        self.on_done = on_done
        self.poll_ms = poll_ms
        self.with_args = with_args
        self._q = queue.Queue()
        self._seq = 0
        self._job = None
        self._alive = True

    def run(self, *args, **kwargs):
        if not self._alive:
            return
        self._seq += 1
        seq = self._seq
        threading.Thread(target=self._work, args=(seq, args, kwargs),
                         daemon=True).start()
        self._ensure_poll()

    def _work(self, seq, args, kwargs):
        try:
            result = self.fn(*args, **kwargs)
        except Exception as e:                       # 不让后台异常静默吞掉
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self._q.put((seq, result, args))

    def _ensure_poll(self):
        if self._job is None and self._alive:
            try:
                self._job = self.root.after(self.poll_ms, self._poll)
            except Exception:
                self._job = None

    def _poll(self):
        self._job = None
        latest = None
        meta = ()
        while True:
            try:
                seq, result, args = self._q.get_nowait()
            except queue.Empty:
                break
            if seq == self._seq:                    # 过期结果直接丢弃
                latest, meta = result, args
        if latest is not None and self._alive:
            try:
                if self.with_args:
                    self.on_done(latest, meta)
                else:
                    self.on_done(latest)
            except Exception:
                pass
        elif self._alive:
            self._ensure_poll()

    def destroy(self):
        self._alive = False
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
