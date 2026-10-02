"""设置页：默认目录汇总 + Cookie + 网络代理 + 外观主题 + 关于信息。"""
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from . import theme
from .version import APP_VERSION
from .widgets import PathRow, SectionCard


_COOKIE_HELP = (
    "怎么导出 Cookie？\n\n"
    "1. 用浏览器扩展（如 Get cookies.txt LOCALLY）在已登录目标网站的"
    "标签页里导出，格式选 Netscape；\n"
    "2. 导出后建议关闭对应标签页（减少 Cookie 失效）；\n"
    "3. Cookie 有效期通常几天到几周，失效后重新导出即可；\n\n"
    "Cookie 只保存在本机、只用于下载，不会上传。")


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

        # ---- Cookie（站点登录态：解锁需登录的站点与高清画质） ----
        cookie_card = SectionCard("Cookie", title_style="h2")
        cookie_card.addLayout(PathRow(
            "cookies.txt", lambda: settings.cookie_file,
            lambda v: setattr(settings, "cookie_file", v),
            pick_file=True,
            file_filter="Cookies 文件 (cookies.txt *.txt);;所有文件 (*)"))
        crow = QHBoxLayout()
        chelp = QPushButton("怎么导出？")
        chelp.setProperty("ghost", True)
        chelp.clicked.connect(
            lambda: QMessageBox.information(self, "导出 Cookie", _COOKIE_HELP))
        cnote = QLabel("需要登录的站点（西瓜 / 小红书 / B站高清等）在此导入；"
                       "只读本地文件，不上传")
        cnote.setObjectName("sub")
        crow.addWidget(chelp)
        crow.addWidget(cnote, 1)
        cookie_card.addLayout(crow)
        root.addWidget(cookie_card)

        # ---- 网络代理（境外站点需要；跟随系统 = 读 Windows 代理设置） ----
        net_card = SectionCard("网络", title_style="h2")
        nrow = QHBoxLayout()
        nlbl = QLabel("代理")
        nlbl.setFixedWidth(110)
        self.proxy_mode = QComboBox()
        for data, text in (("system", "跟随系统"), ("manual", "手动"),
                           ("off", "关闭（直连）")):
            self.proxy_mode.addItem(text, data)
        idx = self.proxy_mode.findData(settings.proxy_mode)
        self.proxy_mode.blockSignals(True)
        self.proxy_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.proxy_mode.blockSignals(False)
        self.proxy_mode.currentIndexChanged.connect(self._on_proxy_mode)
        self.proxy_edit = QLineEdit(settings.proxy_url)
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:7890 或 socks5://…")
        self.proxy_edit.textChanged.connect(self._on_proxy_url)
        nrow.addWidget(nlbl)
        nrow.addWidget(self.proxy_mode)
        nrow.addSpacing(6)
        nrow.addWidget(self.proxy_edit, 1)
        net_card.addLayout(nrow)
        nnote = QLabel("YouTube / X 等境外站点需要代理；「跟随系统」自动读取 "
                       "Windows 代理设置。抖音 / B 站始终直连，不受影响。")
        nnote.setObjectName("sub")
        nnote.setWordWrap(True)
        net_card.addWidget(nnote)
        root.addWidget(net_card)
        self._sync_proxy_edit()

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

    def _on_proxy_mode(self):
        self.settings.proxy_mode = self.proxy_mode.currentData() or "system"
        self._sync_proxy_edit()

    def _on_proxy_url(self, text: str):
        self.settings.proxy_url = (text or "").strip()

    def _sync_proxy_edit(self):
        # 「手动」模式才需要填地址
        self.proxy_edit.setEnabled(self.settings.proxy_mode == "manual")
