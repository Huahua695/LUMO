"""识别粘贴的链接应该交给哪个引擎处理。"""
import re
import urllib.parse

from .utils import DIRECT_EXTS, IMAGE_EXTS, VIDEO_EXTS
from urllib.parse import unquote, urlparse

AUDIO_EXTS = DIRECT_EXTS - IMAGE_EXTS - VIDEO_EXTS

# 书签脚本用 URL fragment 携带来源页（Referer）：#sgref=<encodeURIComponent(页面URL)>
SGREF = "#sgref="

# 排除集含中文标点与全部汉字：短链/BV号/数字ID 都是 ASCII，遇中文即断，
# 从源头避免「链接后紧跟中文（无空格粘贴）」把 URL 污染
URL_RE = re.compile(
    r"(?:m3u8dl://|https?://)[^\s，。；、）】》」』\"“”‘’<>『「\u4e00-\u9fff]+",
    re.IGNORECASE)

# 无协议头时也允许识别的主机白名单。只收录 README 兼容性表里的站点 +
# 常见短链，不做成"任意裸域名都当链接"——否则普通英文句子里的
# "example.com" 会被误抓。新增站点时同步更新 README 的兼容性表。
BARE_HOSTS = (
    "b23.tv", "bili2233.cn", "bilibili.com",
    "douyin.com", "iesdouyin.com",
    "weibo.com", "weibo.cn", "t.cn",
    "xiaohongshu.com", "xhslink.com",
    "kuaishou.com", "chenzhongtech.com",
    "ixigua.com", "haokan.baidu.com",
    "youtube.com", "youtu.be",
    "x.com", "twitter.com", "t.co",
)

# 裸主机匹配：白名单主机（可带 www./m. 前缀）+ 后续非空白非标点串。
# (?<![\w./-]) 负向断言必须有：避免匹配到已有协议头的 URL 尾部
# （https://www.bilibili.com/... 里的 www.bilibili.com/... 片段）
BARE_RE = re.compile(
    r"(?<![\w./-])(?:www\.|m\.)?(?:"
    + "|".join(re.escape(h) for h in BARE_HOSTS)
    + r")/[^\s，。；、）】》」』\"“”‘’<>『「\u4e00-\u9fff]*",
    re.IGNORECASE)

# 纯 BV 号（B 站视频编号，BV + 10 位字母数字）
BV_RE = re.compile(r"(?<![0-9A-Za-z])BV[0-9A-Za-z]{10}(?![0-9A-Za-z])")


def extract_urls(text: str):
    """从任意粘贴文本提取 URL 列表（保持顺序、自动去重、容忍中文标点）。

    三趟：带协议头的 URL → 无协议头的白名单主机 → 纯 BV 号。
    归一化后统一去重，因此 "BV1xx" 与含同一 BV 号的完整链接不会重复。
    """
    text = text or ""
    urls, seen = [], set()

    def add(raw: str):
        u = raw.rstrip(".,;:!?)'\"，。；：！？）】》”’")
        if len(u) <= len("http://a.bb"):
            return
        # 非 ASCII 字符做百分号编码（对齐浏览器行为），
        # 避免带中文的直链在后续网络请求里以 ascii 编码崩溃
        u = urllib.parse.quote(u, safe=":/?#[]@!$&'()*+,;=%~")
        key = u.lower()
        if key not in seen:
            seen.add(key)
            urls.append(u)

    for m in URL_RE.findall(text):
        add(m)
    for m in BARE_RE.findall(text):
        add("https://" + m)
    for m in BV_RE.findall(text):
        add(f"https://www.bilibili.com/video/{m}")
    return urls


def split_referer(url: str) -> tuple[str, str]:
    """拆出书签脚本用 #sgref= 携带的来源页。返回 (纯媒体URL, referer)。

    没有 sgref 片段时 referer 为 ''，纯媒体URL 即原串——
    因此对既有全部链接形态是完全透明的。fragment 不会发给服务器，
    是嗅探链接逐条自带 Referer 的带外通道。
    """
    url = url or ""
    i = url.find(SGREF)
    if i < 0:
        return url, ""
    return url[:i], urllib.parse.unquote(url[i + len(SGREF):])


def detect_engine(url: str) -> str:
    """返回 'm3u8' | 'direct' | 'site'。"""
    u, _ref = split_referer((url or "").strip())  # 先剥离 #sgref=：Referer
    low = u.lower()                               # 里的 .m3u8/.mpd 字样会误导路由
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
    u, _ref = split_referer(url)  # 同 detect_engine：先剥离再按 path 后缀匹配
    path = unquote(urlparse(u or "").path).lower()
    for ext, kind in (
        tuple((e, "video") for e in VIDEO_EXTS)
        + tuple((e, "audio") for e in AUDIO_EXTS)
        + tuple((e, "image") for e in IMAGE_EXTS)
    ):
        if path.endswith(ext):
            return kind
    return None


ENGINE_LABEL = {"m3u8": "m3u8/HLS 视频", "direct": "文件直链", "site": "网站视频"}
