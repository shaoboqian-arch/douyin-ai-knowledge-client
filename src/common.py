# -*- coding: utf-8 -*-
"""公共常量与路径解析（源码运行 / PyInstaller 冻结两种形态都可用）。"""
import os
import sys

VERSION = "0.1.0"          # 唯一版本真源：构建 / 界面 / MCP / 测试都从这里读
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

DEFAULT_MIN_COUNT = 1700   # 账号硬校验的条数量级下限（可在设置里改）


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
