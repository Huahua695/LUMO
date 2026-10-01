"""简单视频剪切引擎：精确模式（重编码，帧级准确）/ 无损模式（流复制，关键帧对齐）。"""
import os
import re
import subprocess
import threading
import time

from .base_task import BaseTask
from .paths import ffmpeg, ffprobe
from .proc import CREATE_NO_WINDOW, stderr_target
from .utils import unique_path, sanitize_name


def probe_duration(src: str) -> tuple[float, tuple[int, int], bool]:
    """返回 (时长秒, 视频宽高, 是否有音频轨)。失败时 (0, (0,0), False)。"""
    try:
        r = subprocess.run(
            [ffprobe(), "-v", "error", "-show_entries",
             "stream=width,height,codec_type:format=duration", "-of", "json", src],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=30)
        import json
        info = json.loads(r.stdout or b"{}")
        dur = float((info.get("format") or {}).get("duration") or 0)
        wh = (0, 0)
        has_audio = False
        for s in info.get("streams", []):
            if s.get("width") and wh == (0, 0):
                wh = (int(s["width"]), int(s["height"]))
            if s.get("codec_type") == "audio":
                has_audio = True
        return dur, wh, has_audio
    except Exception:
        return 0.0, (0, 0), False


def parse_time(text: str) -> float | None:
    """'83.5' / '1:23.5' / '1:23:04' -> 秒；失败返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) > 3:
                return None
            t = 0.0
            for p in parts:
                t = t * 60 + float(p or 0)
            return t
        return float(text)
    except ValueError:
        return None


def fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(int(m), 60)
    if h:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


def fmt_time_file(sec: float) -> str:
    """文件名安全版（Windows 文件名不能含冒号）。"""
    sec = max(0.0, float(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(int(m), 60)
    if h:
        return f"{h}h{m:02d}m{s:04.1f}s"
    return f"{m:02d}m{s:04.1f}s"


class CutTask(BaseTask):
    def __init__(self, task_id, src, start, end, mode, audio_fmt=None,
                 parent=None):
        super().__init__(task_id, parent)
        self.src = src
        # 注意：不能叫 self.start/self.end，会覆盖 QThread.start()
        self.t_start = float(start)
        self.t_end = float(end)
        self.mode = mode  # accurate | lossless
        self.audio_fmt = audio_fmt  # None | 'mp3' | 'm4a'（提取音频）

    def run(self):
        src = self.src
        if not os.path.isfile(src):
            self.error("源文件不存在")
            return
        dur, _wh, has_audio = probe_duration(src)
        if dur <= 0:
            self.error("无法读取视频信息（格式不支持或文件损坏）")
            return
        if self.audio_fmt and not has_audio:
            self.error("该文件没有音频轨，无法提取音频")
            return
        start = max(0.0, min(self.t_start, dur - 0.05))
        end = max(start + 0.05, min(self.t_end, dur))
        duration = end - start
        full_range = start <= 0.02 and end >= dur - 0.02

        stem = sanitize_name(os.path.splitext(os.path.basename(src))[0])
        out_dir = os.path.dirname(src)

        if self.audio_fmt:
            ext = self.audio_fmt
            tag = "" if full_range else \
                f"_{fmt_time_file(start)}-{fmt_time_file(end)}"
            out = unique_path(os.path.join(out_dir, f"{stem}_音频{tag}.{ext}"))
            if full_range:
                head = [ffmpeg(), "-y", "-i", src]
            else:
                head = [ffmpeg(), "-y", "-ss", f"{start:.3f}", "-i", src,
                        "-t", f"{duration:.3f}"]
            cmd = head + ["-vn", "-map", "0:a:0?"]
            if ext == "mp3":
                cmd += ["-c:a", "libmp3lame", "-q:a", "0"]
            else:  # m4a：源是 aac 系容器则直接拷贝，否则转 AAC
                src_ext = os.path.splitext(src)[1].lower()
                if src_ext in (".m4a", ".mp4", ".aac", ".ts", ".mov"):
                    cmd += ["-c:a", "copy"]
                else:
                    cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            tag = "剪切" if self.mode == "accurate" else "剪切无损"
            out = unique_path(os.path.join(
                out_dir,
                f"{stem}_{tag}_{fmt_time_file(start)}-{fmt_time_file(end)}.mp4"))
            head = [ffmpeg(), "-y", "-ss", f"{start:.3f}", "-i", src,
                    "-t", f"{duration:.3f}",
                    "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?"]
            if self.mode == "accurate":
                cmd = head + ["-c:v", "libx264", "-crf", "17", "-preset", "medium",
                              "-pix_fmt", "yuv420p", "-c:a", "copy",
                              "-movflags", "+faststart"]
            else:
                cmd = head + ["-c", "copy", "-avoid_negative_ts", "make_zero",
                              "-movflags", "+faststart"]
        cmd += ["-progress", "pipe:1", "-nostats", out]

        proc = subprocess.Popen(
            cmd, creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE, stderr=stderr_target())
        self._proc = proc
        pipe = proc.stdout

        def pump():
            if pipe is None:
                return
            last = 0.0
            for raw in iter(pipe.readline, b""):
                line = raw.decode("utf-8", errors="ignore").strip()
                m = re.match(r"out_time_(us|ms)=(\d+)", line)
                if not m or duration <= 0:
                    continue
                us = int(m.group(2)) * (1 if m.group(1) == "us" else 1000)
                now = time.time()
                if now - last >= 0.4:
                    last = now
                    self.progress(min(100.0, us / 1e6 * 100.0 / duration),
                                  stage="提取音频中" if self.audio_fmt else "剪切中",
                                  done=fmt_time(us / 1e6),
                                  total=fmt_time(duration))

        try:
            t = threading.Thread(target=pump, daemon=True)
            t.start()
            rc = proc.wait()
            t.join(timeout=2)
            if self._cancelled:
                self.error("已取消", cancelled=True)
                return
            if rc != 0 or not os.path.isfile(out):
                hint = "，无损模式对某些编码不兼容，可改用「精确剪切」" \
                    if (not self.audio_fmt and self.mode == "lossless") else ""
                self.error(f"处理失败（退出码 {rc}）{hint}")
                return
            self.progress(100, stage="完成", done=fmt_time(duration),
                          total=fmt_time(duration))
            self.done(path=out)
        except Exception as e:
            self.error(str(e) or e.__class__.__name__)
