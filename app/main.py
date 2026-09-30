"""拾光工具箱 入口。"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox


def _excepthook(t, v, tb):
    try:
        QMessageBox.critical(None, "哎呀，出了点问题",
                             f"{t.__name__}: {v}\n\n{traceback.format_exc(limit=4)}")
    except Exception:
        pass
    sys.__stderr__ and sys.__stderr__.write(traceback.format_exc())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("拾光工具箱")
    app.setOrganizationName("ShiGuang")
    from paths import asset_path
    icon = asset_path("icon.ico")
    if os.path.exists(icon):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon))
    sys.excepthook = _excepthook
    from main_window import MainWindow
    if "--selftest" in sys.argv:
        w = MainWindow()
        import yt_dlp
        from paths import tools_ready
        missing = tools_ready()
        ok = w.stack.count() == 4 and not missing
        sys.exit(0 if ok else 1)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
