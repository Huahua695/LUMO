"""直链下载引擎：原始字节流保存，天然无损；支持断点续传（HTTP Range）。"""
import os
import time
import urllib.parse
import urllib.request
import urllib.error

from .base_task import BaseTask
from .media_convert import convert_media
from .utils import DEFAULT_UA, filename_from_url, unique_path, now_tag, sanitize_name

CHUNK = 256 * 1024


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
    def __init__(self, task_id, url, save_dir, fmt="auto", parent=None):
        super().__init__(task_id, parent)
        self.url = url.strip()
        self.save_dir = save_dir
        self.fmt = (fmt or "auto").lower()

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
            # 1) 探测：文件名与总大小
            with self._open(origin) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                name = (_name_from_disposition(resp.headers.get("Content-Disposition", ""))
                        or filename_from_url(self.url)
                        or f"文件_{now_tag()}")
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
    if isinstance(e, urllib.error.HTTPError):
        return f"服务器返回错误 {e.code}（{e.reason}）"
    if isinstance(e, urllib.error.URLError):
        reason = getattr(e, "reason", e)
        return f"无法连接：{reason}"
    if isinstance(e, TimeoutError):
        return "连接超时，请检查网络后重试"
    return str(e) or e.__class__.__name__
