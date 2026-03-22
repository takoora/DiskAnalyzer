from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget, QApplication


class LoadingOverlay(QWidget):
    """Semi-transparent overlay that shows a status message over a widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setVisible(False)
        self._text = "Loading..."

    def set_text(self, text):
        self._text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(30, 30, 30, 180))
        painter.setPen(QColor(200, 200, 200))
        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
        painter.end()

    def show_over(self, widget, text=None):
        """Position over the given widget and show."""
        if text:
            self._text = text
        self.setParent(widget)
        self.setGeometry(widget.rect())
        self.raise_()
        self.setVisible(True)
        QApplication.processEvents()

    def hide_overlay(self):
        self.setVisible(False)
