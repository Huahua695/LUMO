"""m3u8/HLS 下载引擎：调用本地已编译好的 N_m3u8DL-CLI。
支持仅音频下载（--enableAudioOnly）与 MP3/M4A 后转换。"""
import hashlib
import os
import re
import subprocess
import threading
import time

from .base_task import BaseTask
from .errors import friendly_error
from .paths import m3u8dl_exe
from .proc import CREATE_NO_WINDOW, stderr_target
from .utils import now_tag
from .media_convert import convert_media

PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

RESULT_EXTS = (".mp4", ".mkv", ".ts", ".flv", ".m4a", ".aac")


def default_save_name(url: str, audio_only: bool = False) -> str:
    """无显式名字时的兜底名：时间戳 + URL 哈希。

    哈希不能省：批量粘贴多个 m3u8 时任务毫秒级同秒启动，只靠秒级时间戳
    会生成完全相同的 saveName，多个 N_m3u8DL-CLI 进程写进同一目录互相
    覆盖分片，最终合并出损坏文件。"""
    tag = hashlib.md5(url.encode("utf-8")).hexdigest()[:6]
    return (f"音频_{now_tag()}_{tag}" if audio_only
            else f"视频_{now_tag()}_{tag}")


class M3u8DownloadTask(BaseTask):
    def __init__(self, task_id, url, save_dir, name="", fmt="auto", parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.save_dir = save_dir
        self.name = name
        self.fmt = (fmt or "auto").lower()
        self.audio_only = self.fmt in ("mp3", "m4a")

    def run(self):
        save_name = self.name or default_save_name(self.url, self.audio_only)
        cmd = [
            m3u8dl_exe(), self.url,
            "--workDir", self.save_dir,
            "--saveName", save_name,
            "--enableDelAfterDone",
            "--enableMuxFastStart",
        ]
        if self.audio_only:
            cmd.append("--enableAudioOnly")
        last_emit = [0.0]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=stderr_target(),
                creationflags=CREATE_NO_WINDOW,
            )
            self._emit(event="started", name=save_name)

            def pump(pipe):
                buf = b""
                while True:
                    b = pipe.read(256)
                    if not b:
                        break
                    buf += b
                    if len(buf) > 8192:
                        buf = buf[-2048:]
                    text = buf.decode("utf-8", errors="ignore")
                    m = PCT_RE.findall(text)
                    now = time.time()
                    if m and now - last_emit[0] >= 0.3:
                        last_emit[0] = now
                        try:
                            self.progress(float(m[-1]), stage="下载中")
                        except ValueError:
                            pass

            t = threading.Thread(target=pump, args=(self._proc.stdout,), daemon=True)
            t.start()
            rc = self._proc.wait()
            t.join(timeout=2)
            if self._cancelled:
                self.error("已取消", cancelled=True)
                return
            if rc != 0:
                self.error(f"N_m3u8DL-CLI 退出码 {rc}，链接可能无效或已失效")
                return
            out = _find_result(self.save_dir, save_name)
            if not out:
                self.error("下载完成但未找到合并后的文件")
                return
            if self.fmt in ("mp3", "m4a") or self.audio_only:
                self.progress(None, stage="音频转换中")
                out, note = convert_media(out, self.fmt if self.fmt != "auto" else "m4a",
                                          self.save_dir)
            self.progress(100, stage="完成")
            self.done(path=out)
        except Exception as e:
            self.error(friendly_error(e, "m3u8 下载失败"))


def _find_result(save_dir: str, save_name: str) -> str:
    cand = os.path.join(save_dir, save_name + ".mp4")
    if os.path.isfile(cand):
        return cand
    for ext in RESULT_EXTS:
        p = os.path.join(save_dir, save_name + ext)
        if os.path.isfile(p):
            return p
    best, best_t = "", 0.0
    for root, _dirs, files in os.walk(save_dir):
        for fn in files:
            if fn.lower().endswith(RESULT_EXTS):
                p = os.path.join(root, fn)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                if mt > best_t and os.path.getsize(p) > 100 * 1024:
                    best, best_t = p, mt
    return best
