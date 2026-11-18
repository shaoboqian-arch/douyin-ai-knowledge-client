# -*- coding: utf-8 -*-
"""知识库对接与入库报告复检。

覆盖：
  · Obsidian 检测（安装位置 / 库清单 / 未安装时的降级）
  · 知识库开关：关掉后不跑 gen/audit、状态不因缺库而不就绪
  · 入库报告：身份 / 新增 / 取消 / 转写 / 介绍 / 概念 / 交付物 / 体检
  · 报告落盘与 Markdown 渲染
"""
import json
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
import detect  # noqa: E402
import engine  # noqa: E402
import kbreport  # noqa: E402

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


ROWS_NEW = [
    {"标题/文案": "新 AI 视频：提示词", "类型": "视频", "作者": "甲",
     "发布时间": "2026-11-09 10:00:00", "作品ID": "1000", "AI相关": "是",
     "AI类别": "AI效率办公", "核心内容归纳": "x", "内容介绍": "已写介绍"},
    {"标题/文案": "AI 图集", "类型": "图集", "作者": "乙",
     "发布时间": "2026-11-05 09:00:00", "作品ID": "1001", "AI相关": "是",
     "AI类别": "AI绘画与图像", "核心内容归纳": "x", "内容介绍": ""},
    {"标题/文案": "AI 视频二", "类型": "视频", "作者": "丙",
     "发布时间": "2026-10-20 20:00:00", "作品ID": "1002", "AI相关": "是",
     "AI类别": "AI编程与开发", "核心内容归纳": "x", "内容介绍": ""},
    {"标题/文案": "非 AI 一条", "类型": "视频", "作者": "丁",
     "发布时间": "2026-10-10 08:00:00", "作品ID": "1003", "AI相关": "否",
     "AI类别": "", "核心内容归纳": "", "内容介绍": ""},
    {"标题/文案": "待判定一条", "类型": "视频", "作者": "戊",
     "发布时间": "2026-10-02 08:00:00", "作品ID": "1004", "AI相关": "待定",
     "AI类别": "", "核心内容归纳": "", "内容介绍": ""},
]

ROWS_OLD = [dict(r, 作品ID=str(int(r["作品ID"]) + 1)) for r in ROWS_NEW]


def prepare(tmp):
    kb = _fixture.make_kb(tmp)
    project, _ = _fixture.make_project(tmp, rows=ROWS_NEW)
    with open(os.path.join(project, "work", "prev_rows_merged.json"), "w",
              encoding="utf-8") as f:
        json.dump(ROWS_OLD, f, ensure_ascii=False)
    with open(os.path.join(project, "work", "concepts_merged.json"), "w",
              encoding="utf-8") as f:
        json.dump({"1000": ["新概念", "提示词工程"], "1001": ["提示词工程"]},
                  f, ensure_ascii=False)
    tdir = os.path.join(project, "work", "transcripts")
    open(os.path.join(tdir, "1000.txt"), "w", encoding="utf-8").write("转写稿")
    path = _fixture.configure(tmp, project, kb)
    os.environ["DYSYNC_SETTINGS"] = path
    return kb, project, path


def main():
    tmp = tempfile.mkdtemp(prefix="dysync-kb-")
    os.environ["FAKE_SEC"] = _fixture.SEC
    try:
        print("== Obsidian 检测 ==")
        exe = detect.find_obsidian()
        check("安装位置可探测（本机有则必须给出路径）",
              bool(exe) and os.path.isfile(exe) if exe else True, exe)
        cfg_path = os.path.join(tmp, "obsidian.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"vaults": {"a": {"path": os.path.join(tmp, "vaultA"), "open": False},
                                  "b": {"path": os.path.join(tmp, "vaultB"), "open": True}}}, f)
        vaults = detect.obsidian_vaults(cfg_path)
        check("库清单解析出 2 个", len(vaults) == 2, str(vaults))
        check("当前打开的库排在最前", vaults[0]["name"] == "vaultB", str(vaults[0]))
        info = detect.obsidian_info("", cfg_path)
        check("obsidian_info 结构完整",
              set(info) >= {"installed", "exe", "vaults", "config", "message"})

        orig_find = detect.find_obsidian
        detect.find_obsidian = lambda *_a, **_k: ""
        try:
            bad = detect.obsidian_info("", cfg_path)
            check("未安装时 installed=False", bad["installed"] is False)
            check("未安装时给出提示", bool(bad["message"]))
        finally:
            detect.find_obsidian = orig_find

        print("== 项目目录发现 ==")
        fake_home = os.path.join(tmp, "fakehome")
        deep = os.path.join(fake_home, "ws", "a", "b", "TikTokDownloader")
        os.makedirs(deep, exist_ok=True)
        open(os.path.join(deep, "extract_favorites.py"), "w").write("")
        hits = detect.scan_for_projects(fake_home)
        check("深层目录可被扫描到", deep.replace("/", "\\") in
              [h.replace("/", "\\") for h in hits], str(hits))
        shallow = os.path.join(fake_home, "TikTokDownloader")
        os.makedirs(shallow, exist_ok=True)
        check("同名但无标记文件不算",
              shallow.replace("/", "\\") not in
              [h.replace("/", "\\") for h in detect.scan_for_projects(fake_home)])
        far = os.path.join(fake_home, "1", "2", "3", "4", "5", "TikTokDownloader")
        os.makedirs(far, exist_ok=True)
        open(os.path.join(far, "extract_favorites.py"), "w").write("")
        check("超出深度不扫（默认 4 层）",
              far.replace("/", "\\") not in
              [h.replace("/", "\\") for h in detect.scan_for_projects(fake_home)])
        skip_dir = os.path.join(fake_home, "AppData", "x", "TikTokDownloader")
        os.makedirs(skip_dir, exist_ok=True)
        open(os.path.join(skip_dir, "extract_favorites.py"), "w").write("")
        check("跳过 AppData 等重目录",
              skip_dir.replace("/", "\\") not in
              [h.replace("/", "\\") for h in detect.scan_for_projects(fake_home)])
        os.environ["DOUYIN_PROJECT_DIR"] = deep
        check("环境变量可指定项目目录",
              any(os.path.normpath(h) == os.path.normpath(deep)
                  for h in detect.candidate_project_dirs()))
        os.environ.pop("DOUYIN_PROJECT_DIR", None)

        print("== 开关与状态 ==")
        kb, project, spath = prepare(tmp)
        cfg = config.load()
        check("默认启用知识库", cfg["kb_enabled"] is True)
        cfg["kb_enabled"] = False
        config.save(cfg)
        check("关闭后能读回", config.load()["kb_enabled"] is False)
        cfg = config.load()
        cfg["kb_dir"] = os.path.join(tmp, "不存在的库")
        st = engine.status(project, cfg)
        check("关掉知识库后缺库也不影响就绪", st["ready"] is True, str(st["missing"]))
        check("状态带 Obsidian 信息", "obsidian" in st and "installed" in st["obsidian"])
        cfg["kb_enabled"] = True
        st2 = engine.status(project, cfg)
        check("启用后缺库则不就绪", st2["ready"] is False and "知识库目录" in st2["missing"])
        config.save(cfg)

        print("== 关掉知识库的整理 ==")
        cfg = config.load()
        cfg.update(kb_enabled=False, kb_dir=kb)
        config.save(cfg)
        r = engine.sync(os.path.join(tmp, "out-off"), "2026-10-01", "2026-11-30")
        check("整理成功", r.get("ok"), str(r)[:200])
        stt = engine.read_state(r["batch_path"])
        check("没有跑 gen/audit", "notes" not in (stt.get("logs") or {})
              and "audit" not in (stt.get("logs") or {}), str(stt.get("logs")))
        rows = (r.get("report") or {}).get("rows") or []
        txt = {x["环节"]: x for x in rows}
        check("报告说明 Obsidian 未启用", "未启用" in txt["重建交付物"]["结果"],
              txt["重建交付物"]["结果"])
        check("体检标记为跳过", txt["audit 体检"]["状态"] == "skip")
        export_md = os.path.join(r["batch_path"], "_导出报告.md")
        check("入库结果并入导出报告",
              os.path.isfile(export_md) and "## 入库结果" in
              open(export_md, encoding="utf-8").read())
        check("报告 json 已落盘", os.path.isfile(os.path.join(r["batch_path"], "_入库报告.json")))

        print("== 启用知识库的整理 ==")
        cfg = config.load()
        cfg["kb_enabled"] = True
        config.save(cfg)
        r2 = engine.sync(os.path.join(tmp, "out-on"), "2026-10-01", "2026-11-30")
        check("整理成功", r2.get("ok"), str(r2)[:200])
        rep = r2.get("report") or {}
        rows = {x["环节"]: x for x in (rep.get("rows") or [])}
        check("8 行环节齐全", len(rows) == 8, str(list(rows)))
        check("身份校验匹配", "sec_uid 匹配" in rows["身份校验"]["结果"],
              rows["身份校验"]["结果"])
        check("新增 1 条（ID 差集）", rep["metrics"]["new"] == 1, str(rep["metrics"]["new"]))
        check("取消 1 条", rep["metrics"]["removed"] == 1, str(rep["metrics"]["removed"]))
        check("新增叙述含 1 条", rows["新增收藏"]["结果"].startswith("1 条"),
              rows["新增收藏"]["结果"])
        check("转写 1/1 就绪", rep["metrics"]["transcripts_ok"] == 1
              and rep["metrics"]["transcripts_need"] == 1)
        check("介绍 1/1", rep["metrics"]["intros_ok"] == 1)
        check("概念 1/1", rep["metrics"]["concepts_ok"] == 1)
        check("新增概念被识别", "新概念" in rep["metrics"]["new_concepts"],
              str(rep["metrics"]["new_concepts"]))
        check("共现 1 对", rep["metrics"]["pairs"] == 1, str(rep["metrics"]["pairs"]))
        check("体检通过", rows["audit 体检"]["状态"] == "ok", rows["audit 体检"]["结果"])
        md = kbreport.render_md(rep)
        check("md 表头齐全", "| 环节 | 结果 |" in md and "身份校验" in md)
        check("md 用状态图标", "✅" in md)
        check("报告能从批次读回", (kbreport.load(r2["batch_path"]) or {}).get("rows"))
        broken = kbreport.render_md({
            "rows": [{"环节": "换行", "状态": "ok", "结果": "第一行\n第二行 | x"}]})
        table = [ln for ln in broken.splitlines() if ln.startswith("| 换行")]
        check("结果换行不拆 md 表格", len(table) == 1 and "第一行 第二行" in table[0],
              str(table[:1]))

        print("== 状态机 ==")
        check("已完成批次拒绝续跑", engine.retry(r2["batch_path"]).get("ok") is False)

        print("== 报告窗口 ==")
        try:
            import tkinter as tk
        except ImportError:
            print("  SKIP  报告窗口（本环境没有 tkinter，未装系统包强跑 GUI）")
            tk = None
        if tk is not None:
            import time
            import report_ui
            from ui_kit import fonts
            root = tk.Tk()
            fm, fs, _fam = fonts(root)
            win = report_ui.ReportWindow(root, rep, kb, fm, fs)
            root.lift()
            root.attributes("-topmost", True)
            root.update()
            time.sleep(0.6)
            check("报告窗口可打开", root.winfo_exists() == 1)
            shot = os.path.join(APP, "验证输出", "入库报告-本轮.png")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            try:
                import ctypes
                from PIL import ImageGrab
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
                try:
                    img = ImageGrab.grab(window=hwnd)
                except Exception:
                    x, y = root.winfo_rootx(), root.winfo_rooty()
                    img = ImageGrab.grab(bbox=(x, y, x + root.winfo_width(),
                                               y + root.winfo_height()))
                img.save(shot)
                check("报告窗口截图已保存",
                      os.path.isfile(shot) and os.path.getsize(shot) > 8000,
                      f"{os.path.getsize(shot) if os.path.isfile(shot) else 0} B")
            except Exception as e:
                check("报告窗口截图已保存", False, str(e))
            root.destroy()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n== 汇总 {PASS} PASS / {len(FAILS)} FAIL ==")
    for name, detail in FAILS:
        print(f"  FAIL  {name}  {detail}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
