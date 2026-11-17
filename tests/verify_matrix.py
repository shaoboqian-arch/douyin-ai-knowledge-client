# -*- coding: utf-8 -*-
"""矩阵复检：解析、文件名净化、范围过滤、引擎门禁、续跑。

全部离线：用 tests/_fixture.py 的假项目，不碰真实抖音数据与知识库。
用法: python tests/verify_matrix.py
"""
import datetime as dt
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402
import config  # noqa: E402
import engine  # noqa: E402
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


def md_files(root):
    out = []
    for base, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(base, f))
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="dysync-matrix-")
    os.environ["DYSYNC_SETTINGS"] = os.path.join(tmp, "settings.json")
    try:
        print("== 日期范围解析 ==")
        check("空范围 = 全部", engine.parse_range("", "") == (True, "", "", ""))
        ok, _a, _b, err = engine.parse_range("2026-11-01", "")
        check("只填一端被拒", not ok and "都填" in err)
        ok, _a, _b, err = engine.parse_range("2026-13-01", "2026-11-02")
        check("非法日期被拒", not ok)
        ok, _a, _b, err = engine.parse_range("2026-11-05", "2026-11-01")
        check("倒序被拒", not ok and "早于" in err)
        check("正常范围通过", engine.parse_range("2026-11-01", "2026-11-05")[0])

        print("== 文件名净化 ==")
        raw = 'a/b\\c:d*e?f"g<h>i|j\u200bk\x01l'
        clean = manifest.clean_name(raw)
        check("非法字符被替换", not any(ch in clean for ch in '\\/:*?"<>|'), clean)
        check("零宽与控制字符被剔除", "\u200b" not in clean and "\x01" not in clean, clean)
        check("保留名加前缀", manifest.clean_name("CON").startswith("_"))
        check("长度受限", len(manifest.clean_name("字" * 200, 20)) <= 20)
        check("空名有兜底", manifest.clean_name("") == "未命名")

        print("== 范围边界（起止都含当天）==")
        row = {"发布时间": "2026-11-05 23:59:59"}
        check("起点当天包含", manifest.in_range(row, "2026-11-05", "2026-11-05"))
        check("终点之后排除", not manifest.in_range(row, "2026-11-01", "2026-11-04"))
        check("空范围包含", manifest.in_range(row, "", ""))

        print("== 只导出（真实流程的离线版）==")
        kb = _fixture.make_kb(tmp)
        project, rows_path = _fixture.make_project(tmp)
        _fixture.configure(tmp, project, kb)
        cfg = config.load()
        check("假项目被识别为就绪", engine.status(None, cfg)["ready"],
              str(engine.status(None, cfg).get("missing")))

        dest = os.path.join(tmp, "out")
        r1 = engine.export_only(dest, "2026-10-01", "2026-11-30")
        check("只导出成功", r1.get("ok"), str(r1)[:300])
        b1 = r1.get("batch_path", "")
        check("批次目录存在", os.path.isdir(b1), b1)
        check("清单 4 行（范围外 1 条被排除）", len(manifest.read_manifest(
            os.path.join(b1, "_导出清单.csv"))) == 4)
        check("写出 4 个 md", len(md_files(b1)) == 4, str(len(md_files(b1))))
        check("视频 3 / 图集 1", r1["stats"]["video"]["total"] == 3
              and r1["stats"]["album"]["total"] == 1, str(r1["stats"]))
        check("AI 笔记 2 条", r1["stats"]["ai"]["total"] == 2)
        check("待加工 2 条", r1["gap_count"] == 2, str(r1["gaps"]))
        check("非 AI 进 02_其他收藏", os.path.isdir(os.path.join(b1, "02_其他收藏")))
        check("待判定进 03_待判定", os.path.isdir(os.path.join(b1, "03_待判定")))
        note = open(md_files(b1)[0], encoding="utf-8").read()
        check("笔记带 frontmatter 必需字段",
              all(k in note for k in ("标题:", "作者:", "发布日期:", "作品ID:", "概念:")))

        before = sorted(os.listdir(b1))
        r2 = engine.export_only(dest, "2026-10-01", "2026-11-30")
        check("第二次导出是新批次", r2.get("batch_path") and r2["batch_path"] != b1)
        check("旧批次文件未被改写", sorted(os.listdir(b1)) == before)

        print("== 完整整理：账号与条数门禁 ==")
        os.environ["FAKE_SEC"] = _fixture.SEC
        os.environ["FAKE_COUNT"] = "5"
        os.environ["FAKE_NEW"] = "1"
        os.environ["FAKE_AUDIT_RC"] = "0"
        r3 = engine.sync(os.path.join(tmp, "out2"), "2026-10-01", "2026-11-30")
        check("整理成功", r3.get("ok"), str(r3)[:300])
        check("新增数解析正确", r3.get("new_count") == 1, str(r3.get("new_count")))
        check("状态文件 stage=done", engine.read_state(r3["batch_path"]).get("stage") == "done")
        check("状态里不含 Cookie", "cookie" not in open(
            os.path.join(r3["batch_path"], engine.STATE_NAME), encoding="utf-8").read().lower())

        os.environ["FAKE_SEC"] = "OTHER-ACCOUNT"
        r4 = engine.sync(os.path.join(tmp, "out3"))
        check("账号不符被拒", not r4.get("ok") and "账号不符" in r4.get("error", ""), r4.get("error", ""))
        check("账号不符时不写交付清单", not os.path.isfile(os.path.join(
            r4.get("batch_path", ""), "_导出清单.csv")))

        os.environ["FAKE_SEC"] = _fixture.SEC
        os.environ["FAKE_COUNT"] = "3"
        cfg = config.load()
        cfg["min_count"] = 10
        config.save(cfg)
        r5 = engine.sync(os.path.join(tmp, "out4"))
        check("条数低于下限被拒", not r5.get("ok") and "条数异常" in r5.get("error", ""),
              r5.get("error", ""))
        check("条数异常时不写交付清单", not os.path.isfile(os.path.join(
            r5.get("batch_path", ""), "_导出清单.csv")))

        print("== 续跑 ==")
        r6 = engine.retry(r4.get("batch_path", ""))
        check("采集阶段失败不给续跑", not r6.get("ok") and "采集阶段" in r6.get("error", ""),
              r6.get("error", ""))
        r7 = engine.retry(r5.get("batch_path", ""))
        check("条数失败也不给续跑", not r7.get("ok"))

        cfg["min_count"] = 1
        config.save(cfg)
        os.environ["FAKE_COUNT"] = "5"
        os.environ["FAKE_AUDIT_RC"] = "1"
        r8 = engine.sync(os.path.join(tmp, "out5"))
        check("体检失败时整轮失败", not r8.get("ok") and "audit_obsidian.py" in r8.get("error", ""),
              r8.get("error", ""))
        check("体检失败保留采集结果", bool(engine.read_state(r8["batch_path"]).get("collect")))
        os.environ["FAKE_AUDIT_RC"] = "0"
        r9 = engine.retry(r8.get("batch_path", ""))
        check("续跑成功", r9.get("ok"), str(r9)[:300])
        check("续跑落到新批次", r9.get("batch_path") != r8.get("batch_path"))
        check("续跑记录来源批次", engine.read_state(r9["batch_path"]).get("resumed_from")
              == r8.get("batch_path"))

        print("== 空批次保护 ==")
        import manifest as mf
        busy = os.path.join(tmp, "busy")
        os.makedirs(busy, exist_ok=True)
        open(os.path.join(busy, "用户自己的文件.txt"), "w").close()
        rr = mf.build(_fixture.ROWS, busy)
        check("非空目录拒绝写入", not rr.get("ok") and "拒绝覆盖" in rr.get("error", ""))
        check("用户文件未被删", os.path.isfile(os.path.join(busy, "用户自己的文件.txt")))
        check("没有生成说明文件", not os.path.isfile(os.path.join(busy, "_导出说明.txt")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
