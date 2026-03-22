from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QTextDocument, QAbstractTextDocumentLayout
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from disk_analyzer.models.file_table_model import SEARCH_TERM_ROLE


class SearchHighlightDelegate(QStyledItemDelegate):
    """Delegate that highlights search term matches in yellow within text cells."""

    HIGHLIGHT_BG = "#c6a700"
    HIGHLIGHT_FG = "#000000"

    def paint(self, painter, option, index):
        search_term = index.data(SEARCH_TERM_ROLE)
        text = index.data(Qt.DisplayRole)

        if not search_term or not text or search_term not in text.lower():
            super().paint(painter, option, index)
            return

        # Draw selection background
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # Build HTML with highlighted matches
        html = self._highlight_html(text, search_term)

        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(html)
        doc.setTextWidth(option.rect.width() - 4)

        painter.translate(option.rect.x() + 2, option.rect.y())
        clip = QRect(0, 0, option.rect.width() - 4, option.rect.height())
        painter.setClipRect(clip)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        if option.state & QStyle.State_Selected:
            ctx.palette.setColor(ctx.palette.Text, option.palette.highlightedText().color())
        else:
            ctx.palette.setColor(ctx.palette.Text, QColor(220, 220, 220))

        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def _highlight_html(self, text, term):
        """Insert <span> highlight tags around all case-insensitive matches."""
        lower = text.lower()
        parts = []
        i = 0
        while i < len(text):
            pos = lower.find(term, i)
            if pos < 0:
                parts.append(self._escape(text[i:]))
                break
            parts.append(self._escape(text[i:pos]))
            match = text[pos:pos + len(term)]
            parts.append(
                f'<span style="background-color:{self.HIGHLIGHT_BG};'
                f'color:{self.HIGHLIGHT_FG};padding:1px 2px;">'
                f'{self._escape(match)}</span>'
            )
            i = pos + len(term)
        return "".join(parts)

    @staticmethod
    def _escape(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
