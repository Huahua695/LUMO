"""设置页：默认目录汇总 + 外观主题 + 关于信息（含第三方组件许可）。"""
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .version import APP_VERSION
from .widgets import PathRow, SectionCard


class SettingsTab(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        # ---- 默认目录（汇总入口；下载/增强页内保留上下文相关入口） ----
        dirs_card = SectionCard("默认目录", title_style="h2")
        dirs_card.addLayout(PathRow("下载保存到", lambda: settings.save_dir,
                                    lambda d: setattr(settings, "save_dir", d)))
        dirs_card.addLayout(PathRow("增强输出到", lambda: settings.enhance_dir,
                                    lambda d: setattr(settings, "enhance_dir", d)))
        root.addWidget(dirs_card)

        # ---- 外观 ----
        appearance = SectionCard("外观", title_style="h2")
        trow = QHBoxLayout()
        tlbl = QLabel("主题")
        tlbl.setFixedWidth(110)
        self.theme_combo = QComboBox()
        for data, text in (("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")):
            self.theme_combo.addItem(text, data)
        cur = settings.theme
        idx = self.theme_combo.findData(cur)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme_combo.blockSignals(False)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        trow.addWidget(tlbl)
        trow.addWidget(self.theme_combo)
        trow.addStretch(1)
        appearance.addLayout(trow)
        root.addWidget(appearance)

        # ---- 关于 ----
        about = SectionCard("关于", title_style="h2")
        about.body.setSpacing(6)
        lines = [
            (f"拾光工具箱 v{APP_VERSION} — 资源无损下载 + AI 画质增强，"
             "全部在本机完成，不上传任何数据。", "h2"),
            ("内置组件：N_m3u8DL-CLI（m3u8/HLS 下载）· yt-dlp（网站视频）· "
             "Real-ESRGAN ncnn Vulkan（AI 超分）· FFmpeg（合成与转封装）。", "sub"),
            ("开源许可：yt-dlp（Unlicense）· N_m3u8DL-CLI / Real-ESRGAN / ncnn（MIT）· "
             "FFmpeg（GPLv3+ 构建，完整分发包需遵守 GPL 义务）· PySide6（LGPLv3）——"
             "完整声明见 THIRD-PARTY-NOTICES.md。", "sub"),
            ("小提示：视频超分是逐帧运算，1 分钟视频通常需要几分钟，请耐心等待进度条。", "sub"),
        ]
        for text, style in lines:
            lbl = QLabel(text)
            lbl.setObjectName(style)
            lbl.setWordWrap(True)
            about.addWidget(lbl)
        root.addWidget(about)
        root.addStretch(1)

    def _on_theme_changed(self):
        v = self.theme_combo.currentData() or "system"
        self.settings.theme = v
        theme.set_theme(v)
