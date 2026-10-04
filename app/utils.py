"""通用小工具。"""
import json
import os
import re
import subprocess
import time
from urllib.parse import unquote, urlparse

from .paths import ffprobe
from .proc import CREATE_NO_WINDOW

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


def probe_media(src: str) -> tuple[float, int, int, float]:
    """返回 (时长秒, 宽, 高, fps)。时长/宽高读不到时为 0。

    fps 保留 probe_fps 的 r_frame_rate 语义（B1 已撤销，不改 VFR）：
    1~240 之外视为无效、整体兜底 25.0。一次 ffprobe 取全四项，
    供增强预检使用（此前 dur/fps 分属 cut_engine 与 enhance 各起一个进程）。
    """
    try:
        r = subprocess.run(
            [ffprobe(), "-v", "error", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration",
             "-of", "json", src],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=30)
        info = json.loads(r.stdout or b"{}")
    except Exception:
        return 0.0, 0, 0, 0.0
    dur = float((info.get("format") or {}).get("duration") or 0)
    w = h = 0
    fps = 0.0
    for s in info.get("streams") or []:
        if not w and s.get("width"):
            w, h = int(s["width"]), int(s.get("height") or 0)
        if not fps and s.get("r_frame_rate"):
            num, _, den = (s["r_frame_rate"] or "").partition("/")
            try:
                f = float(num or 25) / (float(den or 1) or 1.0)
                if 1 <= f <= 240:
                    fps = f
            except (ValueError, ZeroDivisionError):
                pass
    return dur, w, h, fps or 25.0


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


def reveal_in_explorer(path: str):
    """在资源管理器中定位文件；路径无效时回退到打开所在文件夹。"""
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_in_explorer(path if os.path.isdir(path)
                         else os.path.dirname(path) or ".")
