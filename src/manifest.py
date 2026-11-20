# -*- coding: utf-8 -*-
"""把整理结果写成一批可独立带走的交付目录。

目录结构（与 wx V0.4.3 的「一批一目录 + 清单」同构，分类轴换成本项目自己的 AI 类别）：

    export-<范围>-<时间戳>/
    ├─ 01_AI笔记/<AI类别>/<序号>_<发布日>_<作者>_<标题>.md
    ├─ 02_其他收藏/<...>.md
    ├─ 03_待判定/<...>.md
    ├─ _导出报告.md         本批唯一的说明文档：计数 / 子类别 / 待加工 / 明细 / 入库结果
    └─ _整理状态.json       程序内部状态（隐藏，用于续跑）

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

NO_SPEECH_MARKERS = {"[无有效语音]"}
FAILED_TRANSCRIPT_MARKERS = {"[地址刷新失败]", "[下载失败]", "[音频提取失败]"}
MIN_SPEECH_CHARS = 15


def transcript_state(text):
    """判定转写稿状态：missing / no_speech / valid。

    · 失败标记（地址刷新/下载/音频提取失败）或空文本视为 missing（缺语音转写）
    · `[无有效语音]` 或有效字数极少的无口播字幕视为 no_speech（无需语音转写/百字介绍）
    """
    s = str(text or "").strip()
    if not s or s in FAILED_TRANSCRIPT_MARKERS:
        return "missing"
    if s in NO_SPEECH_MARKERS:
        return "no_speech"
    eff = sum(1 for ch in s if ch.isalnum())
    return "no_speech" if eff < MIN_SPEECH_CHARS else "valid"


def gap_reasons(row, kind, concepts, transcript=""):
    """返回一条收藏的待加工原因列表（供 manifest 与 engine.preflight 共用）。"""
    ai = str(row.get("AI相关") or "").strip()
    if ai not in ("是", "否"):
        return ["AI 判定未完成"]
    if ai != "是":
        return []
    intro = str(row.get("内容介绍") or "").strip()
    core = str(row.get("核心内容归纳") or "").strip()
    tstate = transcript_state(transcript) if kind != "图集" else "no_speech"
    reasons = []
    if kind != "图集" and tstate == "missing":
        reasons.append("语音转写")
    if kind != "图集" and tstate in ("valid", "missing"):
        if not intro:
            reasons.append("百字介绍")
    else:
        if not intro and not core:
            reasons.append("内容归纳")
    if not concepts:
        reasons.append("概念标引")
    return reasons



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


def _frontmatter(row, concepts, sub="", sub_hint="", extra=None):
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
    ]
    # 命中词是确定性规则的证据：写进笔记，才能逐条复核「为什么归到这个子类别」。
    if sub_hint:
        lines.append(f"子类别依据: {q(sub_hint)}")
    lines += [
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
    core = str(row.get("核心内容归纳") or "").strip()
    if core:
        parts += [f"> **一句话归纳**：{core}", ""]
    if intro:
        parts += ["## 内容介绍", "", intro.strip(), ""]
    if concepts:
        parts += ["## 概念", ""] + [f"- {c}" for c in concepts] + [""]
    desc = str(row.get("标题/文案") or "").strip()
    if desc:
        parts += ["## 原文文案", "", desc, ""]
    if transcript_state(transcript) == "valid":
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
        ai = str(row.get("AI相关") or "").strip()
        reasons = gap_reasons(row, kind, concepts, transcript)

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
        body = _frontmatter(row, concepts, sub, sub_hint) + _note_body(row, concepts, transcript, intro)
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
                   "作品链接": str(row.get("作品链接") or "").strip(),
                   "原因": "、".join(reasons),
                   "建议": "在项目里对该条跑 AI 判定 / 转写 / 介绍 / 概念标引，"
                           "补齐后点「刷新数据」核对状态，或点「导出文件夹」写出新批次"}
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

    _write_report_md(batch_dir, frm, to, stats, gaps, manifest, report)

    return {"ok": True, "batch_path": batch_dir, "total": len(manifest),
            "stats": stats, "gaps": gaps, "files": len(report)}


REPORT_NAME = "_导出报告.md"


def _md(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _link(text, path):
    t = str(text or "").replace("[", "\\[").replace("]", "\\]").replace("\n", " ").strip()
    return f"[{t[:60]}](<{path}>)" if path else t


def _order_index(value, seq):
    try:
        return seq.index(value)
    except ValueError:
        return len(seq)


def _hierarchy(items):
    """按「AI笔记 → 其他收藏 → 待判定」、类别与子类别词表顺序分组。"""
    cat_order = list(CATS)
    ai_sub = list(subcat.AI_SUBS)
    non_sub = list(subcat.NON_AI_SUBS)
    groups = {}
    for r in items:
        if r.get("AI相关") == "是":
            key = ("AI笔记", r.get("AI类别") or "其他AI相关", r.get("子类别") or "")
        elif r.get("AI相关") == "否":
            key = ("其他收藏", "", r.get("子类别") or "")
        else:
            key = ("待判定", "", "")
        groups.setdefault(key, []).append(r)

    def sort_key(k):
        kind, cat, sub = k
        kind_rank = {"AI笔记": 0, "其他收藏": 1, "待判定": 2}.get(kind, 9)
        cat_rank = _order_index(cat, cat_order) if kind == "AI笔记" else 0
        sub_rank = _order_index(sub, ai_sub if kind == "AI笔记" else non_sub)
        return (kind_rank, cat_rank, cat, sub_rank, sub)

    return [(k, groups[k]) for k in sorted(groups, key=sort_key)]


def _item_line(r):
    return (f"- `{r.get('序号')}` · {r.get('发布日期','')} · {r.get('类型','')} · "
            f"{_md(r.get('作者',''))} · {_link(r.get('标题',''), r.get('输出路径',''))} · "
            f"{_md(r.get('状态',''))} <!-- id:{r.get('作品ID','')} -->")


def _write_report_md(batch_dir, frm, to, stats, gaps, items, files):
    scope = f"{frm or '最早'} ~ {to or '最新'}" if (frm or to) else "全部收藏"
    ordered = _hierarchy(items)
    lines = [
        "# 导出报告",
        "",
        f"**生成时间**：{dt.datetime.now():%Y-%m-%d %H:%M:%S}　　"
        f"**发布时间范围**：{scope}",
        "",
        f"**本批条目**：{len(items)}　　**交付目录**：`{batch_dir}`",
        "",
        "## 概览",
        "",
        "| 类别 | 总数 | 已写出 | 待加工 |",
        "|---|---:|---:|---:|",
        f"| 视频 | {stats['video']['total']} | {stats['video']['ok']} | {stats['video']['gap']} |",
        f"| 图集 | {stats['album']['total']} | {stats['album']['ok']} | {stats['album']['gap']} |",
        f"| 其中 · AI 笔记 | {stats['ai']['total']} | {stats['ai']['ok']} | {stats['ai']['gap']} |",
        "",
        "## 子类别分布",
        "",
    ]

    # 层级树：AI 笔记（类别 → 子类别）/ 其他收藏（子类别）/ 待判定
    for kind in ("AI笔记", "其他收藏", "待判定"):
        rows = [(k, v) for k, v in ordered if k[0] == kind]
        total = sum(len(v) for _k, v in rows)
        if not total:
            continue
        label = {"AI笔记": "AI 笔记", "其他收藏": "其他收藏", "待判定": "待判定"}[kind]
        lines.append(f"- **{label}**（{total}）")
        if kind == "AI笔记":
            cats = {}
            for (k, v) in rows:
                cats.setdefault(k[1], []).append((k, v))
            for cat in sorted(cats, key=lambda c: _order_index(c, list(CATS))):
                cat_total = sum(len(v) for _k, v in cats[cat])
                lines.append(f"  - {cat}（{cat_total}）")
                subs = sorted(cats[cat], key=lambda kv: _order_index(kv[0][2], list(subcat.AI_SUBS)))
                for (k, v) in subs:
                    if k[2]:
                        lines.append(f"    - {k[2]}（{len(v)}）")
        elif kind == "其他收藏":
            for (k, v) in sorted(rows, key=lambda kv: _order_index(kv[0][2], list(subcat.NON_AI_SUBS))):
                if k[2]:
                    lines.append(f"  - {k[2]}（{len(v)}）")
    lines.append("")

    lines += [f"## 待加工（{len(gaps)}）", ""]
    if gaps:
        for g in gaps:
            lines.append(f"- **{g.get('序号','')}** {_md(str(g.get('标题') or '（无标题）')[:80])}")
            lines.append(f"  - 缺：{_md(g.get('原因',''))}")
    else:
        lines.append("本批没有待加工条目。")

    lines += ["", "## 明细", ""]
    for kind in ("AI笔记", "其他收藏", "待判定"):
        block = [(k, v) for k, v in ordered if k[0] == kind]
        if not block:
            continue
        if kind == "AI笔记":
            cats = {}
            for (k, v) in block:
                cats.setdefault(k[1], []).append((k, v))
            for cat in sorted(cats, key=lambda c: _order_index(c, list(CATS))):
                cat_rows = cats[cat]
                cat_total = sum(len(v) for _k, v in cat_rows)
                lines += [f"### AI 笔记 · {cat}（{cat_total}）", ""]
                for (k, v) in sorted(cat_rows, key=lambda kv: _order_index(kv[0][2], list(subcat.AI_SUBS))):
                    if k[2]:
                        lines += [f"#### {k[2]}（{len(v)}）", ""]
                    for r in v:
                        lines.append(_item_line(r))
                    if k[2]:
                        lines.append("")
        elif kind == "其他收藏":
            for (k, v) in sorted(block, key=lambda kv: _order_index(kv[0][2], list(subcat.NON_AI_SUBS))):
                lines += [f"### 其他收藏 · {k[2]}（{len(v)}）", ""]
                for r in v:
                    lines.append(_item_line(r))
                lines.append("")
        else:
            rows = block[0][1]
            lines += [f"### 待判定（{len(rows)}）", ""]
            for r in rows:
                lines.append(_item_line(r))
            lines.append("")

    lines += [
        "## 说明",
        "",
        "- 目录：`01_AI笔记/<AI类别>/<子类别>/`、`02_其他收藏/<子类别>/`、`03_待判定/`",
        "- 每条笔记的 frontmatter 含「子类别」与「子类别依据」（规则命中词），可逐条复核",
        "- 待加工：缺 AI 判定 / 转写 / 百字介绍 / 概念标引的条目，补齐后点「刷新数据」核对状态，或点「导出文件夹」写出新批次",
        "- 每次同步都新建带时间戳的批次目录；同名文件加 `~2` 后缀，不改写已有文件",
        "- `_整理状态.json` 是程序内部状态（已隐藏），用于续跑与入库结果，不需要手工看",
        "",
    ]
    with open(os.path.join(batch_dir, REPORT_NAME), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines))


def _split_row(line):
    """按未转义的 | 切分，标题里的 \\| 还原成 |。"""
    cells, buf, esc = [], [], False
    for ch in line.strip().strip("|"):
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _table(section):
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if not cells or all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows


_ITEM_RX = __import__("re").compile(
    r"^- `(?P<seq>\d+)` · (?P<date>[^·]+) · (?P<type>视频|图集) · (?P<author>.*?) · "
    r"\[(?P<title>.*)\]\(<(?P<path>.*)>\) · (?P<status>.+?)"
    r"(?: <!-- id:(?P<wid>[0-9A-Za-z_]+) -->)?$")
_H_AI = __import__("re").compile(r"^### AI 笔记 · (.+?)（(\d+)）$")
_H_SUB = __import__("re").compile(r"^#### (.+?)（(\d+)）$")
_H_OTHER = __import__("re").compile(r"^### 其他收藏 · (.+?)（(\d+)）$")
_H_PENDING = __import__("re").compile(r"^### 待判定（(\d+)）$")


def read_report(batch_dir):
    """读回《导出报告》的结构化内容，供复检使用。"""
    path = os.path.join(batch_dir, REPORT_NAME)
    text = open(path, encoding="utf-8").read()
    meta = {}
    for line in text.splitlines():
        for key in ("生成时间", "发布时间范围", "本批条目"):
            if f"**{key}**：" in line:
                meta[key] = line.split(f"**{key}**：", 1)[1].split("　")[0].strip()

    counts = {}
    for row in _table(_section(text, "概览"))[1:]:
        if len(row) >= 4:
            counts[row[0]] = {"total": int(row[1]), "ok": int(row[2]), "gap": int(row[3])}

    subs, kind = {}, ""
    for line in _section(text, "子类别分布").splitlines():
        if line.startswith("- **AI 笔记**"):
            kind = "ai"
        elif line.startswith("- **其他收藏**"):
            kind = "other"
        elif line.startswith("- **待判定**"):
            kind = "pending"
        elif line.startswith("    - ") and kind == "ai":
            m = __import__("re").match(r"^    - (.+?)（(\d+)）$", line)
            if m:
                subs[m.group(1)] = subs.get(m.group(1), 0) + int(m.group(2))
        elif line.startswith("  - ") and kind == "other":
            m = __import__("re").match(r"^  - (.+?)（(\d+)）$", line)
            if m:
                subs[m.group(1)] = subs.get(m.group(1), 0) + int(m.group(2))

    gaps, gap_lines = [], _section(text, "待加工").splitlines()
    for i, line in enumerate(gap_lines):
        if line.startswith("- **"):
            body = line[4:]
            seq, _, title = body.partition("** ")
            reason = ""
            if i + 1 < len(gap_lines) and gap_lines[i + 1].strip().startswith("- 缺："):
                reason = gap_lines[i + 1].split("缺：", 1)[1].strip()
            gaps.append({"序号": seq.strip(), "标题": title.strip(), "原因": reason})

    items = []
    ai_flag, cat, sub = "待定", "", ""
    for line in _section(text, "明细").splitlines():
        if line.startswith("### "):
            m = _H_AI.match(line)
            if m:
                ai_flag, cat, sub = "是", m.group(1), ""
                continue
            m = _H_OTHER.match(line)
            if m:
                ai_flag, cat, sub = "否", "", m.group(1)
                continue
            if _H_PENDING.match(line):
                ai_flag, cat, sub = "待定", "", ""
            continue
        if line.startswith("#### "):
            m = _H_SUB.match(line)
            if m:
                sub = m.group(1)
            continue
        m = _ITEM_RX.match(line)
        if m:
            items.append({"序号": m.group("seq"), "发布日期": m.group("date"),
                          "类型": m.group("type"), "作者": m.group("author"),
                          "标题": m.group("title"), "AI相关": ai_flag,
                          "AI类别": cat, "子类别": sub,
                          "作品ID": m.group("wid") or "", "状态": m.group("status"),
                          "输出路径": m.group("path")})

    by_seq = {it["序号"]: it for it in items}
    for g in gaps:
        it = by_seq.get(g.get("序号"))
        if it and it.get("作品ID"):
            g["作品ID"] = it["作品ID"]

    return {"title": "导出报告", "meta": meta, "counts": counts, "subs": subs,
            "gaps": gaps, "items": items}


def _section(text, name):
    marker = f"## {name}"
    start = text.find(marker)
    if start < 0:
        return ""
    rest = text[start + len(marker):]
    nxt = rest.find("\n## ")
    return rest[:nxt] if nxt >= 0 else rest
