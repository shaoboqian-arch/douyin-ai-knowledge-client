# -*- coding: utf-8 -*-
"""入库报告：把一轮整理的关键结果，做成原项目那套「环节 / 结果」表。

数据全部从本机文件反推，不看日志里的自述：
  · 身份与条数：本轮采集结果
  · 新增 / 取消：raw 与上一版快照的作品 ID 差集
  · 转写 / 介绍 / 概念：新条目在 work/ 与 Obsidian 库里的实际就绪情况
  · 交付物：rows_merged、work/top20.json、知识库笔记与概念节点实算
  · 体检：audit_obsidian.py 的退出码与末行结论
共现关系数由 concepts_merged 的组合数复算（与知识图谱的 225 对一致）。
"""
import datetime as dt
import itertools
import json
import os
import re

from common import VERSION

OK = "ok"
WARN = "warn"
SKIP = "skip"


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def ids_of(rows):
    """兼容两种来源：rows_merged 用「作品ID」，favorites_raw 用 aweme_id。"""
    out = set()
    for r in rows or []:
        aid = r.get("作品ID") or r.get("aweme_id") or r.get("id") or ""
        if aid:
            out.add(str(aid))
    return out


def count_pairs(concepts_map):
    pairs = set()
    for _wid, items in (concepts_map or {}).items():
        uniq = sorted({str(c) for c in (items or []) if str(c).strip()})
        for a, b in itertools.combinations(uniq, 2):
            pairs.add((a, b))
    return len(pairs)


def snapshot(project):
    """采集后、重建前的基线：上一版快照 + 本轮 raw。"""
    work = os.path.join(project, "work")
    raw = _read_json(os.path.join(project, "output", "favorites_raw.json"), [])
    prev = _read_json(os.path.join(work, "prev_rows_merged.json"), None)
    if not isinstance(prev, list) or not prev:
        prev = _read_json(os.path.join(work, "rows_merged.json"), [])
    return {"raw_ids": ids_of(raw), "old_ids": ids_of(prev), "prev_rows": prev}


def _active_concepts(concepts_map, ids):
    out = set()
    for wid in ids:
        out.update(str(c) for c in (concepts_map.get(wid) or []))
    return out


def snapshot_stats(project, kb_dir, concepts_map=None, rows=None):
    """只读现状：收藏 / AI 笔记 / 概念 / 共现。用于设置页与 --cli --status。"""
    try:
        rows = rows if rows is not None else _read_json(
            os.path.join(project, "work", "rows_merged.json"), [])
    except (OSError, ValueError):
        rows = []
    concepts_map = concepts_map if concepts_map is not None else _read_json(
        os.path.join(project, "work", "concepts_merged.json"), {})
    ai = sum(1 for r in rows if str(r.get("AI相关") or "") == "是")
    notes = 0
    if kb_dir and os.path.isdir(kb_dir):
        for _b, _d, fs in os.walk(os.path.join(kb_dir, "01_AI笔记")):
            notes += sum(1 for f in fs if f.endswith(".md"))
    cdir = os.path.join(kb_dir, "05_概念") if kb_dir else ""
    concepts = sum(1 for f in os.listdir(cdir) if f.endswith(".md")) \
        if cdir and os.path.isdir(cdir) else 0
    top20 = _read_json(os.path.join(project, "work", "top20.json"), [])
    return {"total": len(rows), "ai": ai, "notes": notes, "concepts": concepts,
            "pairs": count_pairs(concepts_map), "top20": len(top20)}


def build(project, kb_dir, cfg, collect, ids, rows, prev_rows, concepts_map,
          audit_rc=None, audit_lines=None, kb_enabled=True, mode="sync"):
    """返回 {rows:[{环节,结果,状态}], metrics:{...}}。"""
    new_ids = set(ids.get("new") or [])
    removed_ids = set(ids.get("removed") or [])
    old_ids = set(ids.get("old") or [])

    def row(label, text, state=OK):
        return {"环节": label, "结果": text, "状态": state}

    # 身份与条数
    acct = (collect or {}).get("account") or {}
    total = int((collect or {}).get("total") or len(rows))
    min_count = int(cfg.get("min_count") or 0)
    matched = bool(acct.get("matched"))
    if mode == "retry":
        identity = f"{acct.get('nickname') or '（沿用本轮采集）'}（sec_uid 匹配），采集 {total} 条（续跑，不重新采集）"
        identity_state = OK
    elif matched:
        identity = f"{acct.get('nickname') or '（未取到昵称）'}（sec_uid 匹配），采集 {total} 条"
        if min_count:
            identity += f"（≥{min_count} 达标）"
        identity_state = OK
    else:
        identity = f"{acct.get('nickname') or '未知'}（sec_uid 未匹配），采集 {total} 条"
        identity_state = WARN

    # 新增 / 取消
    new_rows = [r for r in rows if str(r.get("作品ID") or "") in new_ids]
    new_ai = [r for r in new_rows if str(r.get("AI相关") or "") == "是"]
    new_pending = [r for r in new_rows if str(r.get("AI相关") or "") not in ("是", "否")]
    new_other = [r for r in new_rows if str(r.get("AI相关") or "") == "否"]
    cat_count = {}
    for r in new_ai:
        cat = str(r.get("AI类别") or "未分类")
        cat_count[cat] = cat_count.get(cat, 0) + 1
    new_total = len(new_ids)
    if new_total:
        detail = []
        if new_ai:
            detail.append(f"{len(new_ai)} 条 AI 相关（"
                          + "、".join(f"{k} {v}" for k, v in
                                     sorted(cat_count.items(), key=lambda x: -x[1]))
                          + "）")
        if new_other:
            detail.append(f"{len(new_other)} 条非 AI")
        if new_pending:
            detail.append(f"{len(new_pending)} 条待判定")
        new_text = f"{new_total} 条" + ("，其中 " + "，".join(detail) if detail else "")
        missing_rows = new_total - len(new_rows)
        if missing_rows:
            new_text += f"；{missing_rows} 条未进 rows_merged（检查 AI 加工阶段）"
        new_state = WARN if (new_pending or missing_rows) else OK
    else:
        new_text, new_state = "0 条（本轮无新增）", OK

    removed_text = (f"{len(removed_ids)} 条，档案已同步清洗" if removed_ids
                    else "0 条，清洗步骤空跑")

    # 转写 / 介绍 / 概念：只对新 AI 视频/条目算
    tdir = os.path.join(project, "work", "transcripts")
    new_ai_videos = [r for r in new_ai if str(r.get("类型") or "") != "图集"]
    tr_ok = sum(1 for r in new_ai_videos
                if os.path.isfile(os.path.join(tdir, f"{r.get('作品ID')}.txt")))
    if not new_ai_videos:
        tr_text, tr_state = "0 条需要转写", SKIP
    elif tr_ok == len(new_ai_videos):
        tr_text, tr_state = f"{tr_ok}/{len(new_ai_videos)} 就绪，0 失败", OK
    else:
        tr_text = (f"{tr_ok}/{len(new_ai_videos)} 就绪，缺 {len(new_ai_videos) - tr_ok} 条"
                   "（客户端不转写，见 _待加工.csv）")
        tr_state = WARN

    intro_ok = sum(1 for r in new_ai if str(r.get("内容介绍") or "").strip())
    if not new_ai:
        intro_text, intro_state = "0 条需要介绍", SKIP
    elif intro_ok == len(new_ai):
        intro_text, intro_state = f"{intro_ok}/{len(new_ai)} 完成", OK
    else:
        intro_text = f"{intro_ok}/{len(new_ai)} 完成，缺 {len(new_ai) - intro_ok} 条"
        intro_state = WARN

    con_ok = sum(1 for r in new_ai if concepts_map.get(str(r.get("作品ID") or "")))
    new_concepts = sorted(_active_concepts(concepts_map, new_ids)
                          - _active_concepts(concepts_map, old_ids))
    if not new_ai:
        con_text, con_state = "0 条需要标引", SKIP
    else:
        con_text = f"{con_ok}/{len(new_ai)} 完成"
        if new_concepts:
            shown = "、".join(new_concepts[:5])
            con_text += f"，新增 {len(new_concepts)} 个概念「{shown}」"
        else:
            con_text += "，无新增概念"
        con_state = OK if con_ok == len(new_ai) else WARN

    # 交付物实算
    ai_total = sum(1 for r in rows if str(r.get("AI相关") or "") == "是")
    top20 = _read_json(os.path.join(project, "work", "top20.json"), [])
    notes = concepts = pairs = 0
    if kb_enabled and kb_dir and os.path.isdir(kb_dir):
        for _b, _d, fs in os.walk(os.path.join(kb_dir, "01_AI笔记")):
            notes += sum(1 for f in fs if f.endswith(".md"))
        cdir = os.path.join(kb_dir, "05_概念")
        if os.path.isdir(cdir):
            concepts = sum(1 for f in os.listdir(cdir) if f.endswith(".md"))
    pairs = count_pairs(concepts_map)
    if kb_enabled:
        rebuild = (f"Excel（{len(rows)} / AI {ai_total} / TOP20 {len(top20)}）+ "
                   f"Obsidian（{notes} 笔记 + {concepts} 概念 + {pairs} 共现）")
        rebuild_state = OK if (notes and concepts) else WARN
    else:
        rebuild = (f"Excel（{len(rows)} / AI {ai_total} / TOP20 {len(top20)}）；"
                   "Obsidian 未启用（可在设置里打开）")
        rebuild_state = SKIP

    # 体检
    if not kb_enabled:
        audit_text, audit_state = "未启用（跳过知识库体检）", SKIP
    elif audit_rc == 0:
        last = ""
        for line in reversed(audit_lines or []):
            if "全部检查通过" in line or "发现" in line:
                last = line.strip()
                break
        audit_text = last or "全部检查通过"
        audit_state = OK
    else:
        last = ""
        for line in reversed(audit_lines or []):
            if "发现" in line or "问题" in line:
                last = line.strip()
                break
        audit_text = f"未通过（exit {audit_rc}）{('：' + last) if last else ''}"
        audit_state = WARN

    report_rows = [
        row("身份校验", identity, identity_state),
        row("新增收藏", new_text, new_state),
        row("取消收藏", removed_text, OK),
        row("视频转写", tr_text, tr_state),
        row("百字介绍", intro_text, intro_state),
        row("概念标引", con_text, con_state),
        row("重建交付物", rebuild, rebuild_state),
        row("audit 体检", audit_text, audit_state),
    ]
    return {
        "ok": True, "version": VERSION,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "scope": (collect or {}).get("scope") or {},
        "account": {"nickname": acct.get("nickname", ""),
                    "sec_uid_masked": acct.get("sec_uid_masked", "")},
        "rows": report_rows,
        "metrics": {
            "total": len(rows), "ai": ai_total, "pending": sum(
                1 for r in rows if str(r.get("AI相关") or "") not in ("是", "否")),
            "new": new_total, "new_ai": len(new_ai), "new_other": len(new_other),
            "new_pending": len(new_pending), "removed": len(removed_ids),
            "transcripts_ok": tr_ok, "transcripts_need": len(new_ai_videos),
            "intros_ok": intro_ok, "concepts_ok": con_ok,
            "new_concepts": new_concepts,
            "top20": len(top20), "notes": notes, "concepts": concepts,
            "pairs": pairs, "kb_enabled": bool(kb_enabled), "audit_rc": audit_rc,
        },
    }


def render_md(report):
    meta = report.get("scope") or {}
    scope = f"{meta.get('from') or '最早'} ~ {meta.get('to') or '最新'}" if meta else "全部"
    lines = [
        "# 入库报告",
        "",
        f"- 时间：{report.get('generated_at', '')}",
        f"- 账号：{(report.get('account') or {}).get('nickname', '')}",
        f"- 发布时间范围：{scope}",
        f"- 客户端：V{report.get('version', '')}",
        "",
        "| 环节 | 结果 |",
        "|---|---|",
    ]
    for r in report.get("rows") or []:
        icon = {"ok": "✅", "warn": "⚠️", "skip": "➖"}.get(r.get("状态"), "")
        text = " ".join(str(r.get("结果") or "").split()).replace("|", "\\|")
        lines.append(f"| {r.get('环节')} | {icon} {text} |")
    lines += ["", "> ✅ 通过 ｜ ⚠️ 需处理 ｜ ➖ 本轮跳过", ""]
    return "\n".join(lines)


def write(batch_dir, report):
    os.makedirs(batch_dir, exist_ok=True)
    with open(os.path.join(batch_dir, "_入库报告.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(batch_dir, "_入库报告.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(report))
    return os.path.join(batch_dir, "_入库报告.md")


def load(batch_dir):
    return _read_json(os.path.join(batch_dir, "_入库报告.json"), {})


def parse_audit_fail(lines):
    for line in lines or []:
        m = re.search(r"发现\s*(\d+)\s*个问题", line)
        if m:
            return int(m.group(1))
    return None
