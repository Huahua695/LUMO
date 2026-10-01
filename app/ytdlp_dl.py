"""网站视频下载引擎：yt-dlp Python API（B站/YouTube/抖音/推特等数千个站点）。
支持画质/分辨率选择、保存格式选择、链接解析预览（标题/封面/真实分辨率/播放列表）。"""
import os
import tempfile
import time

from .base_task import BaseTask
from .paths import tools_dir
from .utils import DEFAULT_UA

QUALITY_HEIGHTS = {"1080p": 1080, "720p": 720, "480p": 480}
AUDIO_FORMATS = ("mp3", "m4a")
MAX_PLAYLIST = 100


def build_ytdlp_opts(quality: str, fmt: str, format_id=None) -> dict:
    """(画质, 保存格式, 具体画质ID) -> yt-dlp 关键选项 dict。纯函数，便于测试。

    quality: best | 1080p | 720p | 480p | audio
    fmt:     auto | mp4 | mkv | mp3 | m4a
    format_id: 解析卡片选中的具体画质（优先级高于 quality 预设）
    """
    opts: dict = {}
    audio_codec = fmt if fmt in AUDIO_FORMATS else None
    if quality == "audio" or audio_codec:
        # 仅音频：选最佳音轨，再用 ffmpeg 提取/转码
        opts["format"] = "ba/b"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_codec or "mp3",
            "preferredquality": "0",
        }]
        return opts
    if format_id:
        # 解析卡片选中的具体格式：该画质视频 + 最佳音轨，合并封装
        opts["format"] = f"{format_id}+bestaudio/best"
    else:
        height = QUALITY_HEIGHTS.get(quality)
        if height:
            opts["format"] = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            opts["format"] = "bv*+ba/b"
    if fmt in ("mp4", "mkv"):
        opts["merge_output_format"] = fmt
    return opts


def dedupe_formats(raw_formats) -> list[dict]:
    """把 yt-dlp 的 formats 列表整理成按高度去重的画质选项（每档取最高码率）。
    返回 [{format_id, label, size}]，按高度降序。纯函数，便于测试。"""
    best_by_height: dict = {}
    for f in raw_formats or []:
        if not isinstance(f, dict):
            continue
        height = f.get("height")
        if not height or f.get("vcodec", "none") == "none":
            continue
        tbr = f.get("tbr") or 0
        if height not in best_by_height or tbr > (best_by_height[height].get("tbr") or 0):
            best_by_height[height] = f
    out = []
    for height in sorted(best_by_height, reverse=True):
        f = best_by_height[height]
        size = f.get("filesize") or f.get("filesize_approx")
        out.append({
            "format_id": f.get("format_id"),
            "label": f"{height}p" + (f"{f['fps']:.0f}帧" if f.get("fps") and f["fps"] > 45 else ""),
            "height": height,
            "size": size,
        })
    return out


def _download_thumbnail(url: str) -> str:
    """下载封面到临时文件，失败返回 ''。"""
    if not url:
        return ""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
        data = urllib.request.urlopen(req, timeout=15).read()
        fd, path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path
    except Exception:
        return ""


class ProbeTask(BaseTask):
    """链接解析：单视频返回标题/封面/时长/真实分辨率；播放列表返回条目清单。"""

    def __init__(self, task_id, url, parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()

    def run(self):
        import yt_dlp
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",  # 播放列表只取条目清单，不逐个解析
            "socket_timeout": 15,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
        except Exception as e:
            msg = str(e)
            if "Unsupported URL" in msg:
                msg = "不支持的网站链接"
            elif "Sign in" in msg or "login" in msg.lower() or "会员" in msg:
                msg = "该内容需要登录/会员，只能按默认画质尝试下载"
            self.error(msg)
            return
        if not info:
            self.error("未能解析出视频信息")
            return
        if info.get("_type") == "playlist":
            entries = []
            for entry in (info.get("entries") or []):
                u = entry.get("url") or entry.get("webpage_url")
                if u:
                    entries.append({"title": entry.get("title") or "", "url": u})
                if len(entries) >= MAX_PLAYLIST:
                    break
            if not entries:
                self.error("播放列表为空或无法读取条目")
                return
            self.done(kind="playlist", title=info.get("title") or "播放列表",
                      entries=entries,
                      truncated=(info.get("playlist_count") or len(entries)) > len(entries))
            return
        thumb = _download_thumbnail(info.get("thumbnail"))
        self.done(kind="video",
                  title=info.get("title") or "",
                  uploader=info.get("uploader") or info.get("channel") or "",
                  duration=info.get("duration") or 0,
                  thumbnail=thumb,
                  formats=dedupe_formats(info.get("formats")))


class YtdlpTask(BaseTask):
    def __init__(self, task_id, url, save_dir, quality="best", fmt="auto",
                 format_id=None, parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.save_dir = save_dir
        self.quality = quality or "best"
        self.fmt = (fmt or "auto").lower()
        self.format_id = format_id

    def run(self):
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled, DownloadError

        self._final = ""
        last = {"t": 0.0}

        def throttle():
            now = time.time()
            if now - last["t"] >= 0.4:
                last["t"] = now
                return True
            return False

        def progress_hook(d):
            if self._cancelled:
                raise DownloadCancelled()
            st = d.get("status")
            if st == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                speed = d.get("speed") or 0
                if throttle() or total == 0:
                    self.progress(done * 100.0 / total if total else None,
                                  done=done, total=total, speed=speed, stage="下载中")
            elif st == "finished":
                self.progress(None, stage="合并封装中")

        def pp_hook(d):
            if self._cancelled:
                raise DownloadCancelled()
            info = d.get("info_dict") or {}
            fp = info.get("filepath") or info.get("filename")
            if fp:
                self._final = fp
            if throttle():
                self.progress(None, stage=f"后处理：{d.get('postprocessor', '')}")

        opts: dict = {
            "format": "bv*+ba/b",
            "outtmpl": os.path.join(self.save_dir, "%(title).100s.%(ext)s"),
            "paths": {"home": self.save_dir},
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [pp_hook],
            "ffmpeg_location": tools_dir(),
            "windowsfilenames": True,
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 4,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 20,
        }
        opts.update(build_ytdlp_opts(self.quality, self.fmt, self.format_id))
        try:
            self._emit(event="started", name=self.url[:80])
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            if self._cancelled:
                self.error("已取消", cancelled=True)
                return
            final = self._final
            if final and not os.path.isfile(final):
                final = _newest_file(self.save_dir, time.time() - 3600 * 6)
            if not final:
                final = _newest_file(self.save_dir, 0)
            self.progress(100, stage="完成")
            self.done(path=final)
        except DownloadCancelled:
            self.error("已取消", cancelled=True)
        except DownloadError as e:
            msg = str(e)
            if "Unsupported URL" in msg:
                msg = "不支持的网站链接，可尝试直接复制视频文件地址"
            elif "Sign in" in msg or "login" in msg.lower():
                msg = "该内容需要登录才能观看，暂不支持"
            self.error(msg)
        except Exception as e:
            self.error(str(e) or e.__class__.__name__)


def _newest_file(folder: str, min_t: float) -> str:
    best, best_t = "", 0.0
    for fn in os.listdir(folder):
        p = os.path.join(folder, fn)
        if os.path.isfile(p) and not fn.endswith(".part"):
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if mt > best_t and mt >= min_t:
                best, best_t = p, mt
    return best
