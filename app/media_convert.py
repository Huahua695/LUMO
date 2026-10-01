"""媒体格式转换（下载后处理）：
- 视频转封装（mp4/mkv）：流复制 -c copy，失败保留原件
- 音频提取/转码（mp3/m4a）：从任意音视频文件提取；能拷贝则拷贝，否则转码
- 图片转格式（jpg/png）：ffmpeg 单帧重编码
"""
import os
import subprocess

from .paths import ffmpeg
from .proc import CREATE_NO_WINDOW, stderr_target
from .utils import unique_path

# 目标格式 -> (扩展名, 无损可能)
TARGETS = {
    "mp4": ("mp4", True),
    "mkv": ("mkv", True),
    "mp3": ("mp3", False),
    "m4a": ("m4a", True),
    "jpg": ("jpg", False),
    "png": ("png", True),
}


def _run(cmd: list) -> "subprocess.CompletedProcess[bytes]":
    # ffmpeg 的报错细节落滚动日志（app/proc.py），界面只提示成败
    return subprocess.run(cmd, creationflags=CREATE_NO_WINDOW,
                          stdout=subprocess.DEVNULL, stderr=stderr_target())


def convert_media(src: str, fmt: str, out_dir: str) -> tuple[str, str]:
    """把 src 转换为目标格式。返回 (最终路径, 说明)。
    失败时返回 (原路径, 失败原因)——调用方应把原件交给用户。"""
    fmt = (fmt or "auto").lower()
    if fmt not in TARGETS:
        return src, ""
    dst_ext, lossless_ok = TARGETS[fmt]
    cur_ext = os.path.splitext(src)[1].lower().lstrip(".")
    if cur_ext == dst_ext:
        return src, ""
    stem = os.path.splitext(os.path.basename(src))[0]
    out = unique_path(os.path.join(out_dir, f"{stem}.{dst_ext}"))

    if fmt in ("jpg", "png"):
        cmd = [ffmpeg(), "-y", "-i", src, "-frames:v", "1"]
        if fmt == "jpg":
            cmd += ["-q:v", "2"]
        cmd.append(out)
        if _run(cmd).returncode == 0 and os.path.isfile(out):
            os.remove(src)
            return out, f"已转换为 {fmt.upper()}"
        return src, "图片格式转换失败，已保留原文件"

    if fmt in ("mp3", "m4a"):
        # 从任意音/视频提取音频
        base = [ffmpeg(), "-y", "-i", src, "-vn", "-map", "0:a:0?"]
        if fmt == "mp3":
            cmd = base + ["-c:a", "libmp3lame", "-q:a", "0", out]
        else:
            # m4a：源是 aac 系容器则直接拷贝，否则转 AAC
            if cur_ext in ("m4a", "mp4", "aac", "ts"):
                cmd = base + ["-c:a", "copy", out]
            else:
                cmd = base + ["-c:a", "aac", "-b:a", "192k", out]
        if _run(cmd).returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
            os.remove(src)
            return out, "已提取音频"
        return src, "音频提取失败，已保留原文件"

    if fmt in ("mp4", "mkv"):
        # 视频转封装：流复制（无损），mp4 加 faststart
        cmd = [ffmpeg(), "-y", "-i", src, "-c", "copy"]
        if fmt == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd.append(out)
        if _run(cmd).returncode == 0 and os.path.isfile(out):
            os.remove(src)
            return out, f"已无损转封装为 {fmt.upper()}"
        return src, f"转封装 {fmt.upper()} 失败（编码不兼容），已保留原文件"

    return src, ""
