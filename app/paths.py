"""路径解析：开发模式与打包后均可定位外部工具与资源。"""
import os
import sys


def project_dir() -> str:
    """打包后 = 主程序所在目录；开发时 = 项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def assets_dir() -> str:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(os.path.join(meipass, "assets")):
            return os.path.join(meipass, "assets")
        return os.path.join(project_dir(), "assets")
    return os.path.join(project_dir(), "assets")


def asset_path(name: str) -> str:
    return os.path.join(assets_dir(), name)


def tools_dir() -> str:
    return os.path.join(project_dir(), "tools")


def tool(name: str) -> str:
    return os.path.join(tools_dir(), name)


def ffmpeg() -> str:
    return tool("ffmpeg.exe")


def ffprobe() -> str:
    return tool("ffprobe.exe")


def m3u8dl_exe() -> str:
    return tool("N_m3u8DL-CLI.exe")


def realesrgan_exe() -> str:
    return os.path.join(tools_dir(), "realesrgan", "realesrgan-ncnn-vulkan.exe")


def realesrgan_model(name: str) -> str:
    return os.path.join(tools_dir(), "realesrgan", "models", name + ".param")


def tools_ready() -> list:
    """返回缺失的外部工具列表（空列表 = 全部就绪）。"""
    missing = []
    for p in (ffmpeg(), ffprobe(), m3u8dl_exe(), realesrgan_exe()):
        if not os.path.isfile(p):
            missing.append(os.path.basename(p))
    return missing
