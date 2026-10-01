"""直链下载引擎：原始字节流保存，天然无损；支持断点续传（HTTP Range）。"""
import os
import time
import urllib.parse
import urllib.request
import urllib.error

from .base_task import BaseTask
from .errors import friendly_error
from .media_convert import convert_media
from .utils import DEFAULT_UA, filename_from_url, unique_path, now_tag, sanitize_name

CHUNK = 256 * 1024

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
_EXT_BY_CONTENT = {
    "video/mp4": ".mp4", "video/webm": ".webm", "video/x-matroska": ".mkv",
    "video/quicktime": ".mov", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
    "audio/aac": ".aac", "image/jpeg": ".jpg", "image/png": ".png",
    "image/webp": ".webp",
}


def _ext_for_content(ctype: str) -> str:
    """按响应 Content-Type 补文件扩展名（仅精确映射，宁缺勿错）。"""
    return _EXT_BY_CONTENT.get((ctype or "").split(";")[0].strip().lower(), "")


def _name_from_disposition(cd: str) -> str:
    if not cd:
        return ""
    try:
        if "filename*=" in cd:
            raw = cd.split("filename*=")[-1].split(";")[0].strip()
            enc, _, data = raw.partition("''")
            return sanitize_name(urllib.parse.unquote(data, encoding=enc or "utf-8"))
        if "filename=" in cd:
            raw = cd.split("filename=")[-1].split(";")[0].strip().strip('"')
            return sanitize_name(raw)
    except Exception:
        pass
    return ""


class DirectDownloadTask(BaseTask):
    def __init__(self, task_id, url, save_dir, fmt="auto", name="",
                 parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.save_dir = save_dir
        self.fmt = (fmt or "auto").lower()
        self._name_hint = (name or "").strip()  # 调用方给定的文件名（如抖音标题）

    def _open(self, referer, range_start=None):
        h = {"User-Agent": DEFAULT_UA, "Referer": referer, "Accept": "*/*"}
        if range_start is not None:
            h["Range"] = f"bytes={range_start}-"
        return urllib.request.urlopen(
            urllib.request.Request(self.url, headers=h), timeout=30)

    def run(self):
        tmp = ""
        final = ""
        note = ""
        try:
            origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(self.url))
            # 1) 探测：内容类型 / 文件名与总大小
            with self._open(origin) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0]
                ctype = ctype.strip().lower()
                if ctype in HTML_CONTENT_TYPES:
                    # 网站返回了反爬验证页/失效页——绝不能存成假视频
                    raise RuntimeError(
                        "返回的是网页而不是媒体文件（链接可能已失效，"
                        "或触发了网站的风控验证），请稍后重试")
                name = (self._name_hint
                        or _name_from_disposition(resp.headers.get("Content-Disposition", ""))
                        or filename_from_url(self.url)
                        or f"文件_{now_tag()}")
                if self._name_hint and not os.path.splitext(name)[1]:
                    # 调用方给的名字不带扩展名（如抖音标题）时按类型补全
                    name += _ext_for_content(ctype)
            final = unique_path(os.path.join(self.save_dir, name))
            tmp = final + ".part"

            # 2) 若存在半成品则尝试 Range 续传
            done = 0
            resumed = False
            if os.path.exists(tmp):
                have = os.path.getsize(tmp)
                if have > 0:
                    try:
                        resp2 = self._open(origin, range_start=have)
                    except urllib.error.HTTPError as e:
                        if e.code == 416:
                            # 断点超出文件大小：半成品不可信，删掉重下
                            os.remove(tmp)
                            resp2 = None
                        else:
                            raise
                    if resp2 is not None:
                        with resp2:
                            if getattr(resp2, "status", 200) == 206:
                                total = have + int(resp2.headers.get("Content-Length") or 0)
                                done = have
                                resumed = True
                            else:
                                total = int(resp2.headers.get("Content-Length") or 0)

            # 3) 打开正式下载流
            if resumed:
                resp3 = self._open(origin, range_start=done)
            else:
                done = 0
                resp3 = self._open(origin)

            self._emit(event="started", name=os.path.basename(final),
                       resumed=resumed)
            mark_t = time.time()
            mark_done = done
            last_emit = 0.0
            with open(tmp, "ab" if resumed else "wb") as f, resp3 as resp:
                if not resumed:
                    total = int(resp.headers.get("Content-Length") or total)
                while True:
                    if self._cancelled:
                        self.error("已取消（进度已保留，重新下载同一链接可续传）",
                                   cancelled=True)
                        return
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - mark_t >= 0.5:
                        speed = (done - mark_done) / (now - mark_t)
                        mark_t, mark_done = now, done
                        if now - last_emit >= 0.4:
                            last_emit = now
                            pct = done * 100.0 / total if total else None
                            self.progress(pct, done=done, total=total, speed=speed)
            if self._cancelled:
                self.error("已取消（进度已保留，重新下载同一链接可续传）",
                           cancelled=True)
                return
            if total and done != total:
                raise IOError(f"下载不完整：{done}/{total} 字节")
            self.progress(100, done=done, total=total or done, speed=0)
            os.replace(tmp, final)
            tmp = ""
            # 保存格式选择：必要时后处理转换（视频转封装/音频提取/图片转格式）
            if self.fmt != "auto":
                self.progress(None, stage="转换格式")
                final, note = convert_media(final, self.fmt, self.save_dir)
            self.done(path=final, note=note)
        except Exception as e:
            self.error(_friendly(e))
        # 取消/失败时保留 .part 供下次续传；成功时上面已改名


def _friendly(e: Exception) -> str:
    return friendly_error(e, "下载失败")


class DouyinDownloadTask(DirectDownloadTask):
    """抖音分享链接 → 解析无水印直链 → 直链下载。

    probe 已解析出 play_url 时直接下载；否则在线程内解析
    （app/douyin.py，失败信息明确，不再回退 yt-dlp）。
    下载前预检 play_url：抖音播放链接带时效签名，过期或风控时
    服务器返回 200 + HTML 验证页——此时重新解析一次再下（共两轮）。
    """

    def __init__(self, task_id, url, save_dir, fmt="auto",
                 play_url="", name="", parent=None):
        super().__init__(task_id, url, save_dir, fmt=fmt, name=name, parent=parent)
        self._play_url = (play_url or "").strip()

    def _play_looks_html(self) -> bool:
        """预检播放链接：True = 已失效，需要重新解析拿新鲜签名链接。

        失效的两种表现：返回 HTML 验证页；或直接 403/410（CDN 签名过期，
        不返回页面直接拒绝）。403 是用户实际遇到的坑。
        """
        try:
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                head = r.read(16)
        except urllib.error.HTTPError as e:
            return e.code in (403, 410)
        except Exception:
            return False  # 网络错误交给直链引擎去报
        return ("text/html" in ctype
                or head.lstrip()[:1] == b"<")

    def run(self):
        for _attempt in range(2):
            if not self._play_url:
                self._emit(event="started", name="抖音解析中…", resumed=False)
                try:
                    from .douyin import resolve
                    info = resolve(self.url)
                except Exception as e:
                    self.error(f"抖音解析失败：{e}")
                    return
                self.url = info["play_url"]
                self._name_hint = info["title"]
            if not self._play_looks_html():
                break
            # 链接失效/风控：丢弃当前链接，重新解析拿新鲜签名
            self._play_url = ""
        else:
            self.error("抖音下载失败：播放链接已失效（两次解析均失败），"
                       "请稍后重试")
            return
        super().run()
