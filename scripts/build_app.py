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
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", ROOT,
        os.path.join(ROOT, "run.py"),
    ]
    print(">> PyInstaller ...")
    subprocess.run(cmd, check=True, cwd=ROOT)


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
    copy_tools()
    make_shortcut()
    total = 0
    for root, _d, files in os.walk(os.path.join(DIST, APP_NAME)):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print(f"完成。版本 v{APP_VERSION}，总体积约 {total / 1024 / 1024:.0f} MB，位于 dist/{APP_NAME}/")
