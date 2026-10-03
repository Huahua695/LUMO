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


# 增强功能会用到的全部模型权重：param(结构) 与 bin(权重) 必须成对存在。
# 只查 .param 的话，缺 bin 时启动自检照样通过、跑到一半才失败
ENHANCE_MODELS = (
    "realesrgan-x4plus",
    "realesrgan-x4plus-anime",
    "realesr-general-x4v3",
    "realesr-animevideov3-x2",
    "realesr-animevideov3-x3",
    "realesr-animevideov3-x4",
)


def tools_ready() -> list[str]:
    """返回缺失的外部工具列表（空列表 = 全部就绪）。"""
    missing = []
    for p in (ffmpeg(), ffprobe(), m3u8dl_exe(), realesrgan_exe()):
        if not os.path.isfile(p):
            missing.append(os.path.basename(p))
    mdir = os.path.join(tools_dir(), "realesrgan", "models")
    for m in ENHANCE_MODELS:
        for ext in (".param", ".bin"):
            if not os.path.isfile(os.path.join(mdir, m + ext)):
                missing.append(m + ext)
    return missing
