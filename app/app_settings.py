"""应用设置：持久化保存位置等偏好。"""
import os

from PySide6.QtCore import QSettings


def _default_save_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(desktop, "拾光下载")


def _default_enhance_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(desktop, "拾光高清")


class AppSettings:
    def __init__(self):
        self.q = QSettings("ShiGuang", "ShiGuangToolbox")

    @property
    def save_dir(self) -> str:
        d = self.q.value("download/save_dir", _default_save_dir())
        return d or _default_save_dir()

    @save_dir.setter
    def save_dir(self, v: str):
        self.q.setValue("download/save_dir", v)

    @property
    def enhance_dir(self) -> str:
        d = self.q.value("enhance/out_dir", _default_enhance_dir())
        return d or _default_enhance_dir()

    @enhance_dir.setter
    def enhance_dir(self, v: str):
        self.q.setValue("enhance/out_dir", v)

    @property
    def dl_quality(self) -> str:
        return self.q.value("download/quality", "best") or "best"

    @dl_quality.setter
    def dl_quality(self, v: str):
        self.q.setValue("download/quality", v)

    @property
    def dl_format(self) -> str:
        return self.q.value("download/format", "auto") or "auto"

    @dl_format.setter
    def dl_format(self, v: str):
        self.q.setValue("download/format", v)
