# -*- coding: utf-8 -*-
"""一键全量复检（串行，避免窗口与临时数据互相干扰）。

用法: python tests/run_all.py [轮次名]
产出: 验证输出/全量复检-<轮次名>.json
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PY = sys.executable
sys.path.insert(0, os.path.join(APP, "src"))
from common import VERSION  # noqa: E402

EXE = os.path.join(APP, "build", "pyi-dist", "douyin_sync.exe")
OUT = os.path.join(APP, "验证输出")
ROUND = sys.argv[1] if len(sys.argv) > 1 else "本轮"


def steps():
    exe = [EXE] if os.path.isfile(EXE) else []
    return [
        ("矩阵", [PY, os.path.join(HERE, "verify_matrix.py")]),
        ("子类别", [PY, os.path.join(HERE, "verify_subcat.py")]),
        ("知识库与报告", [PY, os.path.join(HERE, "verify_kb.py")]),
        ("新用户路径", [PY, os.path.join(HERE, "verify_new_user.py")]),
        ("清单复核", [PY, os.path.join(HERE, "verify_manifest.py")]),
        ("界面", [PY, os.path.join(HERE, "verify_ui.py"), ROUND]),
        ("界面改动", [PY, os.path.join(HERE, "verify_ui_fix.py")]),
        ("MCP 全链路", [PY, os.path.join(HERE, "verify_mcp.py")] + exe),
        ("MCP 兼容", [PY, os.path.join(HERE, "verify_mcp_compat.py")] + exe),
        ("设置页", [PY, os.path.join(HERE, "verify_settings.py"), ROUND]),
        ("命令行", [PY, os.path.join(HERE, "verify_cli.py")] + exe),
        ("公开面", [PY, os.path.join(HERE, "verify_public_safe.py")]),
        ("真实数据", [PY, os.path.join(HERE, "verify_real.py")]),
        ("审计一致性", [PY, os.path.join(HERE, "verify_audit.py")]),
    ]


def main():
    results = []
    print(f"=== 全量复检 {ROUND} · {dt.datetime.now():%Y-%m-%d %H:%M:%S} · V{VERSION} ===",
          flush=True)
    for name, cmd in steps():
        t0 = time.time()
        print(f"\n--- {name} ---", flush=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1200, cwd=APP)
            out = (r.stdout or "").strip()
            sec = time.time() - t0
            for line in out.splitlines()[-10:]:
                print("   " + line, flush=True)
            if r.returncode:
                print("   [stderr]", (r.stderr or "")[-600:], flush=True)
            results.append({"step": name, "rc": r.returncode, "sec": round(sec, 1),
                            "tail": out.splitlines()[-10:]})
            print(f"   => {'PASS' if r.returncode == 0 else 'FAIL'} · {sec:.1f}s", flush=True)
        except subprocess.TimeoutExpired:
            results.append({"step": name, "rc": -1, "sec": 1200, "tail": ["超时"]})
            print("   => FAIL · 超时", flush=True)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"全量复检-{ROUND}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"round": ROUND, "version": VERSION,
                   "time": dt.datetime.now().isoformat(), "results": results},
                  f, ensure_ascii=False, indent=2)
    fails = [x for x in results if x["rc"] != 0]
    print(f"\n=== 汇总 {len(results)} 步 · 失败 {len(fails)} ===", flush=True)
    for x in results:
        print(f"  {'PASS' if x['rc'] == 0 else 'FAIL'}  {x['step']:<10} {x['sec']:>6.1f}s",
              flush=True)
    print("汇总文件:", path, flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
