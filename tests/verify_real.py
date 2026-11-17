# -*- coding: utf-8 -*-
"""真实数据回归（只读）：对真实项目做预检，并导出一小段范围后逐条对账。

没有任何写回：只在临时目录生成批次，跑完删掉。
找不到真实项目时打印 SKIP 并返回 0（换机器复检不至于失败）。
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))

import config  # noqa: E402
import detect  # noqa: E402
import engine  # noqa: E402
import kbreport  # noqa: E402
import manifest  # noqa: E402

FAILS = []
PASS = 0


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def md_ids(root):
    ids = []
    for base, _d, files in os.walk(root):
        for f in files:
            if not f.endswith(".md"):
                continue
            for line in open(os.path.join(base, f), encoding="utf-8").read().splitlines()[:12]:
                if line.startswith("作品ID:"):
                    ids.append(line.split(":", 1)[1].strip())
                    break
    return ids


def main():
    cfg = config.load()
    st = engine.status(None, cfg)
    if not st.get("project_ok"):
        print("SKIP  本机没有可用的抖音项目目录")
        return 0
    print(f"真实项目：{st['project_dir']}")
    print(f"知识库：{st['kb_dir']}")

    pre = engine.preflight("2026-10-01", "2026-11-17")
    check("预检 ok", pre.get("ok"), str(pre)[:200])
    check("全量条数 ≥ 1000", pre.get("total", 0) >= 1000, str(pre.get("total")))
    check("范围内条数 = 分类型之和",
          pre.get("in_range") == sum((pre.get("by_type") or {}).values()),
          f"{pre.get('in_range')} vs {pre.get('by_type')}")

    rows = engine.load_rows(st["project_dir"])
    snap = kbreport.snapshot_stats(st["project_dir"], st["kb_dir"])
    check("知识库现状：笔记数 = 实际文件数",
          snap["notes"] == sum(1 for b, _d, fs in os.walk(
              os.path.join(st["kb_dir"], "01_AI笔记")) for f in fs if f.endswith(".md")),
          str(snap))
    check("知识库现状：概念数 = 概念节点文件数",
          snap["concepts"] == len([f for f in os.listdir(os.path.join(st["kb_dir"], "05_概念"))
                                   if f.endswith(".md")]), str(snap))
    check("共现关系可复算（>0）", snap["pairs"] > 0, str(snap["pairs"]))
    check("AI 笔记数 = 库内笔记数", snap["ai"] == snap["notes"] or snap["notes"] == 0,
          f"ai={snap['ai']} notes={snap['notes']}")
    expect = [r for r in rows if manifest.in_range(r, "2026-10-01", "2026-11-17")]
    tmp = tempfile.mkdtemp(prefix="dysync-real-")
    try:
        r = engine.export_only(tmp, "2026-10-01", "2026-11-17")
        check("导出 ok", r.get("ok"), str(r)[:200])
        batch = r.get("batch_path", "")
        ids = md_ids(batch)
        check("md 数 = 范围内条数", len(ids) == len(expect), f"{len(ids)} vs {len(expect)}")
        check("作品ID 集合完全一致",
              sorted(ids) == sorted(str(x.get("作品ID")) for x in expect))
        rep = manifest.read_report(batch)
        check("报告明细行数一致", len(rep["items"]) == len(expect))
        check("报告作品ID集合一致",
              sorted(x["作品ID"] for x in rep["items"]) ==
              sorted(str(x.get("作品ID")) for x in expect))
        check("待加工行数一致", len(rep["gaps"]) == r.get("gap_count"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
