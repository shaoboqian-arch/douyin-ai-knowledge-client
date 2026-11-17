# -*- coding: utf-8 -*-
"""导出清单复核：不看清单自己写的数字，从磁盘与源数据反推后逐条对。

用法: python tests/verify_manifest.py [批次目录]
不给批次目录时，用假项目现场生成一批再核（离线）。
"""
import csv
import os
import re
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
    rows = [
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
    ]
    return rows


def md_files(root):
    out = []
    for base, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".md"):
                out.append(os.path.join(base, f))
    return out


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    tmp = ""
    if not target:
        tmp = tempfile.mkdtemp(prefix="dysync-manifest-")
        rows = rows_for_test()
        tdir = os.path.join(tmp, "transcripts")
        os.makedirs(tdir, exist_ok=True)
        open(os.path.join(tdir, "1001.txt"), "w", encoding="utf-8").write("转写稿内容" * 50)
        target = os.path.join(tmp, "batch")
        res = manifest.build(rows, target, "2026-10-01", "2026-11-30",
                             transcripts_dir=tdir,
                             concepts_map={"1001": ["提示词工程"], "1001B": ["提示词工程"]})
        assert res.get("ok"), res
    try:
        listing = manifest.read_manifest(os.path.join(target, "_导出清单.csv"))
        report = manifest.read_manifest(os.path.join(target, "_导出报告.csv"))
        gaps = manifest.read_manifest(os.path.join(target, "_待加工.csv"))
        mds = md_files(target)
        all_files = [os.path.join(b, f) for b, _d, fs in os.walk(target) for f in fs]

        print("== 清单 vs 磁盘 ==")
        check("清单行数 == md 文件数", len(listing) == len(mds),
              f"{len(listing)} vs {len(mds)}")
        check("报告行数 == 清单行数", len(report) == len(listing))
        check("md 全部被清单覆盖", len(mds) == len(
            [r for r in listing if r.get("输出路径")]))

        seqs = [r["序号"] for r in listing]
        check("序号唯一", len(seqs) == len(set(seqs)))
        check("序号连续从 001 起", seqs == [f"{i:03d}" for i in range(1, len(seqs) + 1)],
              str(seqs[:5]))

        missing = [r["输出路径"] for r in listing
                   if not os.path.isfile(os.path.join(target, r["输出路径"]))]
        check("每个输出路径都存在", not missing, str(missing[:3]))

        base = os.path.abspath(target).lower()
        outside = [r["输出路径"] for r in listing
                   if not os.path.abspath(os.path.join(target, r["输出路径"])).lower().startswith(base)]
        check("输出路径不出批次", not outside, str(outside[:3]))

        print("== 报告与字节 ==")
        size_bad = []
        for r in report:
            p = os.path.join(target, r["文件名"])
            if not os.path.isfile(p) or os.path.getsize(p) != int(r["字节"] or -1):
                size_bad.append(r["文件名"])
        check("报告字节数 == 磁盘字节", not size_bad, str(size_bad[:3]))
        status_bad = [r["序号"] for r in report
                      if r["状态"] != next((x["状态"] for x in listing
                                            if x["序号"] == r["序号"]), None)]
        check("报告状态与清单一致", not status_bad, str(status_bad[:3]))
        check("报告无重复文件名",
              len({r["文件名"].lower() for r in report}) == len(report))

        print("== 笔记内容 ==")
        need = ("标题:", "作者:", "发布日期:", "点赞数:", "类别:", "子类别:", "核心内容:",
                "作品链接:", "作品ID:", "概念:")
        bad = []
        id_bad = []
        for r in listing:
            p = os.path.join(target, r["输出路径"])
            t = open(p, encoding="utf-8").read()
            if not t.startswith("---") or any(k not in t.split("---")[1] for k in need):
                bad.append(r["输出路径"])
            if f"作品ID: {r['作品ID']}" not in t:
                id_bad.append(r["输出路径"])
        check("frontmatter 必需字段齐全", not bad, str(bad[:3]))
        check("frontmatter 作品ID 与清单一致", not id_bad, str(id_bad[:3]))
        check("标题不含换行", all("\n" not in r["标题"] for r in listing))

        print("== 子类别 ==")
        sub_bad = [r["序号"] for r in listing
                   if r["AI相关"] in ("是", "否") and not (r.get("子类别") or "").strip()]
        check("每条已判定条目都有子类别", not sub_bad, str(sub_bad[:5]))
        folder_bad = []
        for r in listing:
            if r["AI相关"] not in ("是", "否"):
                continue
            parts = r["输出路径"].split("/")
            if r["AI相关"] == "是":
                if len(parts) < 4 or parts[2] != r["子类别"]:
                    folder_bad.append(r["输出路径"])
            elif len(parts) < 3 or parts[1] != r["子类别"]:
                folder_bad.append(r["输出路径"])
        check("目录层级包含子类别", not folder_bad, str(folder_bad[:3]))
        hint_bad = [r["序号"] for r in listing
                    if r["AI相关"] in ("是", "否")
                    and r.get("子类别") not in ("其他", "其他AI相关")
                    and not (r.get("子类别依据") or "").strip()]
        check("子类别都有命中依据", not hint_bad, str(hint_bad[:3]))
        note_sub = [r["输出路径"] for r in listing
                    if f"子类别: {r.get('子类别')}" not in open(
                        os.path.join(target, r["输出路径"]), encoding="utf-8").read()]
        check("笔记 frontmatter 子类别与清单一致", not note_sub, str(note_sub[:3]))
        txt_all = open(os.path.join(target, "_导出说明.txt"), encoding="utf-8").read()
        check("说明里有子类别分布", "子类别分布" in txt_all)

        print("== 分类与待加工 ==")
        cat_bad = []
        for r in listing:
            path = r["输出路径"]
            if r["AI相关"] == "是":
                ok = path.startswith("01_AI笔记/")
            elif r["AI相关"] == "否":
                ok = path.startswith("02_其他收藏/")
            else:
                ok = path.startswith("03_待判定/")
            if not ok:
                cat_bad.append(path)
        check("目录分类与 AI 相关列一致", not cat_bad, str(cat_bad[:3]))

        listed_gap = [r["序号"] for r in listing if "待加工" in (r["状态"] or "")]
        check("待加工行数与清单一致", len(gaps) == len(listed_gap),
              f"{len(gaps)} vs {len(listed_gap)}")
        reason_bad = []
        for g in gaps:
            row = next((r for r in listing if r["序号"] == g["序号"]), None)
            if not row:
                reason_bad.append(g["序号"])
                continue
            reasons = g["原因"].split("、")
            for reason in reasons:
                if reason == "AI 判定未完成" and row["AI相关"] not in ("", "待定"):
                    reason_bad.append((g["序号"], reason))
                if reason == "缺百字介绍" and row["内容介绍"].strip():
                    reason_bad.append((g["序号"], reason))
                if reason == "缺概念标引" and row["概念"].strip():
                    reason_bad.append((g["序号"], reason))
        check("待加工原因可在清单里复现", not reason_bad, str(reason_bad[:3]))

        print("== 同名不同作品 ==")
        dup = [r for r in listing if r["作品ID"] in ("1001", "1001B")]
        check("同名两条都写出", len(dup) == 2)
        check("同名不同作品文件名不同", len({r["输出路径"] for r in dup}) == 2,
              str([r["输出路径"] for r in dup]))

        print("== 说明文件自洽 ==")
        txt = open(os.path.join(target, "_导出说明.txt"), encoding="utf-8").read()
        v = re.search(r"视频 (\d+) 条", txt)
        a = re.search(r"图集 (\d+) 条", txt)
        check("说明里的视频数与实算一致", v and int(v.group(1)) == sum(
            1 for r in listing if r["类型"] == "视频"), v.group(1) if v else "缺")
        check("说明里的图集数与实算一致", a and int(a.group(1)) == sum(
            1 for r in listing if r["类型"] == "图集"), a.group(1) if a else "缺")

        print("== 不覆盖 ==")
        r2 = manifest.build([], target)
        check("再次写入同目录被拒", not r2.get("ok") and "拒绝覆盖" in r2.get("error", ""))
        check("原有文件数不变", len(md_files(target)) == len(mds))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
