"""子进程公共设施：CREATE_NO_WINDOW 常量 + 子进程 stderr 滚动日志。

所有外部工具（ffmpeg / N_m3u8DL-CLI / realesrgan）的 stderr 统一追加到
%LOCALAPPDATA%/ShiGuang/logs/app.log（超过 1MB 滚动，保留 3 份历史），
界面保持无感；用户报障时无需复现，直接看日志。注意：日志文件不是管道，
不存在「写满管道卡死子进程」的问题，但 stdout 仍不要挂不读取的 PIPE。
"""
import os
import subprocess
import threading

CREATE_NO_WINDOW = 0x08000000

MAX_LOG_BYTES = 1 << 20  # 1 MB
BACKUPS = 3

_lock = threading.Lock()
_fh = None


def logs_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ShiGuang", "logs")


def log_path() -> str:
    return os.path.join(logs_dir(), "app.log")


def _rotate() -> None:
    p = log_path()
    try:
        if os.path.exists(p) and os.path.getsize(p) > MAX_LOG_BYTES:
            for i in range(BACKUPS - 1, 0, -1):
                if os.path.exists(f"{p}.{i}"):
                    os.replace(f"{p}.{i}", f"{p}.{i + 1}")
            os.replace(p, p + ".1")
    except OSError:
        pass


def stderr_target():
    """返回可交给 subprocess stderr= 的追加写文件对象；打不开时退回 DEVNULL。"""
    global _fh
    with _lock:
        if _fh is None:
            try:
                os.makedirs(logs_dir(), exist_ok=True)
                _rotate()
                _fh = open(log_path(), "ab")
            except OSError:
                return subprocess.DEVNULL
        return _fh


def append_log(text: str) -> None:
    """追加一段文本（如未捕获异常堆栈）到日志文件。"""
    try:
        os.makedirs(logs_dir(), exist_ok=True)
        _rotate()
        with open(log_path(), "ab") as f:
            f.write(text.encode("utf-8", errors="replace"))
    except OSError:
        pass
