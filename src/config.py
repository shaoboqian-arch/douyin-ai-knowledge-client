# -*- coding: utf-8 -*-
"""客户端设置：本机路径、账号。

这些值全部可由「初始化本机环境」写入，也可以直接编辑 settings.json。
这里**不保存也不复制**任何 Cookie —— Cookie 始终留在抖音项目自己的
`Volume/settings.json` 里，客户端只读它是否存在。
条数下限门禁已移除（2026-11-18 裁决）：分发场景无法预知用户收藏量级，
固定下限会误伤小库用户；部分采集的风险由《导出报告》的新增 / 取消差集揭示。
"""
import json
import os

from common import settings_path

DEFAULTS = {
    "project_dir": "",      # TikTokDownloader 工作目录（含 extract_favorites.py 与 .venv）
    "python": "",           # 运行采集脚本的解释器；空 = 自动取 <project>/.venv/Scripts/python.exe
    "kb_dir": "",           # Obsidian 知识库目录；空 = 从 gen_obsidian.py / audit_obsidian.py 读取
    "kb_enabled": True,     # 整理后是否重建 Obsidian 知识库（需本机装 Obsidian 并有库）
    "obsidian_exe": "",     # Obsidian 主程序；空 = 自动检测
    "expect_sec_uid": "",   # 账号硬校验用：必须是这个账号
    "expect_nickname": "",
    "dest": "",             # 默认交付目录
    "frm": "",              # 上次发布时间范围（空 = 全部）
    "to": "",
}

_KEYS = tuple(DEFAULTS)


def load(path=None):
    path = path or settings_path()
    data = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return data
    if not isinstance(raw, dict):
        return data
    for k in _KEYS:
        if k not in raw:
            continue
        if k == "kb_enabled":
            if isinstance(raw[k], bool):
                data[k] = raw[k]
            elif isinstance(raw[k], (int, float)):
                data[k] = bool(raw[k])
            elif isinstance(raw[k], str):
                data[k] = raw[k].strip().lower() not in ("0", "false", "no", "off", "")
        elif isinstance(raw[k], (str, int, float)):
            data[k] = raw[k]
    return data


def save(data, path=None):
    path = path or settings_path()
    payload = {k: data.get(k, DEFAULTS[k]) for k in _KEYS}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def update(**kw):
    data = load()
    for k, v in kw.items():
        if k in DEFAULTS:
            data[k] = v
    save(data)
    return data
