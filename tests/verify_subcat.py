# -*- coding: utf-8 -*-
"""子类别复检：规则命中、优先级、兜底、上游覆盖、落盘目录。

用法: python tests/verify_subcat.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))

import manifest  # noqa: E402
import subcat  # noqa: E402

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


AI_CASES = [
    ("GitHub 上 40.9K Star 的开源项目，免费生成提示词",
     "#开源 #免费", "开源项目与免费资源"),
    ("Claude Skills 怎么用：从零搭建你的技能库", "#skill", "Skill 与 Agent 用法"),
    ("10 个必装的 Skill 合集", "#skills #推荐", "Skill 类"),
    ("分享一段 Claude 技术主管的 ai 指令", "#提示词", "提示词与模板"),
    ("三分钟教你用 AI 做海报", "#教程", "教程与实操"),
    ("豆包 vs 元宝 深度测评", "#测评", "工具测评与选型"),
    ("OpenAI 发布会解读", "#行业", "行业资讯与观点"),
    ("大模型的注意力机制到底在算什么", "#原理", "原理与科普"),
    ("靠 AI 接单赚钱的四条路", "#副业", "变现与商业"),
    ("随手记一条没关键词的", "", "其他AI相关"),
]

NON_AI_CASES = [
    ("海贼王最新剧情解说", "#动漫", "影视与动漫"),
    ("周末探店：这家火锅真不错", "#美食", "美食"),
    ("广州新地标开业，客流火爆", "#城市", "旅行与城市"),
    ("从零开始练引体向上", "#健身", "健身运动"),
    ("拼豆日记：附图纸", "#拼豆", "手工与创作"),
    ("银行利息返回了 8 千多", "#理财", "职场与财经"),
    ("今天的日常 vlog", "#生活", "生活记录"),
    ("恋爱技巧：怎么和喜欢的人聊天", "#情感", "情感与成长"),
    ("营养师说蔬菜要这样吃", "#健康", "健康与养生"),
    ("随便拍拍", "", "其他"),
]


def main():
    print("== 分类表自洽 ==")
    for name, subs in (("AI", subcat.AI_SUBS), ("非 AI", subcat.NON_AI_SUBS)):
        check(f"{name} 子类别唯一", len(subs) == len(set(subs)))
        check(f"{name} 子类别无路径分隔符",
              not any(("/" in s or "\\" in s) for s in subs))
        check(f"{name} 子类别可作目录名",
              all(manifest.clean_name(s, 24) == s for s in subs))
    check("AI 兜底为其他AI相关", subcat.AI_SUBS[-1] == "其他AI相关")
    check("非 AI 兜底为其他", subcat.NON_AI_SUBS[-1] == "其他")

    print("== AI 规则 ==")
    for title, tags, want in AI_CASES:
        row = {"AI相关": "是", "标题/文案": title, "话题标签": tags}
        got = subcat.classify(row)
        check(f"{title[:16]}… → {want}", got["子类别"] == want,
              f"got={got['子类别']} hits={got['依据']}")
        if want not in ("其他", "其他AI相关"):
            check(f"  ↑ 有命中依据", bool(got["依据"]), str(got))

    print("== 非 AI 规则 ==")
    for title, tags, want in NON_AI_CASES:
        row = {"AI相关": "否", "标题/文案": title, "话题标签": tags}
        got = subcat.classify(row)
        check(f"{title[:16]}… → {want}", got["子类别"] == want,
              f"got={got['子类别']} hits={got['依据']}")

    print("== 优先级 ==")
    row = {"AI相关": "是", "标题/文案": "这个开源 Skill 怎么用？保姆级教程",
           "话题标签": "#开源 #skill"}
    got = subcat.classify(row)["子类别"]
    check("方法论优先于开源与教程", got == "Skill 与 Agent 用法", got)
    row = {"AI相关": "是", "标题/文案": "免费 GitHub 资源合集推荐", "话题标签": ""}
    got = subcat.classify(row)["子类别"]
    check("资源优先于推荐", got == "开源项目与免费资源", got)

    print("== 上游覆盖 ==")
    row = {"AI相关": "是", "标题/文案": "GitHub 开源", "子类别": "我自己定的类"}
    got = subcat.classify(row)
    check("上游子类别优先", got["子类别"] == "我自己定的类" and got["依据"] == "上游标注")

    print("== 落盘目录 ==")
    tmp = tempfile.mkdtemp(prefix="dysync-sub-")
    try:
        rows = [
            {"标题/文案": "GitHub 开源项目合集", "类型": "视频", "作者": "甲",
             "发布时间": "2026-11-01 10:00:00", "作品ID": "2001", "AI相关": "是",
             "AI类别": "AI编程与开发", "内容介绍": "x", "核心内容归纳": ""},
            {"标题/文案": "周末探店火锅", "类型": "视频", "作者": "乙",
             "发布时间": "2026-11-02 10:00:00", "作品ID": "2002", "AI相关": "否",
             "AI类别": "", "内容介绍": "", "核心内容归纳": ""},
            {"标题/文案": "还没判定的一条", "类型": "视频", "作者": "丙",
             "发布时间": "2026-11-03 10:00:00", "作品ID": "2003", "AI相关": "待定",
             "AI类别": "", "内容介绍": "", "核心内容归纳": ""},
        ]
        batch = os.path.join(tmp, "b")
        res = manifest.build(rows, batch, concepts_map={"2001": ["x"]})
        check("批次生成", res.get("ok"), str(res)[:200])
        paths = [r["输出路径"] for r in manifest.read_report(batch)["items"]]
        check("AI 目录含两级类别", any(p.startswith("01_AI笔记/AI编程与开发/开源项目与免费资源/")
                                      for p in paths), str(paths))
        check("非 AI 目录含子类别", any(p.startswith("02_其他收藏/美食/") for p in paths),
              str(paths))
        check("待判定不套子类别", any(p.startswith("03_待判定/") for p in paths))
        check("文件实际存在", all(os.path.isfile(os.path.join(batch, p)) for p in paths))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
