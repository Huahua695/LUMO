"""界面主题：设计令牌（浅色 / 暗色）→ 生成全局 QSS 与调色板。

颜色 / 圆角 / 字号一律出自令牌表，改一处全局生效；不要在页面代码里写死颜色——
需要主题色的地方用 current() 取值或交给 QSS 的 objectName 规则。
set_theme() 负责应用并通知界面刷新自绘元素（图标、标题栏等）。
"""
import sys
import weakref

from PySide6.QtGui import QColor, QFont, QPalette

# ---------------- 令牌 ----------------

# 圆角：控件 8 / 卡片 12 / 浮层 12
RADIUS_CONTROL = 8
RADIUS_CARD = 12
RADIUS_OVERLAY = 12

# 字号四级：12 / 13 / 15 / 20
FS_SUB = 12
FS_BODY = 13
FS_H2 = 15
FS_H1 = 20

LIGHT = {
    "accent": "#3478F6",
    "accent_hover": "#2B69DF",
    "accent_soft": "rgba(52,120,246,0.12)",      # 选中态底色
    "accent_soft2": "rgba(52,120,246,0.06)",     # hover / 弱底色
    "accent_disabled_bg": "rgba(52,120,246,0.14)",
    "accent_disabled_text": "rgba(52,120,246,0.55)",
    "on_accent": "#FFFFFF",
    "bg": "#F5F6F8",
    "card": "#FFFFFF",
    "input": "#FFFFFF",
    "border": "rgba(0,0,0,0.08)",
    "border_strong": "rgba(0,0,0,0.16)",
    "hover_overlay": "rgba(0,0,0,0.045)",
    "text": "#1D1D1F",
    "sub": "#6E6E73",
    "ok": "#2E9E5B",
    "err": "#E5484D",
    "err_soft": "rgba(229,72,77,0.10)",
    "err_border": "rgba(229,72,77,0.35)",
    "warn_bg": "rgba(255,196,0,0.16)",
    "warn_border": "rgba(202,138,4,0.45)",
    "warn_icon": "#B45309",
    "track": "rgba(0,0,0,0.06)",
    "chunk_from": "#6AA6FF",
    "scroll": "rgba(0,0,0,0.18)",
    "scroll_hover": "rgba(0,0,0,0.30)",
    "tooltip_bg": "#FFFFFF",
    "caption": "#F5F6F8",
}

DARK = {
    "accent": "#0A84FF",
    "accent_hover": "#3396FF",
    "accent_soft": "rgba(10,132,255,0.22)",
    "accent_soft2": "rgba(10,132,255,0.10)",
    "accent_disabled_bg": "rgba(10,132,255,0.18)",
    "accent_disabled_text": "rgba(130,185,255,0.60)",
    "on_accent": "#FFFFFF",
    "bg": "#1C1C1E",
    "card": "#2C2C2E",
    "input": "#1C1C1E",
    "border": "rgba(255,255,255,0.09)",
    "border_strong": "rgba(255,255,255,0.18)",
    "hover_overlay": "rgba(255,255,255,0.06)",
    "text": "#F5F5F7",
    "sub": "#98989D",
    "ok": "#30D158",
    "err": "#FF5C5C",
    "err_soft": "rgba(255,92,92,0.16)",
    "err_border": "rgba(255,92,92,0.40)",
    "warn_bg": "rgba(255,214,10,0.12)",
    "warn_border": "rgba(255,214,10,0.35)",
    "warn_icon": "#FFD60A",
    "track": "rgba(255,255,255,0.10)",
    "chunk_from": "#409CFF",
    "scroll": "rgba(255,255,255,0.22)",
    "scroll_hover": "rgba(255,255,255,0.36)",
    "tooltip_bg": "#3A3A3C",
    "caption": "#1C1C1E",
}

# 当前生效的令牌 / 模式（set_theme 维护）
_tokens = dict(LIGHT)
_is_dark = False
_mode = "system"

# 主题切换监听（弱引用，界面元素自绘部分在此刷新）
_listeners = []


def current() -> dict:
    return _tokens


def is_dark() -> bool:
    return _is_dark


def mode() -> str:
    return _mode


def on_theme_changed(callback):
    """注册主题切换回调（绑定的控件销毁后自动失效）。"""
    _listeners.append(weakref.WeakMethod(callback))


def _notify_listeners():
    alive = []
    for ref in _listeners:
        cb = ref()
        if cb is None:
            continue
        alive.append(ref)
        try:
            cb()
        except Exception:
            pass
    _listeners[:] = alive


# ---------------- QSS 生成 ----------------

def build_qss(t: dict) -> str:
    return f"""
* {{ font-family: 'Microsoft YaHei UI','Microsoft YaHei',sans-serif; outline: none; }}
QMainWindow {{ background: {t['bg']}; }}
QWidget {{ color: {t['text']}; font-size: {FS_BODY}px; }}
QLabel {{ background: transparent; border: none; }}

QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: {RADIUS_CARD}px; }}
QFrame#sidebar {{ background: {t['card']}; border-right: 1px solid {t['border']}; }}
QFrame#hr {{ background: {t['border']}; border: none; max-height: 1px; }}
QFrame#probeCard {{ background: {t['accent_soft2']}; border: 1px solid {t['border']};
    border-radius: {RADIUS_CONTROL}px; }}
QFrame#warnBanner {{ background: {t['warn_bg']}; border: 1px solid {t['warn_border']};
    border-radius: {RADIUS_CONTROL}px; }}

QLabel#h1 {{ font-size: {FS_H1}px; font-weight: 600; background: transparent; border: none; }}
QLabel#h2 {{ font-size: {FS_H2}px; font-weight: 600; background: transparent; border: none; }}
QLabel#sub {{ color: {t['sub']}; font-size: {FS_SUB}px; background: transparent; border: none; }}
QLabel#ok {{ color: {t['ok']}; font-weight: 600; background: transparent; border: none; }}
QLabel#err {{ color: {t['err']}; background: transparent; border: none; }}
QLabel#accent {{ color: {t['accent']}; background: transparent; border: none; }}
QLabel#logo {{ color: {t['accent']}; font-size: 19px; font-weight: 700;
    background: transparent; border: none; }}
QLabel#thumb {{ background: {t['track']}; border: none; border-radius: 6px; }}

QLineEdit, QPlainTextEdit {{
    background: {t['input']}; border: 1px solid {t['border_strong']};
    border-radius: {RADIUS_CONTROL}px; padding: 8px 12px; font-size: {FS_BODY}px;
    selection-background-color: {t['accent']}; selection-color: {t['on_accent']};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {t['accent']}; }}

QPushButton {{
    background: {t['accent']}; color: {t['on_accent']}; border: none;
    border-radius: {RADIUS_CONTROL}px; padding: 8px 18px;
    font-size: {FS_BODY}px; font-weight: 600;
}}
QPushButton:hover {{ background: {t['accent_hover']}; }}
QPushButton:disabled {{ background: {t['accent_disabled_bg']}; color: {t['accent_disabled_text']}; }}
QPushButton[ghost="true"] {{
    background: {t['card']}; color: {t['text']}; border: 1px solid {t['border_strong']};
    font-weight: 400; padding: 7px 14px;
}}
QPushButton[ghost="true"]:hover {{ border-color: {t['accent']}; color: {t['accent']};
    background: {t['accent_soft2']}; }}
QPushButton[ghost="true"]:disabled {{ color: {t['sub']}; border-color: {t['border']};
    background: transparent; }}
QPushButton[danger="true"] {{
    background: {t['card']}; color: {t['err']}; border: 1px solid {t['err_border']};
    font-weight: 400; padding: 7px 14px;
}}
QPushButton[danger="true"]:hover {{ background: {t['err_soft']}; }}
QPushButton#big {{ font-size: {FS_H2}px; padding: 11px 20px; }}
QPushButton#iconBtn {{ background: transparent; border: none; border-radius: 6px; padding: 3px; }}
QPushButton#iconBtn:hover {{ background: {t['hover_overlay']}; }}

QProgressBar {{
    background: {t['track']}; border: none; border-radius: 6px; height: 12px;
    text-align: center; color: transparent; font-size: 9px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {t['chunk_from']}, stop:1 {t['accent']});
    border-radius: 6px;
}}
QProgressBar#thinBar {{ background: {t['track']}; border: none; border-radius: 2px; height: 4px; }}
QProgressBar#thinBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {t['chunk_from']}, stop:1 {t['accent']});
    border-radius: 2px;
}}

QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border: none; }}
QListWidget#dropList {{
    background: {t['input']}; border: 1.5px dashed {t['border_strong']};
    border-radius: {RADIUS_CONTROL}px; padding: 6px;
}}
QListWidget#dropList:hover {{ border-color: {t['accent']}; }}

QListWidget#nav {{ background: transparent; border: none; font-size: {FS_BODY}px; }}
QListWidget#nav::item {{
    color: {t['text']}; padding: 9px 12px; margin: 2px 6px;
    border-radius: {RADIUS_CONTROL}px; border-left: 3px solid transparent;
}}
QListWidget#nav::item:selected {{
    background: {t['accent_soft']}; color: {t['accent']};
    border-left: 3px solid {t['accent']}; font-weight: 600;
}}
QListWidget#nav::item:hover:!selected {{ background: {t['hover_overlay']}; }}

QComboBox {{
    background: {t['input']}; border: 1px solid {t['border_strong']};
    border-radius: {RADIUS_CONTROL}px; padding: 7px 12px; font-size: {FS_BODY}px;
}}
QComboBox:hover {{ border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t['card']}; border: 1px solid {t['border_strong']};
    border-radius: {RADIUS_OVERLAY}px; outline: none;
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']};
}}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['scroll']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['scroll']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {t['scroll_hover']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QToolTip {{
    background: {t['tooltip_bg']}; color: {t['text']}; border: 1px solid {t['border_strong']};
    padding: 6px 8px; border-radius: 8px; font-size: {FS_SUB}px;
}}
"""


def _palette(t: dict) -> QPalette:
    pal = QPalette()

    def c(key):
        return QColor(t[key])

    pal.setColor(QPalette.ColorRole.Window, c("bg"))
    pal.setColor(QPalette.ColorRole.WindowText, c("text"))
    pal.setColor(QPalette.ColorRole.Base, c("input"))
    pal.setColor(QPalette.ColorRole.AlternateBase, c("bg"))
    pal.setColor(QPalette.ColorRole.Text, c("text"))
    pal.setColor(QPalette.ColorRole.Button, c("card"))
    pal.setColor(QPalette.ColorRole.ButtonText, c("text"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["sub"]))
    pal.setColor(QPalette.ColorRole.Highlight, c("accent"))
    pal.setColor(QPalette.ColorRole.HighlightedText, c("on_accent"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, c("tooltip_bg"))
    pal.setColor(QPalette.ColorRole.ToolTipText, c("text"))
    pal.setColor(QPalette.ColorRole.Link, c("accent"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["sub"]))
    return pal


def _tune_titlebars(dark: bool, caption_hex: str):
    """Windows 11：暗色标题栏 + 标题栏颜色融入窗口背景。失败静默（旧系统/离屏）。"""
    if sys.platform != "win32":
        return
    try:
        from PySide6.QtWidgets import QApplication
        import ctypes
        for w in QApplication.topLevelWidgets():
            if not w.isWindow():
                continue
            hwnd = int(w.winId())
            value = ctypes.c_int(1 if dark else 0)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE（旧版本为 19）
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(hwnd), attr,
                        ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            r, g, b = (int(caption_hex[i:i + 2], 16) for i in (1, 3, 5))
            cap = ctypes.c_int((b << 16) | (g << 8) | r)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 35,  # DWMWA_CAPTION_COLOR
                ctypes.byref(cap), ctypes.sizeof(cap))
    except Exception:
        pass


def set_theme(mode_name: str):
    """应用主题：'system'（跟随系统）/ 'light' / 'dark'。"""
    global _mode, _is_dark, _tokens
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    _mode = mode_name if mode_name in ("system", "light", "dark") else "system"
    hints = app.styleHints()
    if _mode == "dark":
        hints.setColorScheme(Qt.ColorScheme.Dark)
    elif _mode == "light":
        hints.setColorScheme(Qt.ColorScheme.Light)
    else:
        hints.setColorScheme(Qt.ColorScheme.Unknown)
    _is_dark = (_mode == "dark") or (
        _mode == "system" and hints.colorScheme() == Qt.ColorScheme.Dark)
    _tokens = dict(DARK if _is_dark else LIGHT)
    app.setStyleSheet(build_qss(_tokens))
    app.setPalette(_palette(_tokens))
    _tune_titlebars(_is_dark, _tokens["caption"])
    _notify_listeners()


# ---------------- 小工具 ----------------

def retag(widget, object_name: str):
    """改 objectName 并让 QSS 重新生效（用于运行时切换状态色，如 ok/err）。"""
    widget.setObjectName(object_name)
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)


def tabular(widget):
    """给显示数字的控件开等宽数字特性，避免下载时文字左右抖动。"""
    f = widget.font()
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except Exception:
        pass
    widget.setFont(f)


def elide(s: str, n: int = 46) -> str:
    if len(s) <= n:
        return s
    return s[: n // 2 - 2] + "…" + s[-(n // 2 - 1):]


# 兼容旧引用：全局 QSS 由 set_theme 应用到 QApplication，不要再 setStyleSheet(theme.QSS)
QSS = ""
