"""单色线性图标：加载 assets/icons/*.svg，按主题色渲染为 QIcon / QPixmap。

SVG 文件里用 stroke="currentColor" 占位，渲染前替换成实际颜色；
渲染结果按 (名称, 颜色, 尺寸, 缩放) 缓存，主题切换时由 theme 的监听回调重新取。
"""
import os

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from .paths import asset_path

_cache = {}


def pixmap(name: str, color: str, size: int = 24, dpr: float = 1.0):
    """渲染单个图标；SVG 缺失或渲染失败返回 None（调用方需兜底）。"""
    key = (name, color, size, round(dpr, 2))
    if key in _cache:
        return _cache[key]
    pm = None
    try:
        from PySide6.QtSvg import QSvgRenderer
        p = asset_path(os.path.join("icons", f"{name}.svg"))
        with open(p, encoding="utf-8") as f:
            svg = f.read().replace("currentColor", color)
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if r.isValid():
            pm = QPixmap(max(1, int(size * dpr)), max(1, int(size * dpr)))
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            r.render(painter)
            painter.end()
            pm.setDevicePixelRatio(dpr)
    except Exception:
        pm = None
    _cache[key] = pm
    return pm


def _screen_dpr() -> float:
    """窗口未显示时取主屏缩放，保证 125%/150% 下图标一次渲染到位。"""
    from PySide6.QtGui import QGuiApplication
    scr = QGuiApplication.primaryScreen()
    return (scr.devicePixelRatio() if scr is not None else 0.0) or 1.0


def pixmap_for(widget, name: str, color: str, size: int = 24):
    """按所在窗口（未显示时按主屏）缩放渲染，避免高分屏发虚。"""
    dpr = 0.0
    if widget is not None:
        win = widget.window()
        wh = win.windowHandle() if win is not None else None
        if wh is not None:
            dpr = wh.devicePixelRatio()
    return pixmap(name, color, size, dpr or _screen_dpr())


def icon(name: str, normal_color: str, active_color: str = "", dpr: float = 1.0) -> QIcon:
    """双态图标：普通态用 normal_color，选中态用 active_color（QIcon On 态）。"""
    ic = QIcon()
    for state, color in ((QIcon.State.Off, normal_color),
                         (QIcon.State.On, active_color or normal_color)):
        pm = pixmap(name, color, 24, dpr)
        if pm is not None:
            ic.addPixmap(pm, QIcon.Mode.Normal, state)
    return ic


def icon_for(widget, name: str, normal_color: str, active_color: str = "") -> QIcon:
    dpr = 0.0
    if widget is not None:
        win = widget.window()
        wh = win.windowHandle() if win is not None else None
        if wh is not None:
            dpr = wh.devicePixelRatio()
    return icon(name, normal_color, active_color, dpr or _screen_dpr())
