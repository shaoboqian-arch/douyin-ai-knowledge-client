# -*- coding: utf-8 -*-
"""本机环境探测：抖音项目目录、解释器、Cookie 是否存在、知识库目录。

全部只读。Cookie 只判断「有没有、多长」，绝不回传内容。
"""
import glob
import json
import os
import re

MARKER = "extract_favorites.py"


def _norm(p):
    return os.path.normpath(p) if p else ""


def is_project_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, MARKER))


def candidate_project_dirs(extra=None):
    """按可信度排序的项目目录候选（去重、只保留真实存在的）。"""
    home = os.path.expanduser("~")
    pats = [
        os.path.join(home, ".zcode", "workspace", "*", "TikTokDownloader"),
        os.path.join(home, "zcode", "workspace", "*", "TikTokDownloader"),
        os.path.join(home, "Desktop", "TikTokDownloader"),
        os.path.join(home, "Documents", "TikTokDownloader"),
        r"G:\douyin\TikTokDownloader",
    ]
    found = []
    for p in [extra] if extra else []:
        if is_project_dir(p):
            found.append(_norm(p))
    for pat in pats:
        for p in sorted(glob.glob(pat)):
            if is_project_dir(p):
                found.append(_norm(p))
    out = []
    for p in found:
        if p not in out:
            out.append(p)
    return out


def venv_python(project_dir):
    """项目自带解释器；不存在时返回空串（不猜系统 Python）。"""
    for rel in (os.path.join(".venv", "Scripts", "python.exe"),
                os.path.join(".venv", "bin", "python")):
        p = os.path.join(project_dir, rel)
        if os.path.isfile(p):
            return p
    return ""


def resolve_python(project_dir, configured=""):
    if configured and os.path.isfile(configured):
        return configured
    return venv_python(project_dir)


def read_project_settings(project_dir):
    """读抖音项目的 Volume/settings.json；返回脱敏摘要。"""
    path = os.path.join(project_dir, "Volume", "settings.json")
    out = {"path": path, "exists": False, "has_cookie": False,
           "cookie_len": 0, "download": None, "mtime": 0, "error": ""}
    if not os.path.isfile(path):
        out["error"] = "找不到 Volume/settings.json"
        return out
    out["exists"] = True
    out["mtime"] = int(os.path.getmtime(path))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        out["error"] = f"读取失败：{e}"
        return out
    cookie = data.get("cookie") or ""
    out["has_cookie"] = isinstance(cookie, str) and len(cookie.strip()) > 0
    out["cookie_len"] = len(cookie) if isinstance(cookie, str) else 0
    out["download"] = data.get("download")
    return out


def detect_kb_dir(project_dir):
    """知识库目录以项目脚本里的字面量为准（改库只改脚本，客户端跟着走）。"""
    for name in ("gen_obsidian.py", "audit_obsidian.py"):
        path = os.path.join(project_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r'KB\s*=\s*Path\(r"([^"]+)"\)', text)
        if m:
            return _norm(m.group(1))
        v = re.search(r'VAULT\s*=\s*Path\(r"([^"]+)"\)', text)
        k = re.search(r'KB\s*=\s*VAULT\s*/\s*"([^"]+)"', text)
        if v and k:
            return _norm(os.path.join(v.group(1), k.group(1)))
    return ""


def kb_ready(kb_dir):
    if not kb_dir or not os.path.isdir(kb_dir):
        return False, "知识库目录不存在"
    need = "00_入口.md"
    if not os.path.isfile(os.path.join(kb_dir, need)):
        return False, f"知识库缺少 {need}"
    return True, ""


def mask_sec_uid(sec):
    """界面只显示首尾，完整值留在设置里。"""
    if not sec:
        return ""
    if len(sec) <= 14:
        return sec
    return f"{sec[:10]}…{sec[-4:]}"


# ---------------------------------------------------------------- Obsidian
def obsidian_config_path():
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "obsidian", "obsidian.json")


def find_obsidian(configured=""):
    """找 Obsidian 主程序：配置 → 注册表 → 常见安装位置。只读。"""
    if configured and os.path.isfile(configured):
        return _norm(configured)
    cands = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Obsidian", "Obsidian.exe"),
    ]
    for p in cands:
        if p and os.path.isfile(p):
            return _norm(p)
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for sub in (r"Software\Classes\obsidian\shell\open\command",
                        r"Software\Classes\obsidian\shell\open\command"):
                try:
                    with winreg.OpenKey(root, sub) as k:
                        cmd = winreg.QueryValue(k, None) or ""
                    m = re.match(r'\s*"([^"]+)"', cmd) or re.match(r"\s*(\S+\.exe)", cmd)
                    if m and os.path.isfile(m.group(1)):
                        return _norm(m.group(1))
                except OSError:
                    continue
    except ImportError:
        pass
    return ""


def obsidian_vaults(config_path=""):
    """读 Obsidian 的库清单（%APPDATA%\\obsidian\\obsidian.json）。只读。"""
    path = config_path or obsidian_config_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for vid, item in (data.get("vaults") or {}).items():
        p = _norm((item or {}).get("path", ""))
        if p:
            out.append({"id": vid, "path": p, "name": os.path.basename(p.rstrip("\\/")),
                        "open": bool((item or {}).get("open"))})
    out.sort(key=lambda x: (not x["open"], x["name"]))
    return out


def obsidian_info(configured="", config_path=""):
    exe = find_obsidian(configured)
    vaults = obsidian_vaults(config_path)
    return {"installed": bool(exe), "exe": exe, "vaults": vaults,
            "config": config_path or obsidian_config_path(),
            "message": "" if exe else "未检测到 Obsidian（写入 Markdown 仍可进行，但不会自动打开）"}


def open_in_obsidian(kb_dir):
    """用 obsidian:// 打开指定库；失败时返回 False，不抛异常。"""
    from urllib.parse import quote
    try:
        os.startfile(f"obsidian://open?path={quote(os.path.abspath(kb_dir))}")
        return True
    except OSError:
        return False
