import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from disk_analyzer.utils.logging_config import setup_logging, get_logger
from disk_analyzer.views.main_window import MainWindow

_RES_DIR = os.path.join(os.path.dirname(__file__), "resources", "icons")
# When bundled by PyInstaller, resources are in sys._MEIPASS
if hasattr(sys, "_MEIPASS"):
    _RES_DIR = os.path.join(sys._MEIPASS, "resources", "icons")

if sys.platform == "win32":
    ICON_PATH = os.path.join(_RES_DIR, "app_icon.ico")
else:
    ICON_PATH = os.path.join(_RES_DIR, "app_icon.svg")


def main():
    setup_logging()
    log = get_logger("main")
    log.info("DiskAnalyzer starting")

    app = QApplication(sys.argv)
    app.setApplicationName("DiskAnalyzer")
    app.setWindowIcon(QIcon(ICON_PATH))
    app.setStyle("Fusion")

    # Dark theme
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(42, 42, 42))
    palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(55, 55, 55))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Link, QColor(66, 133, 244))
    palette.setColor(QPalette.Highlight, QColor(66, 133, 244))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    log.info("Main window shown")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
