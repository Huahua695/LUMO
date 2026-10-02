"""网站视频下载引擎：yt-dlp Python API（B站/YouTube/抖音/推特等数千个站点）。
支持画质/分辨率选择、保存格式选择、链接解析预览（标题/封面/真实分辨率/播放列表）。"""
import os
import tempfile
import threading
import time

from .base_task import BaseTask
from .errors import friendly_error
from .paths import tools_dir
from .utils import DEFAULT_UA

QUALITY_HEIGHTS = {"1080p": 1080, "720p": 720, "480p": 480}
AUDIO_FORMATS = ("mp3", "m4a")
MAX_PLAYLIST = 100
# 下载停滞判定：超过该秒数没有任何进度/后处理事件则报超时（大文件正常
# 下载每 0.4s 就有一次 hook 回调，停滞只可能是网络断了或需要代理）
DOWNLOAD_STALL = 90


def _log_raw(task_name: str, e: BaseException):
    """把翻译前的英文原文+堆栈写入日志（friendly_error 只给用户中文壳）。"""
    try:
        from .proc import append_log
        import traceback
        append_log(f"[{task_name}] raw={e!r}\n{traceback.format_exc()}")
    except Exception:
        pass


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
    """链接解析：单视频返回标题/封面/时长/真实分辨率；播放列表返回条目清单。

    解析有 25 秒整体超时（yt-dlp 内部 retries 会把单次 socket 超时放大到
    两分钟，光靠 socket_timeout 管不住总时长）：解析放到子线程 join，
    超时即报错返回，残留线程随进程退出。
    """

    PROBE_TIMEOUT = 25  # 秒

    def __init__(self, task_id, url, cookie_file="", proxy="", parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.cookie_file = cookie_file or ""
        self.proxy = proxy or ""

    def run(self):
        # 抖音：yt-dlp 的 DouyinIE 需要 cookie（web API 有签名），无 cookie 必失败。
        # 这里走移动端分享页解析（app/douyin.py），失败则回退 yt-dlp 兜底。
        from .douyin import is_douyin, resolve
        if is_douyin(self.url):
            try:
                info = resolve(self.url)
            except Exception as e:
                _log_raw("ProbeTask", e)
                info = None
            if info:
                thumb = _download_thumbnail(info.get("cover") or "")
                self.done(kind="video",
                          title=info.get("title") or "",
                          uploader=info.get("author") or "",
                          duration=info.get("duration") or 0,
                          thumbnail=thumb,
                          formats=[],
                          douyin_url=info.get("play_url"),
                          douyin_title=info.get("title") or "")
                return
        import yt_dlp
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",  # 播放列表只取条目清单，不逐个解析
            "socket_timeout": 15,
            "retries": 2,  # 探测别重试太狠，配合整体超时
        }
        if self.cookie_file and os.path.isfile(self.cookie_file):
            opts["cookiefile"] = self.cookie_file
        if self.proxy:
            opts["proxy"] = self.proxy

        result: dict = {}

        def _extract():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result["info"] = ydl.extract_info(self.url, download=False)
            except Exception as e:  # noqa: BLE001 - 统一翻译
                result["err"] = e

        worker = threading.Thread(target=_extract, daemon=True)
        worker.start()
        worker.join(self.PROBE_TIMEOUT)
        if worker.is_alive():
            self.error(f"该站点 {self.PROBE_TIMEOUT} 秒内无响应，"
                       "可能需要代理（设置 → 网络）或已失效")
            return
        if "err" in result:
            _log_raw("ProbeTask", result["err"])
            self.error(friendly_error(result["err"], "解析失败"))
            return
        info = result.get("info")
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
                 format_id=None, cookie_file="", proxy="", parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.save_dir = save_dir
        self.quality = quality or "best"
        self.fmt = (fmt or "auto").lower()
        self.format_id = format_id
        self.cookie_file = cookie_file or ""
        self.proxy = proxy or ""

    def run(self):
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled, DownloadError

        self._final = ""
        last = {"t": 0.0}
        last_event = {"t": time.time()}  # 停滞看门狗用

        def throttle():
            now = time.time()
            if now - last["t"] >= 0.4:
                last["t"] = now
                return True
            return False

        def progress_hook(d):
            if self._cancelled:
                raise DownloadCancelled()
            last_event["t"] = time.time()
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
            last_event["t"] = time.time()
            info = d.get("info_dict") or {}
            fp = info.get("filepath") or info.get("filename")
            if fp:
                self._final = fp
            if throttle():
                self.progress(None, stage=f"后处理：{d.get('postprocessor', '')}")

        def stall_watchdog():
            """下载停滞超时：socket 卡死时 hook 不会再被调用，只能从外部判。"""
            while not self._terminal_emitted:
                if time.time() - last_event["t"] > DOWNLOAD_STALL:
                    self._cancelled = True  # hook 恢复时自行抛 DownloadCancelled
                    self.error("下载停滞超过 90 秒（网络不稳定或需要代理），已停止。"
                               "可在「设置 → 网络」配置代理后重试")
                    return
                time.sleep(2)

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
        if self.cookie_file and os.path.isfile(self.cookie_file):
            opts["cookiefile"] = self.cookie_file
        if self.proxy:
            opts["proxy"] = self.proxy
        opts.update(build_ytdlp_opts(self.quality, self.fmt, self.format_id))
        try:
            self._emit(event="started", name=self.url[:80])
            watchdog = threading.Thread(target=stall_watchdog, daemon=True)
            watchdog.start()
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            if self._cancelled and not self._terminal_emitted:
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
            _log_raw("YtdlpTask", e)
            self.error(friendly_error(e, "下载失败"))
        except Exception as e:
            _log_raw("YtdlpTask", e)
            self.error(friendly_error(e, "下载失败"))


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
