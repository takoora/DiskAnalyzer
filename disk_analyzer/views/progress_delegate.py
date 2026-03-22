from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


class PercentBarDelegate(QStyledItemDelegate):
    """Draws a progress bar + percentage text for columns that provide
    a float percentage (0-100) via Qt.UserRole."""

    BAR_COLOR = QColor(25, 118, 210)     # Material Blue 700
    BAR_BG = QColor(50, 50, 50)
    TEXT_COLOR = QColor(220, 220, 220)

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        # Get percentage from UserRole
        pct = index.data(Qt.UserRole)
        display = index.data(Qt.DisplayRole)
        if pct is None or not isinstance(pct, (int, float)):
            super().paint(painter, option, index)
            return

        painter.save()

        # Selection highlight
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        rect = option.rect.adjusted(4, 3, -4, -3)

        # Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.BAR_BG)
        painter.drawRoundedRect(rect, 3, 3)

        # Fill
        if pct > 0:
            fill_width = int(rect.width() * min(pct, 100.0) / 100.0)
            fill_rect = QRect(rect.x(), rect.y(), fill_width, rect.height())
            painter.setBrush(self.BAR_COLOR)
            painter.drawRoundedRect(fill_rect, 3, 3)

        # Text
        painter.setPen(self.TEXT_COLOR)
        if display:
            painter.drawText(rect, Qt.AlignCenter, str(display))

        painter.restore()
