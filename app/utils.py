"""通用小工具。"""
import os
import re
import time
from urllib.parse import unquote, urlparse

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 常见媒体扩展名（用于识别"文件直链"）
DIRECT_EXTS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts", ".m4v", ".wmv",
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma",
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif", ".tif", ".tiff",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts", ".m4v", ".wmv"}

ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_name(name: str, max_len: int = 120) -> str:
    name = ILLEGAL_CHARS.sub("_", name).strip(" .")
    return name[:max_len] if name else "未命名"


def filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    base = os.path.basename(path)
    return sanitize_name(base) if base else ""


def unique_path(path: str) -> str:
    """路径已存在时自动加 (1) (2)… 后缀。"""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{root} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def human_size(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "未知大小"
    if n <= 0:
        return "未知大小"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def human_speed(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    return human_size(n) + "/s"


def now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def open_in_explorer(path: str):
    if os.path.isdir(path):
        os.startfile(path)
    elif os.path.isfile(path):
        os.startfile(os.path.dirname(path))
