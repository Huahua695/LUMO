"""所有下载/增强/剪切任务的线程基类：统一信号、取消机制、运行期防睡眠。"""
from PySide6.QtCore import QThread, Signal

from sleep_guard import acquire as _sleep_acquire, release as _sleep_release


class BaseTask(QThread):
    sig = Signal(object)  # 统一事件通道：{'id', 'event', ...}

    def __init__(self, task_id: int, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self._cancelled = False
        self._proc = None
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
        kw["id"] = self.task_id
        self.sig.emit(kw)

    def progress(self, pct=None, **kw):
        if pct is not None:
            kw["pct"] = max(0.0, min(100.0, float(pct)))
        self._emit(event="progress", **kw)

    def done(self, path="", **kw):
        self._emit(event="done", path=path, **kw)

    def error(self, msg="", cancelled=False, **kw):
        self._emit(event="error" if not cancelled else "cancelled",
                   error=msg, **kw)
