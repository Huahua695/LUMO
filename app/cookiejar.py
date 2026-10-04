"""cookies.txt（Netscape 格式）→ HTTP Cookie 头。

设置页存的是 yt-dlp 直接可吃的 Netscape cookies.txt；N_m3u8DL-CLI 与
urllib 需要的是 `Cookie: k=v; k2=v2` 请求头，这里做转换。

隐私硬要求：**A 站的 Cookie 绝不能出现在 B 站的请求头里**——按下载
URL 的域名做后缀匹配过滤，任何解析失败一律返回 ''，绝不能让本来能
匿名下载的链接因为 Cookie 文件损坏而失败。
"""
from urllib.parse import urlparse

# 行首前缀为 #HttpOnly_ 的不是注释，是有效条目（其余 # 开头才是注释）
_HTTSONLY_PREFIX = "#HttpOnly_"


def _is_true(v: str) -> bool:
    return (v or "").strip().lower() in ("true", "1")


def _domain_matches(host: str, cookie_domain: str) -> bool:
    """.example.com 匹配 example.com 与全部子域；无前导点的域按精确匹配
    （带点才放宽），杜绝后缀误配（如域为 com 的条目匹配一切）。"""
    host = (host or "").lower().strip(".")
    cd = (cookie_domain or "").lower().strip(".")
    if not host or not cd:
        return False
    if host == cd:
        return True
    if "." not in cd:
        return False
    return host.endswith("." + cd)


def parse_cookies(cookie_file: str):
    """解析 Netscape cookies.txt，返回 [(domain, name, value, secure), ...]。
    逐行容错：坏行跳过，不抛异常。"""
    import time
    with open(cookie_file, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    if text.startswith("\ufeff"):
        text = text[1:]
    now = int(time.time())
    out = []
    for line in text.splitlines():
        line = line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith(_HTTSONLY_PREFIX):
            line = line[len(_HTTSONLY_PREFIX):]
        elif line.startswith("#"):
            continue
        parts = line.split("\t", 6)
        if len(parts) < 7:
            continue
        domain, _flag, _path, secure, expiry, name, value = parts
        name = name.strip()
        if not name:
            continue
        try:
            exp = int(expiry)
        except ValueError:
            continue
        # exp=0 是会话 Cookie（导出后仍然有效），保留；过期条目跳过
        if exp and exp < now:
            continue
        out.append((domain.strip(), name, value, _is_true(secure)))
    return out


def cookie_header(cookie_file: str, url: str) -> str:
    """从 Netscape cookies.txt 中挑出适用于 url 的条目，拼成 Cookie 头值。
    文件不存在/格式错/无匹配条目时返回 ''（绝不因此让下载失败）。"""
    if not cookie_file:
        return ""
    try:
        cookies = parse_cookies(cookie_file)
    except OSError:
        return ""
    if not cookies:
        return ""
    try:
        u = urlparse(url or "")
        host, scheme = (u.hostname or "").lower(), (u.scheme or "").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    pairs, seen = [], set()
    for domain, name, value, secure in cookies:
        if name in seen:
            continue
        if not _domain_matches(host, domain):
            continue
        if secure and scheme != "https":
            continue  # Secure Cookie 不发给 http
        seen.add(name)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def build_headers(cookie_file: str, url: str, referer: str) -> str:
    """拼 N_m3u8DL-CLI 的 --headers 值：`key:value`，多个用 `|` 分隔。
    Cookie 只取与下载 URL 同域的条目——CLI 会把这组头发给清单与全部分片
    （可能在其它 CDN 域上），跨域 Cookie 不带是隐私要求。

    T2 实测（本地 HTTP 服务打印 CLI 实际请求头，2026-10-04）：
    - 值含 `;`、空格、`:` 均逐字到达（key 按第一个冒号切分）；
    - `|` 是硬分隔符且无法转义：值含 `|` 会被截断，剩余部分还会被
      当作新的头注入。因此值含 `|` 的条目一律丢弃。
    无任何头时返回 ''（调用方不加 --headers 参数）。
    """
    referer = (referer or "").strip()
    cookie = cookie_header(cookie_file, url)
    if cookie:
        # 丢掉值含 | 的条目：CLI 无法表达，且会截断/注入（T2 实测）
        cookie = "; ".join(p for p in cookie.split("; ") if "|" not in p)
    parts = []
    if referer and "|" not in referer:
        parts.append(f"Referer:{referer}")
    if cookie:
        parts.append(f"Cookie:{cookie}")
    return "|".join(parts)
