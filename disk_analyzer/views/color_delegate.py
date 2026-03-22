from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from disk_analyzer.utils.colors import text_color_for_bg


COLOR_ROLE = Qt.UserRole + 100
COLOR_LABEL_ROLE = Qt.UserRole + 101


class ColorSwatchDelegate(QStyledItemDelegate):
    """Draws a small colored square indicator."""

    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        color = index.data(COLOR_ROLE)
        if not isinstance(color, QColor):
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        h = min(option.rect.height() - 8, 10)
        w = option.rect.width() - 10  # leave gap on right for folder icon
        x = option.rect.x() + 3
        y = option.rect.y() + (option.rect.height() - h) // 2
        rect = QRect(x, y, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 2, 2)
        painter.restore()


class ColorLabelDelegate(QStyledItemDelegate):
    """Draws extension text with a colored background pill. Used in File Types."""

    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        color = index.data(COLOR_ROLE)
        label = index.data(Qt.DisplayRole) or ""
        if not isinstance(color, QColor):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(4, 3, -4, -3)

        # Colored pill background
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 4, 4)

        # Accessible text color based on background luminance
        painter.setPen(text_color_for_bg(color))
        painter.drawText(rect, Qt.AlignCenter, label)

        painter.restore()
