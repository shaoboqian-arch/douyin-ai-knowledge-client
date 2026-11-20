# -*- coding: utf-8 -*-
"""导出报告复核：只认批次里那份《导出报告.md》，从磁盘反推后逐条对。

用法: python tests/verify_manifest.py [批次目录]
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

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


def rows_for_test():
    return [
        {"标题/文案": "AI 视频一：提示词技巧", "类型": "视频", "作者": "作者甲",
         "发布时间": "2026-11-09 10:00:00", "点赞数": 1200, "作品ID": "1001",
         "作品链接": "https://www.douyin.com/video/1001", "收藏夹": "AI",
         "AI相关": "是", "AI类别": "AI效率办公", "核心内容归纳": "讲提示词",
         "内容介绍": "介绍了提示词写法。", "概念": ""},
        {"标题/文案": "AI 视频一：提示词技巧", "类型": "视频", "作者": "作者甲",
         "发布时间": "2026-11-09 10:00:00", "点赞数": 1200, "作品ID": "1001B",
         "作品链接": "https://www.douyin.com/video/1001B", "收藏夹": "AI",
         "AI相关": "是", "AI类别": "AI效率办公", "核心内容归纳": "同名重复",
         "内容介绍": "同名但不同作品。", "概念": ""},
        {"标题/文案": "AI 图集二：海报配色", "类型": "图集", "作者": "作者乙",
         "发布时间": "2026-11-05 09:00:00", "点赞数": 300, "作品ID": "1002",
         "作品链接": "https://www.douyin.com/note/1002", "收藏夹": "",
         "AI相关": "是", "AI类别": "AI绘画与图像", "核心内容归纳": "讲配色",
         "内容介绍": "", "概念": ""},
        {"标题/文案": "非 AI：生活记录", "类型": "视频", "作者": "作者丙",
         "发布时间": "2026-10-20 20:00:00", "点赞数": 50, "作品ID": "1003",
         "作品链接": "https://www.douyin.com/video/1003", "收藏夹": "",
         "AI相关": "否", "AI类别": "", "核心内容归纳": "", "内容介绍": "", "概念": ""},
        {"标题/文案": "待判定的一条", "类型": "视频", "作者": "作者丁",
         "发布时间": "2026-10-01 08:00:00", "点赞数": 10, "作品ID": "1004",
         "作品链接": "https://www.douyin.com/video/1004", "收藏夹": "",
         "AI相关": "待定", "AI类别": "", "核心内容归纳": "", "内容介绍": "", "概念": ""},
        {"标题/文案": "范围外的一条", "类型": "视频", "作者": "作者戊",
         "发布时间": "2026-01-01 00:00:00", "点赞数": 1, "作品ID": "1005",
         "作品链接": "https://www.douyin.com/video/1005", "收藏夹": "",
         "AI相关": "是", "AI类别": "其他AI相关", "核心内容归纳": "旧",
         "内容介绍": "旧的介绍", "概念": ""},
        {"标题/文案": "有转写缺介绍", "类型": "视频", "作者": "作者己",
         "发布时间": "2026-10-15 10:00:00", "点赞数": 88, "作品ID": "1006",
         "作品链接": "https://www.douyin.com/video/1006", "收藏夹": "",
         "AI相关": "是", "AI类别": "AI编程与开发", "核心内容归纳": "有归纳",
         "内容介绍": "", "概念": ""},
        {"标题/文案": "无语音纯画面", "类型": "视频", "作者": "作者庚",
         "发布时间": "2026-10-12 10:00:00", "点赞数": 66, "作品ID": "1007",
         "作品链接": "https://www.douyin.com/video/1007", "收藏夹": "",
         "AI相关": "是", "AI类别": "AI绘画与图像", "核心内容归纳": "纯画面展示",
         "内容介绍": "", "概念": ""},
        {"标题/文案": "转写下载失败", "类型": "视频", "作者": "作者辛",
         "发布时间": "2026-10-10 10:00:00", "点赞数": 20, "作品ID": "1008",
         "作品链接": "https://www.douyin.com/video/1008", "收藏夹": "",
         "AI相关": "是", "AI类别": "AI效率办公", "核心内容归纳": "有归纳",
         "内容介绍": "已有百字介绍", "概念": ""},
    ]


def md_files(root):
    return [os.path.join(b, f) for b, _d, fs in os.walk(root) for f in fs
            if f.lower().endswith(".md") and f != manifest.REPORT_NAME]


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    tmp = ""
    if not target:
        tmp = tempfile.mkdtemp(prefix="dysync-report-")
        tdir = os.path.join(tmp, "transcripts")
        os.makedirs(tdir, exist_ok=True)
        open(os.path.join(tdir, "1001.txt"), "w", encoding="utf-8").write("转写稿" * 50)
        open(os.path.join(tdir, "1006.txt"), "w", encoding="utf-8").write(
            "这是一段足够长的有效视频语音转写内容，用于验证缺百字介绍判断。")
        open(os.path.join(tdir, "1007.txt"), "w", encoding="utf-8").write("[无有效语音]")
        open(os.path.join(tdir, "1008.txt"), "w", encoding="utf-8").write("[下载失败]")
        target = os.path.join(tmp, "batch")
        res = manifest.build(rows_for_test(), target, "2026-10-01", "2026-11-30",
                             transcripts_dir=tdir,
                             concepts_map={
                                 "1001": ["提示词工程"],
                                 "1001B": ["提示词工程"],
                                 "1006": ["提示词工程"],
                                 "1007": ["提示词工程"],
                                 "1008": ["提示词工程"],
                             })
        assert res.get("ok"), res
    try:
        print("== 报告结构 ==")
        rep = manifest.read_report(target)
        check("报告文件存在", os.path.isfile(os.path.join(target, manifest.REPORT_NAME)))
        check("标题为导出报告", rep["title"] == "导出报告", rep["title"])
        check("元信息含范围", "发布时间范围" in rep["meta"], str(rep["meta"]))
        check("批次只剩下 Markdown 与隐藏状态",
              not any(f.endswith((".csv", "_导出说明.txt")) for f in os.listdir(target)),
              str(os.listdir(target)))

        items = rep["items"]
        mds = md_files(target)
        print("== 明细 vs 磁盘 ==")
        check("明细行数 == 笔记文件数", len(items) == len(mds), f"{len(items)} vs {len(mds)}")
        check("序号唯一", len({r["序号"] for r in items}) == len(items))
        seqs = sorted((r["序号"] for r in items), key=lambda s: int(s) if s.isdigit() else 0)
        check("序号连续从 001 起", seqs == [f"{i:03d}" for i in range(1, len(seqs) + 1)],
              str(seqs[:4]))
        missing = [r["输出路径"] for r in items
                   if not os.path.isfile(os.path.join(target, r["输出路径"]))]
        check("每个文件都存在", not missing, str(missing[:3]))
        base = os.path.abspath(target).lower()
        outside = [r["输出路径"] for r in items
                   if not os.path.abspath(os.path.join(target, r["输出路径"])).lower().startswith(base)]
        check("文件不越出批次目录", not outside, str(outside[:2]))

        print("== 计数与分类 ==")
        video = sum(1 for r in items if r["类型"] == "视频")
        album = sum(1 for r in items if r["类型"] == "图集")
        ai = sum(1 for r in items if r["AI相关"] == "是")
        c = rep["counts"]
        check("视频数一致", c["视频"]["total"] == video, f"{c['视频']} vs {video}")
        check("图集数一致", c["图集"]["total"] == album, f"{c['图集']} vs {album}")
        check("AI 笔记数一致", c["其中 · AI 笔记"]["total"] == ai,
              f"{c['其中 · AI 笔记']} vs {ai}")
        subs = {}
        for r in items:
            if r["子类别"]:
                subs[r["子类别"]] = subs.get(r["子类别"], 0) + 1
        check("子类别分布一致", subs == rep["subs"], f"{subs} vs {rep['subs']}")

        print("== 待加工 ==")
        gap_seq = {g["序号"] for g in rep["gaps"]}
        marked = {r["序号"] for r in items if "待加工" in r["状态"]}
        check("待加工序号集合一致", gap_seq == marked, f"{sorted(gap_seq)} vs {sorted(marked)}")
        check("待加工条数与计数一致",
              c["视频"]["gap"] + c["图集"]["gap"] == len(rep["gaps"]),
              f"{c['视频']['gap']}+{c['图集']['gap']} vs {len(rep['gaps'])}")
        reasons = {g["序号"]: g["原因"] for g in rep["gaps"]}
        reasons_by_id = {g.get("作品ID"): g["原因"] for g in rep["gaps"] if g.get("作品ID")}
        check("图集缺概念被标出且不误报百字介绍",
              "概念标引" in reasons.get("003", "") and "百字介绍" not in reasons.get("003", ""),
              str(reasons))
        check("有有效转写但缺介绍的视频被标百字介绍",
              reasons_by_id.get("1006") == "百字介绍", str(reasons_by_id))
        check("无有效语音且有归纳的视频不误报待加工",
              "1007" not in reasons_by_id, str(reasons_by_id))
        check("下载失败的转写占位被识别为缺语音转写",
              "语音转写" in reasons_by_id.get("1008", ""), str(reasons_by_id))
        md1007 = next((it for it in items if it.get("作品ID") == "1007"), None)
        t1007 = open(os.path.join(target, md1007["输出路径"]), encoding="utf-8").read() if md1007 else ""
        check("无有效语音视频笔记含一句话归纳且不写入无有效语音正文",
              "一句话归纳" in t1007 and "[无有效语音]" not in t1007, t1007[:300])

        print("== 笔记内容 ==")
        need = ("标题:", "作者:", "发布日期:", "类别:", "子类别:", "作品ID:")
        bad, id_bad = [], []
        for r in items:
            t = open(os.path.join(target, r["输出路径"]), encoding="utf-8").read()
            fm = t.split("---")[1] if t.startswith("---") else ""
            if any(k not in fm for k in need):
                bad.append(r["输出路径"])
            if f"作品ID: {r['作品ID']}" not in t:
                id_bad.append(r["输出路径"])
        check("frontmatter 字段齐全", not bad, str(bad[:3]))
        check("作品ID 与明细一致", not id_bad, str(id_bad[:2]))
        hint_bad = []
        for r in items:
            if not r.get("子类别"):
                continue
            t = open(os.path.join(target, r["输出路径"]), encoding="utf-8").read()
            fm = t.split("---")[1] if t.startswith("---") else ""
            if "子类别依据:" not in fm:
                hint_bad.append(r["输出路径"])
        check("有子类别的笔记带规则依据", not hint_bad, str(hint_bad[:3]))

        print("== 目录规则 ==")
        cat_bad = []
        for r in items:
            p = r["输出路径"]
            if r["AI相关"] == "是":
                ok = p.startswith(f"01_AI笔记/{r['AI类别']}/{r['子类别']}/")
            elif r["AI相关"] == "否":
                ok = p.startswith(f"02_其他收藏/{r['子类别']}/")
            else:
                ok = p.startswith("03_待判定/")
            if not ok:
                cat_bad.append(p)
        check("目录与两级分类一致", not cat_bad, str(cat_bad[:3]))

        print("== 同名与不覆盖 ==")
        dup = [r for r in items if r["作品ID"] in ("1001", "1001B")]
        check("同名不同作品都写出", len(dup) == 2)
        check("同名文件名不同", len({r["输出路径"] for r in dup}) == 2)
        before = set(os.listdir(target))
        r2 = manifest.build([], target)
        check("再次写入被拒", not r2.get("ok") and "拒绝覆盖" in r2.get("error", ""))
        check("目录内容未变", set(os.listdir(target)) == before)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
