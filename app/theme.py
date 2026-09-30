"""界面主题：配色 + 全局 QSS 样式表。"""

ACCENT = "#4f8cff"
ACCENT_DARK = "#3d7bf0"
BG = "#f4f6fb"
CARD = "#ffffff"
BORDER = "#e4e9f2"
TEXT = "#2b2f36"
SUB = "#8a93a3"
GREEN = "#2e9e5b"
RED = "#e5484d"

QSS = f"""
* {{
    font-family: 'Microsoft YaHei UI','Microsoft YaHei',sans-serif;
    outline: none;
}}
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-size: 14px; }}
QFrame#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QLabel#h1 {{ font-size: 21px; font-weight: 600; background: transparent; border: none; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; background: transparent; border: none; }}
QLabel#sub {{ color: {SUB}; font-size: 12px; background: transparent; border: none; }}
QLabel#ok {{ color: {GREEN}; font-weight: 600; background: transparent; border: none; }}
QLabel#err {{ color: {RED}; background: transparent; border: none; }}
QLabel#accent {{ color: {ACCENT}; background: transparent; border: none; }}

QLineEdit {{
    background: #fff; border: 1.5px solid {BORDER}; border-radius: 10px;
    padding: 9px 13px; font-size: 14px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QPushButton {{
    background: {ACCENT}; color: #fff; border: none; border-radius: 10px;
    padding: 9px 20px; font-size: 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ background: #c4d5f5; color: #fff; }}
QPushButton[ghost="true"] {{
    background: #fff; color: {TEXT}; border: 1.5px solid {BORDER};
    font-weight: 400; padding: 8px 16px;
}}
QPushButton[ghost="true"]:hover {{ border-color: {ACCENT}; color: {ACCENT}; background: #f5f9ff; }}
QPushButton[ghost="true"]:disabled {{ color: #b7bec9; border-color: #eef1f6; background: #fafbfd; }}
QPushButton[danger="true"] {{
    background: #fff; color: {RED}; border: 1.5px solid #f2c1c3; font-weight: 400; padding: 8px 16px;
}}
QPushButton[danger="true"]:hover {{ background: #fdeef0; }}
QPushButton#big {{ font-size: 15px; padding: 12px 20px; }}

QProgressBar {{
    background: #edf1f8; border: none; border-radius: 6px; height: 12px;
    text-align: center; color: transparent; font-size: 9px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6aa6ff, stop:1 {ACCENT});
    border-radius: 6px;
}}

QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border: none; }}

QComboBox {{
    background: #fff; border: 1.5px solid {BORDER}; border-radius: 10px;
    padding: 8px 12px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #fff; border: 1px solid {BORDER};
    selection-background-color: #eaf2ff; selection-color: {TEXT};
}}

QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px;
}}
QScrollBar::handle:vertical {{ background: #d3dbe8; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #b9c4d6; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QToolTip {{
    background: #fff; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px 8px; border-radius: 6px; font-size: 12px;
}}
"""


def elide(s: str, n: int = 46) -> str:
    if len(s) <= n:
        return s
    return s[: n // 2 - 2] + "…" + s[-(n // 2 - 1):]
