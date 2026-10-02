"""识别粘贴的链接应该交给哪个引擎处理。"""
import re
import urllib.parse

from .utils import DIRECT_EXTS, IMAGE_EXTS, VIDEO_EXTS
from urllib.parse import unquote, urlparse

AUDIO_EXTS = DIRECT_EXTS - IMAGE_EXTS - VIDEO_EXTS

# 排除集含中文标点与全部汉字：短链/BV号/数字ID 都是 ASCII，遇中文即断，
# 从源头避免「链接后紧跟中文（无空格粘贴）」把 URL 污染
URL_RE = re.compile(
    r"(?:m3u8dl://|https?://)[^\s，。；、）】》」』\"“”‘’<>『「\u4e00-\u9fff]+",
    re.IGNORECASE)


def extract_urls(text: str):
    """从任意粘贴文本提取 URL 列表（保持顺序、自动去重、容忍中文标点）。"""
    urls, seen = [], set()
    for m in URL_RE.findall(text or ""):
        u = m.rstrip(".,;:!?)'\"，。；：！？）】》”’")
        if len(u) <= len("http://a.bb"):
            continue
        # 非 ASCII 字符做百分号编码（对齐浏览器行为），
        # 避免带中文的直链在后续网络请求里以 ascii 编码崩溃
        u = urllib.parse.quote(u, safe=":/?#[]@!$&'()*+,;=%~")
        key = u.lower()
        if key not in seen:
            seen.add(key)
            urls.append(u)
    return urls


def detect_engine(url: str) -> str:
    """返回 'm3u8' | 'direct' | 'site'。"""
    u = (url or "").strip()
    low = u.lower()
    if not low:
        return "site"
    if low.startswith("m3u8dl://") or ".m3u8" in low or ".mpd" in low:
        return "m3u8"
    path = unquote(urlparse(u).path).lower()
    for ext in DIRECT_EXTS:
        if path.endswith(ext):
            return "direct"
    return "site"


def url_media_kind(url: str):
    """直链的媒体类别：'video' | 'audio' | 'image' | None。"""
    path = unquote(urlparse(url or "").path).lower()
    for ext, kind in (
        tuple((e, "video") for e in VIDEO_EXTS)
        + tuple((e, "audio") for e in AUDIO_EXTS)
        + tuple((e, "image") for e in IMAGE_EXTS)
    ):
        if path.endswith(ext):
            return kind
    return None


ENGINE_LABEL = {"m3u8": "m3u8/HLS 视频", "direct": "文件直链", "site": "网站视频"}
