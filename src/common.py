# -*- coding: utf-8 -*-
"""公共常量与路径解析（源码运行 / PyInstaller 冻结两种形态都可用）。"""
import os
import sys

VERSION = "0.1.3"          # 唯一版本真源：构建 / 界面 / MCP / 测试都从这里读
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

DEFAULT_MIN_COUNT = 1000   # 账号硬校验的条数量级下限（可在设置里改）


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
        full = display if not reason else (display + "\n" + reason)
        rows.append((clip_text(display, title_width),
                     clip_text(reason, reason_width), full))
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
