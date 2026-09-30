"""设置页：默认目录 + 关于信息。"""
import os

from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from theme import elide
from utils import open_in_explorer


def _card(title, rows):
    c = QFrame(objectName="card")
    v = QVBoxLayout(c)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(10)
    t = QLabel(title)
    t.setObjectName("h2")
    v.addWidget(t)
    for row in rows:
        v.addLayout(row)
    return c


def _path_row(label_text, getter, setter, refresh):
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(110)
    val = QLabel(elide(getter(), 52))
    val.setObjectName("sub")
    val.setToolTip(getter())

    def pick():
        d = QFileDialog.getExistingDirectory(None, "选择文件夹", getter())
        if d:
            setter(d)
            val.setText(elide(d, 52))
            val.setToolTip(d)
            refresh()

    b = QPushButton("更改…")
    b.setProperty("ghost", True)
    b.clicked.connect(pick)
    o = QPushButton("打开")
    o.setProperty("ghost", True)
    o.clicked.connect(lambda: open_in_explorer(getter()))
    row.addWidget(lbl)
    row.addWidget(val, 1)
    row.addWidget(b)
    row.addWidget(o)
    return row, val


class SettingsTab(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        row1, self.v1 = _path_row("下载默认保存到", lambda: settings.save_dir,
                                  lambda d: setattr(settings, "save_dir", d),
                                  self._refresh)
        root.addWidget(_card("下载", [row1]))

        row2, self.v2 = _path_row("增强结果输出到", lambda: settings.enhance_dir,
                                  lambda d: setattr(settings, "enhance_dir", d),
                                  self._refresh)
        root.addWidget(_card("画质增强", [row2]))

        about = QFrame(objectName="card")
        v = QVBoxLayout(about)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(6)
        t = QLabel("关于")
        t.setObjectName("h2")
        lines = [
            "拾光工具箱 v1.0 — 资源无损下载 + AI 画质增强，全部在本机完成，不上传任何数据。",
            "内置组件：N_m3u8DL-CLI（m3u8/HLS 下载）· yt-dlp（网站视频）· "
            "Real-ESRGAN ncnn Vulkan（AI 超分）· FFmpeg（合成与转封装）。",
            "小提示：视频超分是逐帧运算，1 分钟视频通常需要几分钟，请耐心等待进度条。",
        ]
        for i, s in enumerate(lines):
            lbl = QLabel(s)
            lbl.setObjectName("sub" if i else "h2")
            lbl.setWordWrap(True)
            v.addWidget(lbl)
        root.addWidget(about)
        root.addStretch(1)

    def _refresh(self):
        pass
