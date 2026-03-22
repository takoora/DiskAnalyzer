from PySide6.QtCore import Qt, QAbstractTableModel, Signal
from PySide6.QtWidgets import QTableView, QHeaderView, QAbstractItemView, QMenu
from PySide6.QtGui import QColor

from disk_analyzer.utils.formatting import format_size, format_count, format_percent, calc_percent
from disk_analyzer.utils.colors import color_for_extension
from disk_analyzer.views.progress_delegate import PercentBarDelegate
from disk_analyzer.views.color_delegate import ColorLabelDelegate, COLOR_ROLE


COLUMNS = ["Extension", "Total Size", "Files", "%"]


class FileTypeModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._total_size = 0
        self._highlighted_ext = None

    def set_root(self, root_node):
        self.beginResetModel()
        ext_map = {}
        for f in root_node.all_files():
            ext = f.extension or "(no extension)"
            if ext not in ext_map:
                ext_map[ext] = [0, 0]
            ext_map[ext][0] += f.own_size
            ext_map[ext][1] += 1
        self._data = sorted(ext_map.items(), key=lambda x: x[1][0], reverse=True)
        self._total_size = sum(v[0] for _, v in self._data)
        self._highlighted_ext = None
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self._total_size = 0
        self._highlighted_ext = None
        self.endResetModel()

    def set_highlighted_ext(self, ext):
        self._highlighted_ext = ext
        self.layoutChanged.emit()

    def ext_at(self, row):
        if 0 <= row < len(self._data):
            return self._data[row][0]
        return None

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        ext, (total_size, count) = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return ext
            elif col == 1:
                return format_size(total_size)
            elif col == 2:
                return format_count(count)
            elif col == 3:
                return format_percent(total_size, self._total_size)
        elif role == Qt.UserRole:
            if col == 1:
                return total_size
            elif col == 2:
                return count
            elif col == 3:
                return calc_percent(total_size, self._total_size)
        elif role == COLOR_ROLE:
            if col == 0:
                return color_for_extension(ext if ext != "(no extension)" else "")
        elif role == Qt.BackgroundRole:
            if self._highlighted_ext and ext == self._highlighted_ext:
                return QColor(25, 118, 210, 60)
        elif role == Qt.TextAlignmentRole:
            if col in (1, 2):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = order == Qt.DescendingOrder
        if column == 0:
            self._data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        elif column == 1:
            self._data.sort(key=lambda x: x[1][0], reverse=reverse)
        elif column == 2:
            self._data.sort(key=lambda x: x[1][1], reverse=reverse)
        elif column == 3:
            self._data.sort(key=lambda x: x[1][0], reverse=reverse)
        self.endResetModel()


class FileTypeView(QTableView):
    extension_selected = Signal(str)
    highlight_in_chart = Signal(str)  # extension to highlight in treemap
    reset_chart_highlight = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = FileTypeModel()
        self.setModel(self._model)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Colored label delegate for Extension column
        self._color_label_delegate = ColorLabelDelegate(self)
        self.setItemDelegateForColumn(0, self._color_label_delegate)

        # Progress bar delegate for % column
        self._pct_delegate = PercentBarDelegate(self)
        self.setItemDelegateForColumn(3, self._pct_delegate)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.resizeSection(0, 100)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        self.sortByColumn(1, Qt.DescendingOrder)
        self.clicked.connect(self._on_clicked)

    def set_root(self, root_node):
        self._model.set_root(root_node)

    def clear(self):
        self._model.clear()

    def highlight_ext(self, ext):
        self._model.set_highlighted_ext(ext)

    def _on_clicked(self, index):
        if not index.isValid():
            return
        ext = self._model.ext_at(index.row())
        if ext:
            self.extension_selected.emit(ext)

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        ext = self._model.ext_at(index.row())
        if not ext:
            return
        menu = QMenu(self)
        highlight_action = menu.addAction("Highlight in Chart")
        highlight_action.triggered.connect(lambda: self.highlight_in_chart.emit(ext))
        reset_action = menu.addAction("Reset Highlight")
        reset_action.triggered.connect(lambda: self.reset_chart_highlight.emit())
        menu.exec(self.viewport().mapToGlobal(pos))
