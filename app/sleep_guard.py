"""任务运行期间阻止系统进入睡眠（屏幕仍可正常关闭）。

原理：调用 Windows SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)，
引用计数归零后恢复默认。所有后台任务（下载/增强/剪切）通过 BaseTask 自动接入。
"""
import ctypes
import threading

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

_lock = threading.Lock()
_count = 0


def _apply():
    # 返回值非 0 表示成功；失败（如非 Windows）静默忽略
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def acquire():
    global _count
    with _lock:
        _count += 1
        if _count == 1:
            try:
                _apply()
            except AttributeError:
                pass


def release():
    global _count
    with _lock:
        if _count <= 0:
            return
        _count -= 1
        if _count == 0:
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except AttributeError:
                pass


def active() -> bool:
    return _count > 0
