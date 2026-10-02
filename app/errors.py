"""把底层英文异常翻译成用户能看懂的中文。

约定：项目内部主动抛出的错误消息一律中文——friendly_error 检测到消息
里已含中文时原样透传；只有英文的底层异常才进入类型/关键词翻译表。
所有引擎的 except 分支和主入口异常钩子都应经过这里，保证用户永远
能看到中文报错；英文原文随堆栈写入日志（app/proc.py）。
"""
import errno as _errno
import re
import urllib.error


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


# yt-dlp 报错末尾常带 issue 链接，对普通用户是噪音
_ISSUE_URL_RE = re.compile(
    r"\s*\(?see https://github\.com/yt-dlp/yt-dlp/issues/\d+\)?\s*")

# 常见英文关键词 → 中文（按序匹配，越具体的放越前面）
KEYWORD_MAP = [
    # Cookie 相关（最高频失败，放最前）
    ("fresh cookies", "该网站需要登录 Cookie，请在「设置 → Cookie」导入 cookies.txt"),
    ("cookies (not necessarily logged in) are needed",
     "该网站需要登录 Cookie，请在「设置 → Cookie」导入 cookies.txt"),
    ("could not copy chrome cookie database",
     "读取浏览器 Cookie 失败：请先完全退出该浏览器再试"),
    ("failed to decrypt with dpapi",
     "Chrome 127+ 已禁止自动读取 Cookie，请用浏览器扩展导出 cookies.txt"
     "（见「设置 → Cookie」）"),
    ("no video formats found", "未能取到该网站的视频流（可能需要 Cookie，或站点已改版）"),
    ("unable to download api page", "无法访问该网站接口（可能需要代理，见「设置 → 网络」）"),
    ("transporterror", "网络连接失败（可能需要代理，见「设置 → 网络」）"),
    ("unsupported url", "该网站暂不支持（下载器未收录该站点，非本软件问题）"),
    ("is not a valid url", "不是有效的网址"),
    ("unable to download", "下载数据失败"),
    ("requested format is not available", "所选画质/格式不可用"),
    ("private video", "该视频为私密视频"),
    ("video unavailable", "该视频不可用或已删除"),
    ("sign in", "该内容需要登录，可在「设置 → Cookie」导入 cookies.txt 后重试"),
    ("confirm you're not a bot", "触发了网站人机验证，请稍后重试"),
    ("http error 403", "服务器拒绝访问（403），链接可能已过期或需要登录"),
    ("http error 404", "内容不存在（404）"),
    ("http error 429", "请求过于频繁（429），请稍后重试"),
    ("http error 5", "服务器故障（5xx），请稍后重试"),
    ("timed out", "网络连接超时，请检查网络后重试"),
    ("timeout", "网络连接超时，请检查网络后重试"),
    ("connection refused", "连接被拒绝"),
    ("connection reset", "连接被重置"),
    ("name or service not known", "域名解析失败，请检查网络"),
    ("temporary failure in name resolution", "域名解析失败，请检查网络"),
    ("no route to host", "无法连接到服务器，请检查网络"),
    ("getaddrinfo failed", "域名解析失败，请检查网络"),
    ("disk full", "磁盘空间不足"),
    ("no space left", "磁盘空间不足"),
    ("denied", "没有权限"),
]

_HTTP_CODE_MAP = {
    401: "需要登录（401）",
    403: "服务器拒绝访问（403）",
    404: "内容不存在（404）",
    416: "请求范围无效（416）",
    429: "请求过于频繁（429），请稍后重试",
}


def _cookie_file_invalid(msg: str) -> bool:
    low = msg.lower()
    return "cookie" in low and ("not valid" in low or "format" in low
                                or "can't parse" in low)


def friendly_error(e: BaseException, fallback: str = "操作失败") -> str:
    """把异常翻译成中文；项目内抛出的中文消息原样透传。"""
    if isinstance(e, KeyboardInterrupt):
        return "操作已取消"
    msg = str(e).strip()
    msg = _ISSUE_URL_RE.sub("", msg).strip()
    if msg and _has_cjk(msg):
        return msg

    # Cookie 文件本身坏了（yt-dlp: Cookie file ... is not valid）
    if msg and _cookie_file_invalid(msg):
        return "Cookie 文件格式不正确（需 Netscape 格式的 cookies.txt），" \
               "请重新导出（见「设置 → Cookie」）"

    if isinstance(e, FileNotFoundError):
        name = getattr(e, "filename", None)
        return f"找不到文件：{name}" if name else "找不到文件"
    if isinstance(e, IsADirectoryError):
        return "目标是一个文件夹，不是文件"
    if isinstance(e, PermissionError):
        return "没有权限（文件可能被占用或只读），请关闭相关程序后重试"
    if isinstance(e, urllib.error.HTTPError):
        reason = _HTTP_CODE_MAP.get(e.code, f"服务器返回错误 {e.code}")
        return f"{reason}，请稍后重试"
    if isinstance(e, urllib.error.URLError):
        inner_reason = getattr(e, "reason", None)
        if isinstance(inner_reason, BaseException):
            return f"无法连接：{friendly_error(inner_reason, fallback)}"
        return f"无法连接：{inner_reason or '请检查网络'}"
    if isinstance(e, ConnectionError):
        return "网络连接失败，请检查网络后重试"
    if isinstance(e, TimeoutError):
        return "网络连接超时，请检查网络后重试"
    if isinstance(e, OSError):
        if e.errno == _errno.ENOSPC:
            return "磁盘空间不足，请清理后重试"
        if e.errno == _errno.EACCES:
            return "没有权限（文件可能被占用或只读），请关闭相关程序后重试"
        strerror = getattr(e, "strerror", None) or ""
        if strerror:
            # 中文版 Windows 的 strerror 本身是中文；英文系统回退到类型名
            return (strerror if _has_cjk(strerror)
                    else f"{fallback}：{type(e).__name__}")
    # yt-dlp extractor 内部崩溃（如微博的 TypeError）——上游问题，别让用户以为本地坏了
    if isinstance(e, (TypeError, AttributeError, KeyError, IndexError)):
        return "该网站解析出错（上游兼容问题），可尝试更新软件或更换链接"
    if isinstance(e, ValueError) and "json" in msg.lower():
        return "数据解析失败"

    low = (msg or "").lower()
    for kw, cn in KEYWORD_MAP:
        if kw in low:
            return cn

    # 兜底：不向用户暴露英文细节（原文在日志里）
    return f"{fallback}（{type(e).__name__}）" if msg else fallback
