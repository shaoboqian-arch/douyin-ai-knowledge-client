# -*- coding: utf-8 -*-
"""把整理结果写成一批可独立带走的交付目录。

目录结构（与 wx V0.4.3 的「一批一目录 + 清单」同构，分类轴换成本项目自己的 AI 类别）：

    export-<范围>-<时间戳>/
    ├─ 01_AI笔记/<AI类别>/<序号>_<发布日>_<作者>_<标题>.md
    ├─ 02_其他收藏/<...>.md
    ├─ 03_待判定/<...>.md
    ├─ _导出清单.csv        范围内每一条一行
    ├─ _导出报告.csv        每个写出的文件一行（含字节数与状态）
    ├─ _待加工.csv          还需要外部 AI 加工的条目与原因
    └─ _导出说明.txt        给人看的本批说明

**不覆盖**：批次目录必须是新建的空目录；同名文件一律加 ~2 后缀，绝不改写已有文件。
"""
import csv
import datetime as dt
import json
import os
import re
import unicodedata
from collections import Counter

import subcat

AI_YES = "是"
AI_PENDING = "待定"
BAD_CHARS = re.compile(r'[\\/:*?"<>|]')
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | \
           {f"LPT{i}" for i in range(1, 10)}
CATS = ("AI编程与开发", "AI效率办公", "大模型与行业资讯", "AI绘画与图像",
        "其他AI相关", "AI视频与数字人", "科普与学习")

MANIFEST_COLUMNS = ["序号", "类型", "发布日期", "作者", "标题", "收藏夹", "AI相关",
                    "AI类别", "子类别", "子类别依据", "核心内容", "内容介绍", "概念",
                    "作品链接", "作品ID", "输出路径", "状态"]
REPORT_COLUMNS = ["序号", "文件名", "状态", "字节", "来源"]
GAP_COLUMNS = ["序号", "作品ID", "标题", "原因", "建议"]


def clean_name(text, limit=48):
    """净化成 Windows 可用文件名片段。"""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Cn"))
    s = BAD_CHARS.sub("_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s:
        s = "未命名"
    if s.split(".")[0].upper() in RESERVED:
        s = "_" + s
    return s[:limit].strip(" .") or "未命名"


def parse_date(value):
    s = str(value or "").strip()
    if not s:
        return ""
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def in_range(row, frm="", to=""):
    d = parse_date(row.get("发布时间"))
    if not frm and not to:
        return True
    if not d:
        return False
    if frm and d < frm:
        return False
    if to and d > to:
        return False
    return True


def _group_of(row):
    ai = str(row.get("AI相关") or "").strip()
    if ai == AI_YES:
        return "ai"
    if ai in ("", AI_PENDING, "待定") or ai not in ("是", "否"):
        return "pending"
    return "other"


def _folder_of(row, sub=""):
    """三级目录：AI 笔记按「AI类别/子类别」两层分；非 AI 按子类别分。"""
    g = _group_of(row)
    if g == "ai":
        cat = str(row.get("AI类别") or "").strip()
        parts = ["01_AI笔记", clean_name(cat if cat in CATS else "其他AI相关", 30)]
        if sub:
            parts.append(clean_name(sub, 24))
        return os.path.join(*parts)
    if g == "pending":
        return "03_待判定"
    return os.path.join("02_其他收藏", clean_name(sub, 24)) if sub else "02_其他收藏"


def _frontmatter(row, concepts, sub="", extra=None):
    def q(v):
        return str(v or "").replace("\n", " ").strip()

    lines = [
        "---",
        f"标题: {q(row.get('标题/文案'))[:120]}",
        f"作者: {q(row.get('作者'))}",
        f"发布日期: {parse_date(row.get('发布时间'))}",
        f"点赞数: {q(row.get('点赞数'))}",
        f"类型: {q(row.get('类型'))}",
        f"类别: {q(row.get('AI类别'))}",
        f"子类别: {q(sub)}",
        f"核心内容: {q(row.get('核心内容归纳'))}",
        f"作品链接: {q(row.get('作品链接'))}",
        f"作品ID: {q(row.get('作品ID'))}",
        f"收藏夹: {q(row.get('收藏夹'))}",
        f"概念: [{', '.join(concepts)}]",
        "---",
        "",
    ]
    if extra:
        lines.extend(extra)
    return "\n".join(lines)


def _note_body(row, concepts, transcript, intro):
    parts = [f"# {str(row.get('标题/文案') or '（无标题）').strip()[:120]}", ""]
    if intro:
        parts += ["## 内容介绍", "", intro.strip(), ""]
    if concepts:
        parts += ["## 概念", ""] + [f"- {c}" for c in concepts] + [""]
    desc = str(row.get("标题/文案") or "").strip()
    if desc:
        parts += ["## 原文文案", "", desc, ""]
    if transcript:
        parts += ["## 语音转写（节选）", "",
                  transcript.strip()[:1500] + ("…" if len(transcript.strip()) > 1500 else ""), ""]
    parts += ["## 出处", "",
              f"- 作品：{str(row.get('作品链接') or '').strip()}",
              f"- 作者：{str(row.get('作者') or '').strip()}",
              ""]
    return "\n".join(parts)


def _unique_path(path, used):
    if path.lower() not in used:
        used.add(path.lower())
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while f"{stem}~{i}{ext}".lower() in used:
        i += 1
    out = f"{stem}~{i}{ext}"
    used.add(out.lower())
    return out


def build(rows, batch_dir, frm="", to="", transcripts_dir="", concepts_map=None,
          on_item=None, on_gap=None, on_plan=None):
    """写出整批交付。rows 为 rows_merged.json 的列表。"""
    batch_dir = os.path.abspath(batch_dir)
    # 只允许「本工具自己的过程文件」预先存在（日志目录 / 状态文件），
    # 其他任何东西都视为用户数据，拒绝写入。
    if os.path.isdir(batch_dir):
        foreign = [n for n in os.listdir(batch_dir)
                   if n not in ("_日志", "_整理状态.json")]
        if foreign:
            return {"ok": False,
                    "error": f"批次目录已存在且非空，拒绝覆盖：{batch_dir}"}
    os.makedirs(batch_dir, exist_ok=True)
    concepts_map = concepts_map or {}
    selected = [r for r in rows if in_range(r, frm, to)]

    def sort_key(r):
        return (parse_date(r.get("发布时间")) or "0000-00-00",
                str(r.get("作品ID") or ""))

    selected.sort(key=sort_key, reverse=True)
    if on_plan:
        on_plan(len(selected))

    manifest, report, gaps = [], [], []
    stats = {g: {"total": 0, "ok": 0, "gap": 0} for g in ("video", "album", "ai")}
    used_paths = set()
    idx = 0

    for row in selected:
        idx += 1
        seq = f"{idx:03d}"
        kind = "图集" if str(row.get("类型") or "") == "图集" else "视频"
        wid = str(row.get("作品ID") or "")
        concepts = list(concepts_map.get(wid) or [])
        intro = str(row.get("内容介绍") or "").strip()
        transcript = ""
        if transcripts_dir and wid:
            tp = os.path.join(transcripts_dir, f"{wid}.txt")
            if os.path.isfile(tp):
                try:
                    transcript = open(tp, encoding="utf-8", errors="replace").read()
                except OSError:
                    transcript = ""

        # 待加工判定（每一项都要能落到具体文件上，不写笼统的“失败”）
        reasons = []
        ai = str(row.get("AI相关") or "").strip()
        if ai not in ("是", "否"):
            reasons.append("AI 判定未完成")
        else:
            if ai == "是" and not intro:
                reasons.append("缺百字介绍")
            if ai == "是" and not concepts:
                reasons.append("缺概念标引")
            if ai == "是" and kind == "视频" and not transcript:
                reasons.append("缺语音转写")

        cls = subcat.classify(row, transcript) if str(ai) in ("是", "否") else \
            {"子类别": "", "依据": ""}
        sub, sub_hint = cls["子类别"], cls["依据"]
        folder = os.path.join(batch_dir, _folder_of(row, sub))
        os.makedirs(folder, exist_ok=True)
        title = clean_name(row.get("标题/文案"), 44)
        author = clean_name(row.get("作者"), 16)
        date = parse_date(row.get("发布时间")) or "0000-00-00"
        fname = clean_name(f"{seq}_{date}_{kind}_{author}_{title}", 96) + ".md"
        path = _unique_path(os.path.join(folder, fname), used_paths)
        body = _frontmatter(row, concepts, sub) + _note_body(row, concepts, transcript, intro)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        size = os.path.getsize(path)
        rel = os.path.relpath(path, batch_dir).replace("\\", "/")

        status = "已写出" if not reasons else "已写出·待加工"
        manifest.append({
            "序号": seq, "类型": kind, "发布日期": date,
            "作者": row.get("作者", ""), "标题": row.get("标题/文案", ""),
            "收藏夹": row.get("收藏夹", ""), "AI相关": ai,
            "AI类别": row.get("AI类别", ""), "子类别": sub, "子类别依据": sub_hint,
            "核心内容": row.get("核心内容归纳", ""),
            "内容介绍": intro, "概念": " / ".join(concepts),
            "作品链接": row.get("作品链接", ""), "作品ID": wid,
            "输出路径": rel, "状态": status,
        })
        report.append({"序号": seq, "文件名": rel, "状态": status,
                       "字节": size, "来源": f"rows_merged#{wid}"})

        g = _group_of(row)
        bucket = "album" if kind == "图集" else "video"   # 视频/图集互斥
        stats[bucket]["total"] += 1
        if reasons:
            stats[bucket]["gap"] += 1
            gap = {"序号": seq, "作品ID": wid,
                   "标题": str(row.get("标题/文案") or "")[:80],
                   "原因": "、".join(reasons),
                   "建议": "在项目里对该条跑 AI 判定 / 转写 / 介绍 / 概念标引后重新整理"}
            gaps.append(gap)
            if on_gap:
                on_gap(gap)
        else:
            stats[bucket]["ok"] += 1
        # 「其中 · AI 笔记」是上面两类里 AI 相关的子集，单独统计产出，不与前两行相加
        if g == "ai":
            stats["ai"]["total"] += 1
            if not reasons:
                stats["ai"]["ok"] += 1
            else:
                stats["ai"]["gap"] += 1
        if on_item:
            on_item({"group": "album" if kind == "图集" else "video",
                     "ok": not reasons, "seq": seq, "path": rel,
                     "ai": g == "ai"})

    _write_csv(os.path.join(batch_dir, "_导出清单.csv"), MANIFEST_COLUMNS, manifest)
    _write_csv(os.path.join(batch_dir, "_导出报告.csv"), REPORT_COLUMNS, report)
    _write_csv(os.path.join(batch_dir, "_待加工.csv"), GAP_COLUMNS, gaps)
    with open(os.path.join(batch_dir, "_导出说明.txt"), "w", encoding="utf-8") as f:
        f.write(_explain(frm, to, stats, gaps, len(manifest), batch_dir, manifest))

    return {"ok": True, "batch_path": batch_dir, "total": len(manifest),
            "stats": stats, "gaps": gaps, "files": len(report)}


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in columns})


def _explain(frm, to, stats, gaps, total, batch_dir, manifest_rows=None):
    scope = f"{frm or '最早'} ~ {to or '最新'}" if (frm or to) else "全部收藏"
    subs = Counter(r.get("子类别") or "" for r in (manifest_rows or []) if r.get("子类别"))
    lines = [
        f"抖音收藏整理 · 本批交付说明",
        "",
        f"交付目录：{batch_dir}",
        f"生成时间：{dt.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"发布时间范围：{scope}（起止都含当天；留空表示全部）",
        f"本批条目：{total}",
        "",
        "目录含义：",
        "  01_AI笔记/<AI类别>/<子类别>/   AI 相关条目，两级分类",
        "  02_其他收藏/<子类别>/          判定为与 AI 无关的条目，按内容子类别分",
        "  03_待判定/            AI 判定尚未完成的条目",
        "",
        "计数：",
        f"  视频 {stats['video']['total']} 条（已写完 {stats['video']['ok']}）",
        f"  图集 {stats['album']['total']} 条（已写完 {stats['album']['ok']}）",
        f"  其中 AI 笔记 {stats['ai']['total']} 条（已写完 {stats['ai']['ok']}）",
        f"  待加工 {len(gaps)} 条",
        "",
        "子类别分布（前 12）：",
    ]
    for name, n in subs.most_common(12):
        lines.append(f"  {name} {n} 条")
    lines += [
        "",
        "待加工是什么：",
        "  这是本项目需要外部 AI 处理的部分（判定 / 转写 / 百字介绍 / 概念标引），",
        "  不是导出失败。清单在 _待加工.csv，逐条写了缺哪一步。",
        "  补齐后重新点一次「开始整理」，新一轮批次会包含更新后的内容。",
        "",
        "不覆盖：",
        "  每次整理都新建带时间戳的批次目录；本目录内同名文件会被加 ~2 后缀，",
        "  不会改写任何已有文件。",
    ]
    return "\n".join(lines) + "\n"


def read_manifest(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
