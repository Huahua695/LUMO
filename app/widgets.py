"""跨页面共用的小组件：SectionCard / PathRow / EmptyState / TaskProgressRow。

颜色一律交给 QSS（objectName）或 theme 令牌，这里不写死；
图标随主题变色由 theme 的监听回调刷新（WeakMethod，控件销毁自动失效）。
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from . import icons, theme
from .theme import elide
from .utils import human_size, human_speed, open_in_explorer, reveal_in_explorer


def retire_thread(widget, th, timeout_ms: int = 2000) -> None:
    """任务线程收尾：wait 超时仍未退出的线程绝不能 deleteLater——
    Qt 6 会 qFatal「QThread: Destroyed while thread is still running」整个
    进程闪退。改为挂到 finished 信号延迟回收，并在 widget 上保留 Python
    引用，防止包装器先于 C++ 对象被回收。"""
    if th is None:
        return
    th.wait(timeout_ms)
    if th.isRunning():
        retired = getattr(widget, "_retired_threads", None)
        if retired is None:
            retired = widget._retired_threads = []
        retired.append(th)
        th.finished.connect(th.deleteLater)
    else:
        th.deleteLater()


class SectionCard(QFrame):
    """白底圆角卡片：标题 + 内容。四个页面的统一容器。"""

    def __init__(self, title: str = "", title_style: str = "h1",
                 spacing: int = 10, parent=None):
        super().__init__(objectName="card", parent=parent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 18, 24, 18)
        self.body.setSpacing(spacing)
        if title:
            t = QLabel(title)
            t.setObjectName(title_style)
            self.body.addWidget(t)

    def addLayout(self, lay) -> None:
        self.body.addLayout(lay)

    def addWidget(self, w, stretch: int = 0) -> None:
        self.body.addWidget(w, stretch)

    def addSpacing(self, n: int) -> None:
        self.body.addSpacing(n)


class PathRow(QHBoxLayout):
    """目录/文件选择行：标签 + 省略路径 + [folder] [arrow-out] 两个图标按钮。

    getter/setter 读写设置项；changed 在变化后回调（如刷新恢复横幅）。
    pick_file=True 时改为选择文件（如 cookies.txt），「打开」也变成定位文件。
    """

    def __init__(self, label_text: str, getter, setter, changed=None,
                 pick_file: bool = False, file_filter: str = "", parent=None):
        super().__init__()
        self._getter = getter
        self._setter = setter
        self._changed = changed
        self._pick_file = pick_file
        self._file_filter = file_filter or "所有文件 (*)"
        lbl = QLabel(label_text)
        self.val = QLabel(elide(getter(), 52))
        self.val.setObjectName("sub")
        self.val.setToolTip(getter())

        self.b_change = QPushButton()
        self.b_open = QPushButton()
        open_tip = "定位文件" if pick_file else "打开文件夹"
        for b, tip in ((self.b_change, "更改…"), (self.b_open, open_tip)):
            b.setObjectName("iconBtn")
            b.setFixedSize(QSize(30, 30))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
        self.b_change.clicked.connect(self._pick)
        self.b_open.clicked.connect(self._open)

        self.addWidget(lbl)
        self.addWidget(self.val, 1)
        self.addWidget(self.b_change)
        self.addWidget(self.b_open)
        self._refresh_icons()
        theme.on_theme_changed(self._refresh_icons)

    def _refresh_icons(self) -> None:
        t = theme.current()
        pm1 = icons.pixmap_for(None, "folder", t["sub"], 16)
        pm2 = icons.pixmap_for(None, "arrow-out", t["sub"], 16)
        if pm1 is not None:
            self.b_change.setIcon(QIcon(pm1))
        if pm2 is not None:
            self.b_open.setIcon(QIcon(pm2))

    def _pick(self) -> None:
        if self._pick_file:
            d, _ = QFileDialog.getOpenFileName(
                None, "选择文件", self._getter(), self._file_filter)
        else:
            d = QFileDialog.getExistingDirectory(None, "选择文件夹", self._getter())
        if d:
            self._apply(d)

    def _open(self) -> None:
        if self._pick_file:
            reveal_in_explorer(self._getter())
        else:
            open_in_explorer(self._getter())

    def _apply(self, d: str) -> None:
        self._setter(d)
        self.val.setText(elide(d, 52))
        self.val.setToolTip(d)
        if self._changed:
            self._changed()


class EmptyState(QWidget):
    """居中空状态：线性图标 + 一两句说明，可带一个 ghost 操作按钮。"""

    def __init__(self, icon_name: str, text: str, button_text: str = "",
                 on_click=None, icon_size: int = 44, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 12, 0, 12)
        v.setSpacing(10)
        v.addStretch(1)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.icon_label)
        self.text_label = QLabel(text)
        self.text_label.setObjectName("sub")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.text_label)
        self.btn = None
        if button_text:
            self.btn = QPushButton(button_text)
            self.btn.setProperty("ghost", True)
            if on_click is not None:
                self.btn.clicked.connect(on_click)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(self.btn)
            row.addStretch(1)
            v.addLayout(row)
        v.addStretch(1)
        self._refresh_icon()
        theme.on_theme_changed(self._refresh_icon)

    def _refresh_icon(self) -> None:
        pm = icons.pixmap_for(self, self._icon_name, theme.current()["sub"],
                              self._icon_size)
        if pm is not None:
            self.icon_label.setPixmap(pm)


class TaskProgressRow(QWidget):
    """任务列表的两行式行：
    标题 + 百分比 + 操作按钮 / 元信息 · 状态 / 行底通栏细进度条。
    完成后按钮变「打开」并真正定位结果文件。"""

    action_clicked = Signal(int)

    def __init__(self, task_id, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.folder = ""     # 保存目录（失败/取消时「打开」回退到这里）
        self.open_path = ""  # 完成后的结果文件
        self._done = False

        self.name_label = QLabel("准备中…")
        self.name_label.setStyleSheet(
            "font-weight:600; background:transparent; border:none;")
        self.name_label.setMinimumWidth(120)
        self.pct_label = QLabel("")
        self.pct_label.setObjectName("sub")
        self.pct_label.setMinimumWidth(40)
        self.pct_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                    | Qt.AlignmentFlag.AlignVCenter)
        theme.tabular(self.pct_label)

        self.btn = QPushButton("取消")
        self.btn.setProperty("danger", True)
        self.btn.setFixedWidth(64)
        self.btn.clicked.connect(self._on_btn)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.name_label, 1)
        top.addWidget(self.pct_label)
        top.addWidget(self.btn)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("sub")
        self.status_label = QLabel("排队中")
        self.status_label.setObjectName("sub")
        theme.tabular(self.status_label)
        mid = QHBoxLayout()
        mid.setSpacing(6)
        mid.addWidget(self.meta_label)
        mid.addWidget(self.status_label, 1)

        self.bar = QProgressBar(objectName="thinBar")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addLayout(mid)
        lay.addWidget(self.bar)

    def _on_btn(self) -> None:
        if self._done:
            reveal_in_explorer(self.open_path or self.folder)
        else:
            self.action_clicked.emit(self.task_id)

    def set_state(self, **kw) -> None:
        if kw.get("name"):
            self.name_label.setText(elide(kw["name"], 40))
            self.name_label.setToolTip(kw["name"])
        if "engine" in kw:
            self.meta_label.setText(kw["engine"])
        if "pct" in kw:
            pct = kw["pct"]
            if pct is None:
                self.bar.setRange(0, 0)
                self.pct_label.setText("")
            else:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(pct))
                self.pct_label.setText(f"{int(pct)}%")
        parts = []
        if kw.get("stage"):
            parts.append(kw["stage"])
        if kw.get("total"):
            parts.append(f"{human_size(kw.get('done'))} / {human_size(kw['total'])}")
        elif kw.get("done"):
            parts.append(human_size(kw["done"]))
        if kw.get("fps") is not None:
            parts.append(f"{kw['fps']:.1f} 帧/秒")
        if kw.get("speed"):
            parts.append(human_speed(kw["speed"]))
        if parts:
            self.status_label.setText("  ·  ".join(parts))
        if kw.get("text"):
            self.status_label.setText(kw["text"])

    def finish(self, ok: bool = True, text: str = None,
               open_path: str = None) -> None:
        """任务终态：状态标签换色，按钮改为「打开」并真正定位结果文件。"""
        self._done = True
        if open_path:
            self.open_path = open_path
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if ok else self.bar.value())
        self.pct_label.setText("100%" if ok else "")
        theme.retag(self.status_label, "ok" if ok else "err")
        self.status_label.setText(text or ("已完成 ✓" if ok else "失败"))
        self.btn.setText("打开")
        self.btn.setProperty("danger", False)
        self.btn.setProperty("ghost", True)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)
