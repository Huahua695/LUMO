"""主窗口：左侧导航 + 四个页面。"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import icons
from . import theme
from .app_settings import AppSettings
from .version import APP_VERSION

NAV_ITEMS = [
    ("下载", "download"),
    ("画质增强", "wand"),
    ("视频剪切", "scissors"),
    ("设置", "settings"),
]
NAV_ITEM_H = 40


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings = None):
        super().__init__()
        self.settings = settings or AppSettings()
        self.setWindowTitle(f"拾光工具箱 v{APP_VERSION}")
        self.resize(1080, 840)
        self.setMinimumSize(1000, 760)

        # 全局主题：主入口只创建窗口，这里确保 QSS/调色板已应用
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None and not app.styleSheet():
            theme.set_theme(self.settings.theme)
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- 侧边栏 ----
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(196)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 22, 14, 18)
        sv.setSpacing(6)
        # logo：图标 + 名称一行
        lrow = QHBoxLayout()
        lrow.setSpacing(7)
        logo_icon = QLabel()
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from PySide6.QtGui import QPixmap
        from .paths import asset_path
        icon_file = asset_path("icon.png")
        import os
        if os.path.isfile(icon_file):
            pm = QPixmap(icon_file)
            if not pm.isNull():
                logo_icon.setPixmap(pm.scaled(
                    20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        logo = QLabel("拾光工具箱")
        logo.setObjectName("logo")
        lrow.addStretch(1)
        lrow.addWidget(logo_icon)
        lrow.addWidget(logo)
        lrow.addStretch(1)
        ver = QLabel("无损下载 · AI 高清")
        ver.setObjectName("sub")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv.addLayout(lrow)
        sv.addWidget(ver)
        sv.addSpacing(14)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(18, 18))
        for label, _icon_name in NAV_ITEMS:
            self.nav.addItem(QListWidgetItem(label))
        self.nav.setCurrentRow(0)
        # 每项固定高度，导航总高随条目数自适应（不再写死总高度）
        for i in range(self.nav.count()):
            self.nav.item(i).setSizeHint(QSize(0, NAV_ITEM_H))
        self.nav.setFixedHeight(NAV_ITEM_H * self.nav.count() + 6)
        sv.addWidget(self.nav)
        sv.addStretch(1)
        foot = QLabel("本机处理 · 不上传数据")
        foot.setObjectName("sub")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv.addWidget(foot)
        lay.addWidget(side)
        self._refresh_nav_icons()
        theme.on_theme_changed(self._refresh_nav_icons)

        # ---- 页面 ----
        self.stack = QStackedWidget()
        from .download_tab import DownloadTab
        from .enhance_tab import EnhanceTab
        from .cut_tab import CutTab
        from .settings_tab import SettingsTab
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

    def _refresh_nav_icons(self):
        t = theme.current()
        for i, (_label, icon_name) in enumerate(NAV_ITEMS):
            it = self.nav.item(i)
            if it is not None:
                it.setIcon(icons.icon_for(self, icon_name, t["sub"], t["accent"]))

    def _on_scheme_changed(self, _scheme):
        # 跟随系统模式下，系统深浅切换时重新应用主题
        if theme.mode() == "system":
            theme.set_theme("system")
