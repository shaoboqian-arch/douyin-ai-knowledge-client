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
            if f.endswith(".md") and f != manifest.REPORT_NAME:
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
        check("清单 4 行（范围外 1 条被排除）", len(manifest.read_report(b1)["items"]) == 4)
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
            r4.get("batch_path", ""), manifest.REPORT_NAME)))

        os.environ["FAKE_SEC"] = _fixture.SEC
        print("== 条数下限已移除（2026-11-18 裁决）：低条数不再拦截 ==")
        os.environ["FAKE_COUNT"] = "3"
        r5 = engine.sync(os.path.join(tmp, "out4"))
        check("低条数不再拦截、照常交付",
              r5.get("ok") and r5.get("collect_total") == 3, str(r5)[:200])

        print("== 续跑 ==")
        r6 = engine.retry(r4.get("batch_path", ""))
        check("采集阶段失败不给续跑", not r6.get("ok") and "采集阶段" in r6.get("error", ""),
              r6.get("error", ""))

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

        print("== 项目锁：与每周增量编排互斥 ==")
        import ctypes
        name = engine._project_mutex_name(project, "weekly")
        k32 = ctypes.windll.kernel32
        hold = k32.CreateMutexW(None, True, name)
        rl = engine.sync(os.path.join(tmp, "out-lock"))
        check("每周任务持锁时全仓同步被挡",
              not rl.get("ok") and "每周增量" in rl.get("error", ""), rl.get("error", ""))
        check("被挡时不创建批次目录", not os.path.isdir(rl.get("batch_path") or ""))
        k32.CloseHandle(hold)
        rl2 = engine.sync(os.path.join(tmp, "out-lock2"), "2026-10-01", "2026-11-30")
        check("对方释放后恢复可跑", rl2.get("ok"), str(rl2)[:200])
        check("同步结束互斥体已释放",
              not engine._mutex_open(engine._project_mutex_name(project, "client")))

        print("== 项目锁：重入与异常路径 ==")
        lk1 = engine.ProjectLock(project, "client")
        check("首次加锁成功", lk1.acquire() == "")
        lk2 = engine.ProjectLock(project, "client")
        check("同进程重复加锁被挡", "已在跑另一轮" in lk2.acquire())
        rl3 = engine.sync(os.path.join(tmp, "out-lock3"))
        check("本进程持锁时同步直接中止，不建批次",
              not rl3.get("ok") and "已在跑另一轮" in rl3.get("error", "")
              and not os.path.isdir(rl3.get("batch_path") or ""), rl3.get("error", ""))
        lk1.release()
        check("释放后互斥体消失",
              not engine._mutex_open(engine._project_mutex_name(project, "client")))

        orig_run = engine.pipeline.run_script

        def _boom(*a, **kw):
            raise RuntimeError("模拟未预期异常")

        engine.pipeline.run_script = _boom
        try:
            raised = ""
            try:
                engine.sync(os.path.join(tmp, "out-lock4"))
            except RuntimeError as e:
                raised = str(e)
            check("未预期异常照旧向上抛（由调用层兜底）", "模拟未预期异常" in raised, raised)
        finally:
            engine.pipeline.run_script = orig_run
        check("异常路径也已释放项目锁（finally 兜底）",
              not engine._mutex_open(engine._project_mutex_name(project, "client")))

        print("== 空批次保护 ==")
        import manifest as mf
        busy = os.path.join(tmp, "busy")
        os.makedirs(busy, exist_ok=True)
        open(os.path.join(busy, "用户自己的文件.txt"), "w").close()
        rr = mf.build(_fixture.ROWS, busy)
        check("非空目录拒绝写入", not rr.get("ok") and "拒绝覆盖" in rr.get("error", ""))
        check("用户文件未被删", os.path.isfile(os.path.join(busy, "用户自己的文件.txt")))
        check("没有生成报告", not os.path.isfile(os.path.join(busy, manifest.REPORT_NAME)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
