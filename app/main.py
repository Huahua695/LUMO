"""拾光工具箱 入口。

开发运行：项目根目录 `python run.py`（或 `python -m app.main`）；
PyInstaller 打包入口为根目录 run.py。
"""
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


def _excepthook(t, v, tb):
    try:
        QMessageBox.critical(None, "哎呀，出了点问题",
                             f"{t.__name__}: {v}\n\n{traceback.format_exc(limit=4)}")
    except Exception:
        pass
    sys.__stderr__ and sys.__stderr__.write(traceback.format_exc())
    from .proc import append_log
    append_log(traceback.format_exc())


def main():
    # 125%/150% 系统缩放下按实际比例渲染，避免界面发虚
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("拾光工具箱")
    app.setOrganizationName("ShiGuang")
    from .paths import asset_path
    icon = asset_path("icon.ico")
    import os
    if os.path.exists(icon):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon))
    sys.excepthook = _excepthook
    from .app_settings import AppSettings
    settings = AppSettings()
    from .main_window import MainWindow
    if "--selftest" in sys.argv:
        w = MainWindow(settings)
        from .paths import tools_ready
        missing = tools_ready()
        ok = w.stack.count() == 4 and not missing
        # 打包环境下 SVG 图标渲染链路（qsvg 插件）必须可用
        if ok:
            from . import icons
            pm = icons.pixmap("download", "#666666", 24, 1.0)
            ok = pm is not None and not pm.isNull()
        sys.exit(0 if ok else 1)
    w = MainWindow(settings)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
