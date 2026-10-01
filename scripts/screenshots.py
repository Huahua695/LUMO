"""生成浅色/暗色各 4 页截图到 docs/screenshots/（界面改版验收用）。

用法：venv/Scripts/python.exe scripts/screenshots.py
说明：offscreen 平台加载不到系统字体（中文会变豆腐块），默认走真实 windows
平台 + WA_DontShowOnScreen（不弹窗）来渲染；可用 QT_QPA_PLATFORM 覆盖。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import theme  # noqa: E402
from app.app_settings import AppSettings  # noqa: E402
from app.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("拾光工具箱")
    w = MainWindow(AppSettings())
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.resize(1080, 840)
    w.show()
    out_dir = os.path.join(ROOT, "docs", "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    pages = [("download", 0), ("enhance", 1), ("cut", 2), ("settings", 3)]
    for mode in ("light", "dark"):
        theme.set_theme(mode)
        for _ in range(30):
            QCoreApplication.processEvents()
        for name, idx in pages:
            w.nav.setCurrentRow(idx)
            for _ in range(30):
                QCoreApplication.processEvents()
            path = os.path.join(out_dir, f"{mode}-{name}.png")
            if not w.grab().save(path):
                raise SystemExit(f"截图保存失败: {path}")
            print("saved", path)


if __name__ == "__main__":
    main()
