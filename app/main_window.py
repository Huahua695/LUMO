"""主窗口：左侧导航 + 三个页面。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget,
)

import theme
from app_settings import AppSettings


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("拾光工具箱")
        self.resize(1040, 720)
        self.setMinimumSize(940, 640)

        self.settings = AppSettings()

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- 侧边栏 ----
        side = QFrame()
        side.setFixedWidth(196)
        side.setStyleSheet("background:#ffffff; border-right:1px solid %s;" % theme.BORDER)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 22, 14, 18)
        sv.setSpacing(8)
        logo = QLabel("拾光工具箱")
        logo.setStyleSheet("font-size:19px; font-weight:700; background:transparent;"
                           "color:%s; border:none;" % theme.ACCENT)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver = QLabel("无损下载 · AI 高清")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setObjectName("sub")
        sv.addWidget(logo)
        sv.addWidget(ver)
        sv.addSpacing(14)

        self.nav = QListWidget()
        self.nav.addItem("⬇️  下载")
        self.nav.addItem("✨  画质增强")
        self.nav.addItem("✂️  视频剪切")
        self.nav.addItem("⚙️  设置")
        self.nav.setCurrentRow(0)
        self.nav.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{
                color: {theme.TEXT}; padding: 12px 14px; margin: 3px 0;
                border-radius: 10px; font-size: 15px;
            }}
            QListWidget::item:selected {{ background: {theme.ACCENT}; color: #fff; }}
            QListWidget::item:hover:!selected {{ background: #f0f4fb; }}
        """)
        self.nav.setFixedHeight(230)
        sv.addWidget(self.nav)
        sv.addStretch(1)
        foot = QLabel("本机处理 · 不上传数据")
        foot.setObjectName("sub")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv.addWidget(foot)
        lay.addWidget(side)

        # ---- 页面 ----
        self.stack = QStackedWidget()
        from download_tab import DownloadTab
        from enhance_tab import EnhanceTab
        from cut_tab import CutTab
        from settings_tab import SettingsTab
        self.page_dl = DownloadTab(self.settings)
        self.page_enh = EnhanceTab(self.settings)
        self.page_cut = CutTab(self.settings)
        self.page_set = SettingsTab(self.settings)
        self.stack.addWidget(self.page_dl)
        self.stack.addWidget(self.page_enh)
        self.stack.addWidget(self.page_cut)
        self.stack.addWidget(self.page_set)
        lay.addWidget(self.stack, 1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.setCentralWidget(central)
        self.setStyleSheet(theme.QSS)
