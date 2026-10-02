"""所有下载/增强/剪切任务的线程基类：统一信号、取消机制、运行期防睡眠。"""
import subprocess

from PySide6.QtCore import QThread, Signal

from .sleep_guard import acquire as _sleep_acquire, release as _sleep_release


class BaseTask(QThread):
    sig = Signal(object)  # 统一事件通道：{'id', 'event', ...}

    def __init__(self, task_id: int, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self._cancelled = False
        self._proc: subprocess.Popen | None = None
        self._terminal_emitted = False  # done/error/cancelled 只发一次
        # 线程结束时归还"阻止睡眠"名额
        self.finished.connect(self._release_sleep)

    def start(self, *args, **kw):
        _sleep_acquire()
        super().start(*args, **kw)

    def _release_sleep(self):
        _sleep_release()

    def cancel(self):
        self._cancelled = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    def _emit(self, **kw):
        if kw.get("event") in ("done", "error", "cancelled"):
            # 终态只发一次：防止看门狗超时与线程自身收尾事件双重上报
            if self._terminal_emitted:
                return
            self._terminal_emitted = True
        kw["id"] = self.task_id
        self.sig.emit(kw)

    def progress(self, pct=None, **kw):
        if pct is not None:
            kw["pct"] = max(0.0, min(100.0, float(pct)))
        self._emit(event="progress", **kw)

    def done(self, path="", **kw):
        self._emit(event="done", path=path, **kw)

    def error(self, msg="", cancelled=False, **kw):
        if not cancelled:
            # 失败落日志：报障不再依赖复现（英文原文/堆栈由调用方另行记录）
            try:
                from .proc import append_log
                append_log(f"[task:{type(self).__name__}] {msg}\n")
            except Exception:
                pass
        self._emit(event="error" if not cancelled else "cancelled", error=msg, **kw)
