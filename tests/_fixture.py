# -*- coding: utf-8 -*-
"""测试用假项目：完全离线，不碰真实抖音数据与真实知识库。

真实脚本的接口约定（extract_favorites.py 的日志行、weekly_prepare.py 的 exit 10、
rebuild_deliverables.py 的三段式）在这里用最小桩复刻，用来验证引擎的门禁与续跑。
"""
import json
import os

SEC = "MS4wTESTACCOUNT0000000000000000000000000000"
ROWS = [
    {"标题/文案": "AI 视频一：提示词技巧", "类型": "视频", "作者": "作者甲",
     "发布时间": "2026-11-09 10:00:00", "点赞数": 1200, "作品ID": "1001",
     "作品链接": "https://www.douyin.com/video/1001", "收藏夹": "AI",
     "AI相关": "是", "AI类别": "AI效率办公", "核心内容归纳": "讲提示词",
     "内容介绍": "介绍了提示词写法与常见坑。", "概念": ""},
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
    {"标题/文案": "边界外的一条", "类型": "视频", "作者": "作者戊",
     "发布时间": "2026-01-01 00:00:00", "点赞数": 1, "作品ID": "1005",
     "作品链接": "https://www.douyin.com/video/1005", "收藏夹": "",
     "AI相关": "是", "AI类别": "其他AI相关", "核心内容归纳": "旧",
     "内容介绍": "旧的介绍", "概念": ""},
]

EXTRACT = '''# -*- coding: utf-8 -*-
import json, os, sys
N = int(os.environ.get("FAKE_COUNT", "5"))
SEC = os.environ.get("FAKE_SEC", "%s")
print("[self-profile] 账号: 测试账号  sec_uid: " + SEC, flush=True)
for i in range(1, 3):
    print("[collect] 第 %%d 页完成, 累计 %%d 条" %% (i, min(i * 3, N)), flush=True)
print("[collect] 共获取 %%d 条收藏" %% N, flush=True)
os.makedirs("output", exist_ok=True)
json.dump([{"aweme_id": str(1000 + i)} for i in range(N)],
          open("output/favorites_raw.json", "w", encoding="utf-8"))
print("DONE rows=%%d" %% N, flush=True)
sys.exit(0)
''' % SEC

DIFF = '''# -*- coding: utf-8 -*-
import os, sys
n = int(os.environ.get("FAKE_NEW", "1"))
print("发现新增 %d 条 | 旧源=rows_merged.json 旧=4 全量=5" % n)
if n == 0:
    sys.exit(10)
sys.exit(0)
'''

TABLES = '''# -*- coding: utf-8 -*-
import json, os, shutil, sys
rows = os.environ.get("FAKE_ROWS", "")
if rows and os.path.isfile(rows):
    os.makedirs("work", exist_ok=True)
    shutil.copyfile(rows, "work/rows_merged.json")
print("DONE rows")
sys.exit(0)
'''

GEN = '''# -*- coding: utf-8 -*-
import sys
print("ok")
sys.exit(0)
'''

OK = '''# -*- coding: utf-8 -*-
import os, sys
print("ok")
sys.exit(int(os.environ.get("FAKE_AUDIT_RC", "0")))
'''


def make_kb(tmp):
    kb = os.path.join(tmp, "kb")
    os.makedirs(os.path.join(kb, "01_AI笔记"), exist_ok=True)
    with open(os.path.join(kb, "00_入口.md"), "w", encoding="utf-8") as f:
        f.write("# 入口\n")
    return kb


def make_project(tmp, kb=None, rows=None):
    p = os.path.join(tmp, "TikTokDownloader")
    os.makedirs(os.path.join(p, "Volume"), exist_ok=True)
    os.makedirs(os.path.join(p, "output"), exist_ok=True)
    os.makedirs(os.path.join(p, "work", "transcripts"), exist_ok=True)
    files = {"extract_favorites.py": EXTRACT, "weekly_prepare.py": DIFF,
             "make_tables.py": TABLES, "gen_obsidian.py": GEN,
             "audit_obsidian.py": OK, "probe_account.py": EXTRACT}
    for name, body in files.items():
        with open(os.path.join(p, name), "w", encoding="utf-8") as f:
            f.write(body)
    with open(os.path.join(p, "Volume", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"cookie": "fake-cookie", "download": False}, f)
    with open(os.path.join(p, "output", "favorites_raw.json"), "w", encoding="utf-8") as f:
        json.dump([{"aweme_id": "1001"}], f)
    rows_path = os.path.join(p, "work", "rows_merged.json")
    with open(rows_path, "w", encoding="utf-8") as f:
        json.dump(rows or ROWS, f, ensure_ascii=False)
    with open(os.path.join(p, "work", "concepts_merged.json"), "w", encoding="utf-8") as f:
        json.dump({"1001": ["提示词工程"], "1005": ["旧概念"]}, f, ensure_ascii=False)
    with open(os.path.join(p, "work", "transcripts", "1001.txt"), "w", encoding="utf-8") as f:
        f.write("这是视频一的转写稿，用来验证笔记里会带节选。")
    return p, rows_path


def configure(tmp, project, kb, sec=SEC, rows_path=None):
    import config
    path = os.path.join(tmp, "settings.json")
    config.save({"project_dir": project, "python": os.sys.executable,
                 "kb_dir": kb, "expect_sec_uid": sec, "expect_nickname": "测试账号",
                 "dest": os.path.join(tmp, "out"),
                 "frm": "", "to": ""}, path)
    return path
