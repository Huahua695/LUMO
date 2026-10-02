"""网络环境：读 Windows 系统代理（yt-dlp 不会替你读注册表）+ 代理决策。

GUI 程序从快捷方式启动时进程环境里没有 HTTP_PROXY/HTTPS_PROXY，
yt-dlp 也不读 Windows 的 Internet Settings——所以「系统代理」必须自己读。
"""
import winreg


def system_proxy() -> str:
    """读 HKCU Internet Settings；未启用或读失败返回 ''。"""
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            if not winreg.QueryValueEx(k, "ProxyEnable")[0]:
                return ""
            s = str(winreg.QueryValueEx(k, "ProxyServer")[0])
    except OSError:
        return ""
    if not s:
        return ""
    if "=" in s:  # "http=127.0.0.1:7890;https=127.0.0.1:7890" 形式
        for part in s.split(";"):
            key, _, val = part.partition("=")
            if key.strip().lower() in ("https", "http") and val:
                s = val
                break
        else:
            return ""
    s = s.strip()
    return s if "://" in s else f"http://{s}"


def effective_proxy(mode: str, manual_url: str) -> str:
    """按设置得出实际代理地址：system=读系统、manual=手动、off=直连。"""
    if mode == "off":
        return ""
    if mode == "manual":
        return (manual_url or "").strip()
    return system_proxy()
