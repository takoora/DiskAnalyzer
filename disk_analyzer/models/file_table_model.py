from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtGui import QColor
from disk_analyzer.utils.formatting import format_size, format_percent, calc_percent
from disk_analyzer.utils.colors import color_for_extension
from disk_analyzer.views.color_delegate import COLOR_ROLE


COLUMNS = ["", "Size", "%", "Name", "Path", "Extension"]


class FileTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files = []
        self._total_size = 0
        self._highlighted_paths = set()

    def set_root(self, root_node):
        self.beginResetModel()
        self._files = sorted(root_node.all_files(), key=lambda f: f.own_size, reverse=True)
        self._total_size = sum(f.own_size for f in self._files)
        self._highlighted_paths = set()
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._files = []
        self._total_size = 0
        self._highlighted_paths = set()
        self.endResetModel()

    def set_highlighted_paths(self, paths):
        self._highlighted_paths = paths
        self.layoutChanged.emit()

    def node_at(self, row):
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def rowCount(self, parent=None):
        return len(self._files)

    def columnCount(self, parent=None):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._files):
            return None

        node = self._files[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 1:
                return format_size(node.own_size)
            elif col == 2:
                return format_percent(node.own_size, self._total_size)
            elif col == 3:
                return node.name
            elif col == 4:
                return node.path
            elif col == 5:
                return node.extension or "(none)"
        elif role == Qt.UserRole:
            if col == 1:
                return node.own_size
            elif col == 2:
                return calc_percent(node.own_size, self._total_size)
            return self.data(index, Qt.DisplayRole)
        elif role == COLOR_ROLE:
            if col == 0:
                return color_for_extension(node.extension)
        elif role == Qt.BackgroundRole:
            if self._highlighted_paths and node.path in self._highlighted_paths:
                return QColor(25, 118, 210, 60)
        elif role == Qt.TextAlignmentRole:
            if col == 1:
                return int(Qt.AlignRight | Qt.AlignVCenter)

        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = order == Qt.DescendingOrder
        if column == 1 or column == 2:
            self._files.sort(key=lambda f: f.own_size, reverse=reverse)
        elif column == 3:
            self._files.sort(key=lambda f: f.name.lower(), reverse=reverse)
        elif column == 4:
            self._files.sort(key=lambda f: f.path.lower(), reverse=reverse)
        elif column == 5:
            self._files.sort(key=lambda f: f.extension.lower(), reverse=reverse)
        self.endResetModel()
