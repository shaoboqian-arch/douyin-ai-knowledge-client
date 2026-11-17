# -*- coding: utf-8 -*-
"""公开面自检：源码 / 文档 / 构建脚本里不能出现本机个人字面量。

本机敏感词名单在 tests/public_safe.local.txt（不进 Git），
缺文件或名单为空即判不通过 —— 没有名单的「通过」没有意义。

用法: python tests/verify_public_safe.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
LIST = os.path.join(HERE, "public_safe.local.txt")

SKIP_DIRS = {".git", "__pycache__", "vendor", "pyi-dist", "pyi-work", "dist",
             "验证输出", "整理输出", "src/_data", "build"}
SKIP_EXT = {".pyc", ".exe", ".zip", ".ico", ".png", ".jpg", ".db", ".log"}


def load_needles():
    if not os.path.isfile(LIST):
        return []
    out = []
    with open(LIST, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def iter_files():
    for base, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                   and os.path.relpath(os.path.join(base, d), APP).replace("\\", "/")
                   not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, APP).replace("\\", "/")
            if rel.startswith(("验证输出/", "整理输出/", "dist/", "build/", "src/_data/")):
                continue
            yield path, rel


def main():
    needles = load_needles()
    if not needles:
        print(f"FAIL  敏感词名单为空或不存在：{LIST}")
        print("      先复制 tests/public_safe.local.example.txt 再按本机情况填写")
        return 1

    hits = []
    scanned = 0
    for path, rel in iter_files():
        if os.path.basename(path) == os.path.basename(LIST):
            continue
        try:
            text = open(path, encoding="utf-8", errors="strict").read()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        low = text.lower()
        for n in needles:
            if n.lower() in low:
                for i, line in enumerate(text.splitlines(), 1):
                    if n.lower() in line.lower():
                        hits.append((rel, i, n))
                        break

    print(f"扫描文件 {scanned} 个 · 敏感词 {len(needles)} 条")
    if hits:
        print(f"FAIL  命中 {len(hits)} 处：")
        for rel, line, needle in hits[:20]:
            print(f"      {rel}:{line}  含「{needle}」")
        return 1
    print("PASS  源码与文档中没有本机个人字面量")
    return 0


if __name__ == "__main__":
    sys.exit(main())
