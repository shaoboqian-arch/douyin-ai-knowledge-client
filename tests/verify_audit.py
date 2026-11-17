# -*- coding: utf-8 -*-
"""审计一致性门禁（run_all 第 14 步）：保证「测试测的就是用户看到的那套」。

只读：不修改任何文件。检查项：
  1. 待加工文案唯一真源在 common.py，gui.py 不得再自带一份
  2. 子类别规则命中词确实写进笔记 frontmatter
  3. Tk 线程安全：安装器 / 初始化都用队列 + 主线程轮询，销毁时取消
  4. 字体族唯一真源 FONT_FAMILY，控件默认值不再写死字体名
  5. 安装包 / 便携版说明与界面动作、MCP 工具数一致
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, HERE)

import common  # noqa: E402

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


def read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


def main():
    print(f"== 审计一致性 · V{common.VERSION} ==")
    gui = read("src/gui.py")
    common_src = read("src/common.py")
    installer = read("src/installer.py")
    setup = read("src/setup_env.py")
    kit = read("src/ui_kit.py")
    report = read("src/report_ui.py")
    manifest_src = read("src/manifest.py")
    settings = read("src/settings.py")
    tpl = read("build/README.template.md")
    build = read("build/build.py")

    print("== 版本 ==")
    check("版本号三段式", bool(re.fullmatch(r"\d+\.\d+\.\d+", common.VERSION)),
          common.VERSION)
    check("版本号唯一真源", common_src.count('VERSION = "') == 1)

    print("== 待加工文案真源 ==")
    check("gui 不再自带待文案实现",
          "def gap_heading(" not in gui and "def format_gap_rows(" not in gui)
    check("common 提供唯一实现",
          "def gap_heading(" in common_src and "def format_gap_rows(" in common_src)
    try:
        import gui as gui_mod
        check("gui.gap_heading 就是 common.gap_heading",
              gui_mod.gap_heading is common.gap_heading)
        check("gui.format_gap_rows 就是 common.format_gap_rows",
              gui_mod.format_gap_rows is common.format_gap_rows)
    except ImportError:
        print("  SKIP  gui 模块导入（本解释器没有 tkinter，静态检查已覆盖）")
    except Exception as e:
        check("gui 模块可导入", False, f"{type(e).__name__}: {e}")
    rows = common.format_gap_rows([
        {"标题": "同名", "原因": "缺介绍", "序号": 1,
         "作品链接": "https://example.invalid/v/1", "建议": "补一段介绍"},
        {"标题": "同名", "原因": "缺转写", "序号": 2},
    ])
    check("同名条目带序号消歧", "（1）" in rows[0][0] and "（2）" in rows[1][0],
          f"{rows[0][0]} / {rows[1][0]}")
    check("详情含原因 / 作品 / 建议",
          all(k in rows[0][2] for k in ("缺什么", "作品：", "建议：")), rows[0][2])
    check("界面标题口径与 common 一致", common.gap_heading(1) == "待加工 1")

    print("== 子类别依据 ==")
    import manifest
    fm = manifest._frontmatter({"标题/文案": "x", "AI类别": "AI效率办公"}, [],
                               "提示词与模板", "提示词")
    check("frontmatter 写出规则命中词",
          "子类别: 提示词与模板" in fm and "子类别依据: 提示词" in fm, fm[:200])
    check("依据为空时不写空字段",
          "子类别依据" not in manifest._frontmatter({}, [], "", ""))
    check("build 把 sub_hint 传进 frontmatter",
          "_frontmatter(row, concepts, sub, sub_hint)" in manifest_src)
    check("《导出报告》指明依据位置", "子类别依据" in
          read("src/manifest.py").split("## 说明")[-1][:800])

    print("== Tk 线程安全 ==")
    check("安装器不再从子线程调 after",
          "after(0" not in installer and "after_idle" not in installer.split("def go")[-1])
    check("安装器用队列回传结果", "_q.put" in installer and "def _poll" in installer)
    check("安装器销毁时取消轮询", "<Destroy>" in installer and "_cancel_poll" in installer)
    check("初始化销毁时取消轮询", "<Destroy>" in setup and "_cancel_poll" in setup)

    print("== 字体与控件系统 ==")
    check("字体族唯一真源", "FONT_FAMILY" in kit and "global FONT_FAMILY" in kit)
    check("ui_kit 默认字体不写死",
          '("Microsoft YaHei UI", 9)' not in kit
          and '("Microsoft YaHei UI", 10,' not in kit)
    check("报告窗口 fallback 跟随 FONT_FAMILY", "(FONT_FAMILY, 10)" in report)
    check("卡片标题跟随 family",
          '(family, 11, "bold")' in gui and '(family, 11, "bold")' in settings)

    print("== 对外材料 ==")
    tools = ("dy_status", "dy_preflight", "dy_export", "dy_sync", "dy_retry", "dy_report")
    check("安装包模板列全 6 个 MCP 工具", all(t in tpl for t in tools))
    check("便携版说明列全 6 个 MCP 工具", all(t in build for t in tools))
    check("安装器说明含首启提示与单一报告",
          "⚠️ 全仓同步" in installer and "《导出报告.md》" in installer)
    check("便携版说明含首启提示与单一报告",
          "⚠️ 全仓同步" in build and "《导出报告.md》" in build)
    check("面向用户材料不含已删除交付物",
          all(s not in tpl and s not in installer and s not in build
              for s in ("_导出说明.txt", "_待加工.csv")))
    src_dir = os.path.join(APP, "src")
    src_files = [f"src/{n}" for n in os.listdir(src_dir) if n.endswith(".py")]
    stale = ("开始整理", "同步整理", "重新整理", "一批空清单")
    offenders = [f"{rel}:{s}" for rel in src_files for s in stale
                 if s in read(rel)]
    check("全源码术语统一", not offenders, str(offenders[:3]))
    check("兜底分类也写明依据", "未命中具体规则" in read("src/subcat.py"))
    m = re.search(r"if self\.first_hint\.winfo_manager\(\):\s*\n\s*h \+= (\d+)", gui)
    check("首启提示预留高度 ≥ 40（不裁掉状态行）",
          bool(m) and int(m.group(1)) >= 40,
          m.group(1) if m else "未匹配到 resize 中的高度增量")

    print("== 截图 ==")
    for name in ("main-window.png", "report.png"):
        p = os.path.join(APP, "docs", "images", name)
        check(f"{name} 存在且非空", os.path.isfile(p) and os.path.getsize(p) > 5000,
              str(os.path.getsize(p)) if os.path.isfile(p) else "缺失")

    print(f"\n合计 {PASS} 项 · 失败 {len(FAILS)}")
    for n, d in FAILS:
        print(f"  FAIL {n}  {d}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
