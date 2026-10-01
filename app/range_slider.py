"""双柄区间滑条：视频剪切页的选区条（low / high 两个可拖拽手柄）。

配色取自 QPalette（Highlight / Button / Mid），主题切换自动跟随；
low 手柄用 set_low()/low()，high 手柄用 set_high()/high()。
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QSlider

HANDLE_R = 7
GROOVE_H = 4


class RangeSlider(QSlider):
    low_changed = Signal(int)
    high_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 1000)
        self._low = 0
        self._high = 1000
        self._grab = 0  # -1 拖 low，1 拖 high，0 无
        self.setFixedHeight(HANDLE_R * 2 + 8)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ---- 取值 ----
    def low(self) -> int:
        return self._low

    def high(self) -> int:
        return self._high

    def set_low(self, v: int, emit: bool = True) -> None:
        v = max(self.minimum(), min(self._high, int(v)))
        if v != self._low:
            self._low = v
            self.update()
            if emit:
                self.low_changed.emit(v)

    def set_high(self, v: int, emit: bool = True) -> None:
        v = max(self._low, min(self.maximum(), int(v)))
        if v != self._high:
            self._high = v
            self.update()
            if emit:
                self.high_changed.emit(v)

    # ---- 坐标换算 ----
    def _groove_rect(self) -> QRectF:
        h = self.height()
        return QRectF(HANDLE_R + 1, h / 2 - GROOVE_H / 2,
                      self.width() - 2 * (HANDLE_R + 1), GROOVE_H)

    def _val_to_x(self, v: int) -> float:
        g = self._groove_rect()
        span = max(1, self.maximum() - self.minimum())
        return g.left() + (v - self.minimum()) * g.width() / span

    def _x_to_val(self, x: float) -> int:
        g = self._groove_rect()
        span = max(1, self.maximum() - self.minimum())
        ratio = (x - g.left()) / max(1.0, g.width())
        return self.minimum() + round(ratio * span)

    # ---- 绘制 ----
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        p.setPen(Qt.PenStyle.NoPen)
        g = self._groove_rect()
        # 底槽
        p.setBrush(QColor(pal.color(QPalette.ColorRole.Mid)))
        p.drawRoundedRect(g, GROOVE_H / 2, GROOVE_H / 2)
        # 选区
        sel_left = self._val_to_x(self._low)
        sel_w = max(6.0, self._val_to_x(self._high) - sel_left)
        p.setBrush(QColor(pal.color(QPalette.ColorRole.Highlight)))
        p.drawRoundedRect(QRectF(sel_left, g.top(), sel_w, GROOVE_H),
                          GROOVE_H / 2, GROOVE_H / 2)
        # 手柄：白底圆点 + 主题色描边
        p.setBrush(QColor(pal.color(QPalette.ColorRole.HighlightedText)))
        p.setPen(QColor(pal.color(QPalette.ColorRole.Highlight)))
        for v in (self._low, self._high):
            p.drawEllipse(QPointF(self._val_to_x(v), self.height() / 2),
                          HANDLE_R, HANDLE_R)
        p.end()

    # ---- 交互 ----
    def _nearest_handle(self, x: float) -> int:
        xl, xh = self._val_to_x(self._low), self._val_to_x(self._high)
        if abs(x - xl) <= abs(x - xh):
            if abs(x - xl) <= HANDLE_R + 6 or x < (xl + xh) / 2:
                return -1
        return 1

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            x = ev.position().x()
            self._grab = self._nearest_handle(x)
            v = self._x_to_val(x)
            if self._grab == -1:
                self.set_low(v)
            else:
                self.set_high(v)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._grab:
            v = self._x_to_val(ev.position().x())
            if self._grab == -1:
                self.set_low(v)
            else:
                self.set_high(v)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        self._grab = 0
        super().mouseReleaseEvent(ev)
