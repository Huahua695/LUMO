"""一键打包：PyInstaller 打包主程序 → 拷贝外部工具 → 创建桌面快捷方式。"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
APP_NAME = "拾光工具箱"
ICO = os.path.join(ROOT, "assets", "icon.ico")
sys.path.insert(0, APP)
from version import APP_VERSION  # noqa: E402


def build_exe():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", APP_NAME,
        "--icon", ICO,
        "--add-data", os.path.join(ROOT, "assets") + ";assets",
        "--collect-all", "yt_dlp",
        "--collect-all", "PySide6.QtMultimedia",
        "--collect-all", "PySide6.QtMultimediaWidgets",
        # 纯 Widgets 应用：排除 QML/Quick/PDF 等用不到的 Python 模块
        # （注意：不要 exclude setuptools——与 PySide6/yt-dlp 的 hook 组合
        # 会让 PyInstaller 分析阶段卡死数十分钟）
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtPdf",
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", ROOT,
        os.path.join(ROOT, "run.py"),
    ]
    print(">> PyInstaller ...")
    subprocess.run(cmd, check=True, cwd=ROOT)


# 轻量化：纯 Widgets + Multimedia + Svg 应用用不到的 Qt 二进制。
# 删除后必须跑 exe --selftest 和 scripts/screenshots.py 验证渲染；
# 若个别机器窗口白屏（缺软件 OpenGL 回退），把 opengl32sw.dll 从清单移除。
PRUNE_FILES = [
    "opengl32sw.dll",
    "Qt6Pdf.dll",
    "Qt6VirtualKeyboard.dll",
    "Qt6Quick.dll",
    "Qt6Qml.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlWorkerScript.dll",
]
PRUNE_DIRS = ["translations"]


def prune_dist():
    base = os.path.join(DIST, APP_NAME, "_internal", "PySide6")
    removed = []
    for rel in PRUNE_FILES:
        p = os.path.join(base, rel.replace("/", os.sep))
        if os.path.isfile(p):
            os.remove(p)
            removed.append(rel)
    for rel in PRUNE_DIRS:
        p = os.path.join(base, rel.replace("/", os.sep))
        if os.path.isdir(p):
            shutil.rmtree(p)
            removed.append(rel + "/")
    if removed:
        print(f">> 裁剪无用 Qt 组件 {len(removed)} 项: {', '.join(removed)}")


def copy_tools():
    src = os.path.join(ROOT, "tools")
    dst = os.path.join(DIST, APP_NAME, "tools")
    print(">> 拷贝外部工具 ...")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def make_shortcut():
    dist_app = os.path.join(DIST, APP_NAME)
    exe = os.path.join(dist_app, APP_NAME + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("找不到 " + exe)
    # 图标直接用 exe 内嵌图标（PyInstaller 6 把 assets 放进 _internal，
    # 指向 dist/assets/icon.ico 的旧写法在打包后会失效）
    ps = f"""
$desktop = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop '{APP_NAME}.lnk'))
$lnk.TargetPath = '{exe}'
$lnk.WorkingDirectory = '{dist_app}'
$lnk.IconLocation = '{exe},0'
$lnk.Description = '拾光工具箱 - 资源无损下载 + AI 画质增强'
$lnk.Save()
Write-Output ('快捷方式已创建: ' + (Join-Path $desktop '{APP_NAME}.lnk'))
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


if __name__ == "__main__":
    build_exe()
    prune_dist()
    copy_tools()
    make_shortcut()
    total = 0
    for root, _d, files in os.walk(os.path.join(DIST, APP_NAME)):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print(f"完成。版本 v{APP_VERSION}，总体积约 {total / 1024 / 1024:.0f} MB，位于 dist/{APP_NAME}/")
