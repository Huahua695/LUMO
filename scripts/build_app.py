"""一键打包：PyInstaller 打包主程序 → 拷贝外部工具 → 创建桌面快捷方式 → 生成发行 zip。"""
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
        "--noupx",              # 本机从未装 UPX，spec 里的 upx=True 一直在静默跳过
        "--optimize", "2",      # 常量折叠 + 去 docstring，实测 exe -0.68MB
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
    # Logs/ 是开发机的 ffreport 调试日志，不该带给最终用户（审查 P3-18）
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("Logs"))


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


def make_zip():
    """生成发行 zip（LZMA）。此前仓库无任何生成 zip 的代码，发行包靠手工压缩、不可复现。
    实测 1227 文件 → 136.3MB（deflate 163.6MB）；LZMA 不接受 compresslevel 参数。"""
    import zipfile
    src = os.path.join(DIST, APP_NAME)
    out = os.path.join(DIST, f"{APP_NAME}-v{APP_VERSION}.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_LZMA) as z:
        for root, _d, files in os.walk(src):
            for f in sorted(files):
                p = os.path.join(root, f)
                # arcname 保留顶层 拾光工具箱/ 目录，解压后结构与现有发行包一致
                z.write(p, os.path.relpath(p, DIST))
    print(f">> 发行包 {os.path.getsize(out) / 1048576:.0f} MB → {out}")


if __name__ == "__main__":
    build_exe()
    prune_dist()
    copy_tools()
    make_shortcut()
    make_zip()
    total = 0
    for root, _d, files in os.walk(os.path.join(DIST, APP_NAME)):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    zip_path = os.path.join(DIST, f"{APP_NAME}-v{APP_VERSION}.zip")
    zip_mb = os.path.getsize(zip_path) / 1024 / 1024 if os.path.isfile(zip_path) else 0
    print(f"完成。版本 v{APP_VERSION}，解压后约 {total / 1024 / 1024:.0f} MB，"
          f"发行包约 {zip_mb:.0f} MB，位于 dist/{APP_NAME}/")
