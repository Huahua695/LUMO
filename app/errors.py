"""把底层英文异常翻译成用户能看懂的中文。

约定：项目内部主动抛出的错误消息一律中文——friendly_error 检测到消息
里已含中文时原样透传；只有英文的底层异常才进入类型/关键词翻译表。
所有引擎的 except 分支和主入口异常钩子都应经过这里，保证用户永远
能看到中文报错；英文原文随堆栈写入日志（app/proc.py）。
"""
import errno as _errno
import urllib.error


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


# 常见英文关键词 → 中文（按序匹配，小写比较）
KEYWORD_MAP = [
    ("unsupported url", "不支持的网站链接"),
    ("is not a valid url", "不是有效的网址"),
    ("unable to download", "下载数据失败"),
    ("requested format is not available", "所选画质/格式不可用"),
    ("private video", "该视频为私密视频"),
    ("video unavailable", "该视频不可用或已删除"),
    ("this video is unavailable", "该视频不可用或已删除"),
    ("sign in", "该内容需要登录，暂不支持"),
    ("confirm you're not a bot", "触发了网站人机验证，请稍后重试"),
    ("http error 403", "服务器拒绝访问（403）"),
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


def friendly_error(e: BaseException, fallback: str = "操作失败") -> str:
    """把异常翻译成中文；项目内抛出的中文消息原样透传。"""
    if isinstance(e, KeyboardInterrupt):
        return "操作已取消"
    msg = str(e).strip()
    if msg and _has_cjk(msg):
        return msg

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
        reason = getattr(e, "reason", None)
        if isinstance(reason, BaseException):
            return f"无法连接：{friendly_error(reason, fallback)}"
        return f"无法连接：{reason or '请检查网络'}"
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
    if isinstance(e, (ValueError,)) and "json" in msg.lower():
        return "数据解析失败"

    low = (msg or "").lower()
    for kw, cn in KEYWORD_MAP:
        if kw in low:
            return cn

    # 兜底：不向用户暴露英文细节（原文在日志里）
    return f"{fallback}（{type(e).__name__}）" if msg else fallback
