# -*- coding: utf-8 -*-
"""构建交付物（依赖装在 build/vendor，不污染系统 Python）。

用法:
    "C:/Program Files/Python312/python.exe" build/build.py

步骤:
    1) 缺依赖时 pip 安装 pyinstaller==6.22.3 到 build/vendor（清华源）
    2) PyInstaller 单文件 exe（console 模式，MCP 需要 stdout；GUI 启动时隐藏控制台）
    3) 生成 Setup.exe / 便携 zip / mcp配置.json / dist/README.md
    4) 基础自检：PE 头、--version、文件大小
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
SRC = os.path.join(APP, "src")
DIST = os.path.join(APP, "dist")
VENDOR = os.path.join(HERE, "vendor")
PYI_DIST = os.path.join(HERE, "pyi-dist")
PYI_WORK = os.path.join(HERE, "pyi-work")
sys.path.insert(0, SRC)
from common import APP_NAME, VERSION  # noqa: E402

SETUP_EXE = f"{APP_NAME}-Setup-V{VERSION}.exe"
PORTABLE_ZIP = f"{APP_NAME}-V{VERSION}-便携版.zip"
PY = sys.executable
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def is_cache_path(path):
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    return "__pycache__" in parts or path.endswith(".pyc")


def add_data(src, dest="."):
    """构造 PyInstaller --add-data；跳过 __pycache__ 与 .pyc。"""
    if is_cache_path(src):
        return []
    if os.path.isfile(src):
        return ["--add-data", src + os.pathsep + dest]
    args = []
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel_base = os.path.relpath(base, src)
        for name in files:
            if name.endswith(".pyc"):
                continue
            fp = os.path.join(base, name)
            target = dest if rel_base == "." else os.path.join(dest, rel_base)
            args.extend(["--add-data", fp + os.pathsep + target])
    return args


def prune_caches(*roots):
    """打包前清掉解释器缓存，避免以后增加 --add-data 时打进安装包。"""
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for base, dirs, files in os.walk(root):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(base, "__pycache__"), ignore_errors=True)
                dirs.remove("__pycache__")
            for name in files:
                if name.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(base, name))
                    except OSError:
                        pass


def run(cmd, env=None, check=True):
    print(">>>", " ".join(str(x) for x in cmd), flush=True)
    r = subprocess.run(cmd, env=env, cwd=APP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout:
        print(r.stdout[-4000:], flush=True)
    if r.stderr:
        print("[stderr]", r.stderr[-3000:], flush=True)
    if check and r.returncode:
        raise SystemExit(f"命令失败 exit={r.returncode}")
    return r


def ensure_vendor():
    marker = os.path.join(VENDOR, "PyInstaller", "__init__.py")
    if os.path.isfile(marker):
        print("vendor 已就绪，跳过安装", flush=True)
        return
    os.makedirs(VENDOR, exist_ok=True)
    run([PY, "-m", "pip", "install", "--no-cache-dir", "--no-warn-script-location",
         "--target", VENDOR, "-i", MIRROR, "pyinstaller==6.22.3"])


def build_exe():
    import make_icon
    ico = make_icon.ensure()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([VENDOR, SRC] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    args = [
        PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "douyin_sync",
        "--paths", SRC, "--paths", VENDOR,
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "report_ui",
        "--hidden-import", "kbreport",
        "--hidden-import", "subcat",
        *add_data(ico, "."),
        "--icon", ico,
        "--distpath", PYI_DIST, "--workpath", PYI_WORK, "--specpath", HERE,
        os.path.join(SRC, "app.py"),
    ]
    run(args, env=env)
    exe = os.path.join(PYI_DIST, "douyin_sync.exe")
    if not os.path.isfile(exe):
        raise SystemExit("PyInstaller 未产出 exe")
    return exe


def write_texts():
    with open(os.path.join(DIST, "mcp配置.json"), "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"douyin-fav-sync": {
            "type": "stdio",
            "command": r"C:\Users\<用户名>\AppData\Local\抖音收藏整理\抖音收藏整理.exe",
            "args": ["--mcp"],
            "description": "抖音收藏采集与知识库整理（读取本机抖音项目数据）"}}},
            f, ensure_ascii=False, indent=2)
    with open(os.path.join(HERE, "README.template.md"), encoding="utf-8") as f:
        readme = (f.read()
                  .replace("{VERSION}", VERSION)
                  .replace("{SETUP_EXE}", SETUP_EXE)
                  .replace("{PORTABLE_ZIP}", PORTABLE_ZIP))
    with open(os.path.join(DIST, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)


def pack_portable(exe):
    note = (f"# {APP_NAME} V{VERSION} · 便携版\n\n"
            "双击 `抖音收藏整理.exe` 打开界面；首次运行点「初始化本机环境」。\n\n"
            "MCP 接入：把下面这一个键合并进 `~/.workbuddy/mcp.json` 已有的 mcpServers，\n"
            "把 command 换成本机 exe 的实际绝对路径（不要整份覆盖文件）。\n\n"
            "```json\n"
            '{"douyin-fav-sync": {"type": "stdio", "command": "<本机绝对路径>/抖音收藏整理.exe", '
            '"args": ["--mcp"], "description": "抖音收藏采集与知识库整理"}}\n'
            "```\n\n"
            "保存后到 WorkBuddy 连接器管理 → 右上角自定义连接器 → 对本服务点「信任」才会生效；\n"
            "验证：新建对话调用 dy_status，返回 ready 即接通。\n\n"
            "前置：本机已有可运行的抖音采集项目（TikTokDownloader，含 .venv 与已登录 Cookie），\n"
            "以及一个已生成的 Obsidian 知识库目录。客户端不复制 Cookie、不上传任何数据。\n")
    with zipfile.ZipFile(os.path.join(DIST, PORTABLE_ZIP), "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, f"{APP_NAME}/{APP_NAME}.exe")
        z.writestr(f"{APP_NAME}/说明.md", note)
        z.writestr(f"{APP_NAME}/版本.txt", f"V{VERSION}\n")


def verify(exe, setup):
    with open(exe, "rb") as f:
        magic = f.read(2)
    assert magic == b"MZ", f"不是有效 PE 文件: {magic!r}"
    r = run([exe, "--version"], check=False)
    ver = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    print(f"[自检] PE=MZ  version={ver!r}  exe={os.path.getsize(exe):,} bytes", flush=True)
    assert ver == VERSION, f"版本号不符: {ver!r}"
    assert os.path.isfile(setup)
    return ver


def main():
    os.makedirs(DIST, exist_ok=True)
    ensure_vendor()
    prune_caches(SRC, HERE)
    exe = build_exe()
    setup = os.path.join(DIST, SETUP_EXE)
    shutil.copy2(exe, setup)
    write_texts()
    pack_portable(exe)
    v = verify(exe, setup)
    print("\n=== 交付物 ===", flush=True)
    for name in sorted(os.listdir(DIST)):
        p = os.path.join(DIST, name)
        if os.path.isfile(p):
            print(f"  {name}  {os.path.getsize(p):,} bytes", flush=True)
    print(f"V{v} 构建完成", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
