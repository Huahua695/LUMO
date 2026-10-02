"""抖音链接解析：短链展开 → 移动端分享页 → 无水印直链。

yt-dlp 的 DouyinIE 走 web detail API，需要浏览器 cookie（有签名校验），
无 cookie 报 "Fresh cookies are needed"。这里走移动端分享页：
1) v.douyin.com 短链 302 展开出视频 ID；
2) 注册一个 ttwid cookie（字节公开接口，无需签名）——分享页的 SSR
   只对带 ttwid 的移动 UA 注入视频数据（实测 Safari/无 cookie 均为空壳）；
3) GET https://www.iesdouyin.com/share/video/{id}/ 解析内嵌
   window._ROUTER_DATA → videoInfoRes.item_list[0].video.play_addr；
4) playwm → play 去水印、ratio 提到 1080p，302 到无水印 CDN mp4。
解析失败时调用方回退 yt-dlp。
"""
import json
import re
import urllib.request

# 分享页的 SSR 数据只对移动 Edge UA 注入（实测 Safari/桌面 UA 均为空壳）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)

SHORT_RE = re.compile(r"https?://v\.douyin\.com/[\w-]+/?", re.IGNORECASE)

# 抖音是国内站点：所有请求强制直连，不被系统代理/TUN 带去绕远路
DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ID_RE = re.compile(r"(?:video|note)/(\d+)")
# 精选/发现/主页弹窗等形式：ID 在查询参数里（www.douyin.com/jingxuan?modal_id=xxx）
MODAL_RE = re.compile(r"[?&]modal_id=(\d+)")
ROUTER_RE = re.compile(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})[\s;]*</script>", re.S)
TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"

_ttwid = ""


class DouyinError(Exception):
    pass


def is_douyin(url: str) -> bool:
    u = (url or "").lower()
    return "douyin.com" in u or "iesdouyin.com" in u


def extract_aweme_id(url: str) -> str:
    """从各种抖音链接形态里取视频 ID；取不到返回空串。

    覆盖：/video/{id}、/note/{id}、?modal_id={id}（精选/发现/主页弹窗）。
    """
    m = ID_RE.search(url or "") or MODAL_RE.search(url or "")
    return m.group(1) if m else ""


def build_play_url(raw: str) -> str:
    """play_addr 首地址 → 无水印 1080p（playwm 去水印、ratio 提到最高）。"""
    u = raw.replace("playwm", "play")
    return re.sub(r"ratio=\d+p", "ratio=1080p", u)


def _get_ttwid(timeout: int = 15) -> str:
    """注册 ttwid 设备令牌（字节公开接口，无需签名）；失败返回空串。"""
    global _ttwid
    if _ttwid:
        return _ttwid
    try:
        body = json.dumps({
            "region": "cn", "aid": 1768, "needFid": False,
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https", "union": True,
        }).encode()
        req = urllib.request.Request(
            TTWID_URL, data=body,
            headers={"Content-Type": "application/json", "User-Agent": MOBILE_UA})
        with DIRECT_OPENER.open(req, timeout=timeout) as r:
            for c in (r.headers.get_all("Set-Cookie") or []):
                if c.startswith("ttwid="):
                    _ttwid = c.split(";")[0].split("=", 1)[1]
                    break
    except Exception:
        _ttwid = ""
    return _ttwid


def expand_short(url: str, timeout: int = 15) -> str:
    """v.douyin.com 短链 → 跟随 302 后的最终地址（含视频 ID）。"""
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
    try:
        with DIRECT_OPENER.open(req, timeout=timeout) as resp:
            final = resp.geturl()
            resp.read(64)
    except Exception as e:
        raise DouyinError(f"短链打开失败：{e}") from e
    return final


def extract_router_data(html: str) -> dict:
    m = ROUTER_RE.search(html)
    if not m:
        raise DouyinError("分享页里没有视频数据（可能接口已变）")
    try:
        return json.loads(m.group(1).rstrip(";"))
    except ValueError as e:
        raise DouyinError("分享页数据解析失败") from e


def parse_share_html(html: str) -> dict:
    """从分享页 HTML 解析视频信息（纯函数，便于离线测试）。"""
    data = extract_router_data(html)
    # loaderData 的键是固定模板键："video_(id)/page" / "note_(id)/page"
    loader = data.get("loaderData") or {}
    page = (loader.get("video_(id)/page")
            or loader.get("note_(id)/page") or {})
    vir = page.get("videoInfoRes") or {}
    items = vir.get("item_list") or []
    if not items:
        # 服务端明确给出的失败原因（仅自己可见/审核中/地区限制…）原样透传
        fl = (vir.get("filter_list") or [{}])[0]
        reason = {
            "status_self_see": "该作品仅作者自己可见",
            "status_friend_see": "该作品仅好友可见",
            "status_under_review": "该作品正在审核中，暂不可下载",
            "status_deleted": "该作品已被删除",
        }.get(fl.get("filter_reason"), "")
        detail = fl.get("detail_msg") or fl.get("notice") or ""
        if reason or detail:
            raise DouyinError("：".join(x for x in (reason, detail) if x))
        raise DouyinError("分享页里没有找到视频条目（视频可能已删除或需要登录）")
    item = items[0]
    if item.get("images"):
        raise DouyinError("这是图集（图文）链接，暂只支持视频")

    video = item.get("video") or {}
    play_list = (video.get("play_addr") or {}).get("url_list") or []
    if not play_list:
        raise DouyinError("分享页里没有播放地址（视频可能已删除或仅限登录）")

    duration_ms = video.get("duration") or item.get("duration") or 0
    try:
        duration = int(duration_ms) / 1000.0
    except (TypeError, ValueError):
        duration = 0
    return {
        "title": item.get("desc") or "",
        "author": (item.get("author") or {}).get("nickname") or "",
        "duration": duration,
        "cover": ((video.get("cover") or {}).get("url_list") or [""])[0],
        "play_url": build_play_url(play_list[0]),
    }


def resolve(url: str) -> dict:
    """解析抖音链接，返回 {id, title, author, duration, cover, play_url}。

    支持 v.douyin.com 短链、www.douyin.com/video|note/{id}、
    www.iesdouyin.com/share/video|note/{id}。失败抛 DouyinError。
    """
    u = (url or "").strip()
    if not is_douyin(u):
        raise DouyinError("不是抖音链接")
    m = SHORT_RE.match(u)
    # group(0) 是不含中文的干净短链：口令粘贴无空格时尾部会带中文
    final = expand_short(m.group(0)) if m else u
    # 短链展开后的地址与原始地址（含 modal_id 等参数）都试一遍
    aweme_id = extract_aweme_id(final) or extract_aweme_id(u)
    if not aweme_id:
        raise DouyinError("无法从链接中识别视频 ID（直播/商品等链接不支持）")

    headers = {"User-Agent": MOBILE_UA}
    ttwid = _get_ttwid()
    if ttwid:
        headers["Cookie"] = f"ttwid={ttwid}"
    share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    try:
        with DIRECT_OPENER.open(
                urllib.request.Request(share_url, headers=headers),
                timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise DouyinError(f"分享页请求失败：{e}") from e
    info = parse_share_html(html)
    info["id"] = aweme_id
    if not info["title"]:
        info["title"] = f"抖音视频_{aweme_id}"
    return info
