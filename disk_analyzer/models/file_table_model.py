import heapq
import os
from datetime import datetime

from PySide6.QtCore import Qt, QAbstractTableModel, QThread, Signal
from PySide6.QtGui import QColor
from disk_analyzer.utils.formatting import format_size, format_percent, calc_percent
from disk_analyzer.utils.colors import color_for_extension
from disk_analyzer.views.color_delegate import COLOR_ROLE


class _FileListBuilder(QThread):
    """Build the sorted file list off the main thread."""
    done = Signal(list, int)  # (sorted_files, total_size)

    def __init__(self, root_node, max_files, parent=None):
        super().__init__(parent)
        self._root_node = root_node
        self._max_files = max_files

    def run(self):
        all_files = list(self._root_node.all_files())
        total_size = sum(f.own_size for f in all_files)
        if len(all_files) <= self._max_files:
            result = sorted(all_files, key=lambda f: f.own_size, reverse=True)
        else:
            result = heapq.nlargest(self._max_files, all_files, key=lambda f: f.own_size)
        self.done.emit(result, total_size)


COLUMNS = ["", "Size", "%", "Name", "Modified", "Path", "Extension"]


def _file_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _file_mtime_str(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


SEARCH_TERM_ROLE = Qt.UserRole + 200


class FileTableModel(QAbstractTableModel):
    loading_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_files = []  # full unfiltered list
        self._files = []      # currently displayed (filtered)
        self._total_size = 0
        self._highlighted_paths = set()
        self._search_term = ""
        self._filename_only = False
        self._builder = None

    MAX_FILES = 100_000

    def set_root(self, root_node):
        """Kick off background building of the file list."""
        # Clear current data immediately
        self.beginResetModel()
        self._all_files = []
        self._files = []
        self._total_size = 0
        self._search_term = ""
        self._highlighted_paths = set()
        self.endResetModel()

        # Build the sorted list in a background thread
        self._builder = _FileListBuilder(root_node, self.MAX_FILES, self)
        self._builder.done.connect(self._on_build_done)
        self._builder.start()

    def _on_build_done(self, files, total_size):
        self.beginResetModel()
        self._all_files = files
        self._files = files
        self._total_size = total_size
        self.endResetModel()
        self._builder = None
        self.loading_finished.emit()

    def clear(self):
        self.beginResetModel()
        self._all_files = []
        self._files = []
        self._total_size = 0
        self._highlighted_paths = set()
        self._search_term = ""
        self.endResetModel()

    def set_filter(self, search_term, filename_only=False):
        self.beginResetModel()
        self._search_term = search_term.lower()
        self._filename_only = filename_only
        if not self._search_term:
            self._files = self._all_files
        else:
            self._files = [
                f for f in self._all_files
                if self._search_term in (f.name.lower() if filename_only else f.path.lower())
            ]
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
                return _file_mtime_str(node.path)
            elif col == 5:
                return node.path
            elif col == 6:
                return node.extension or "(none)"
        elif role == Qt.UserRole:
            if col == 1:
                return node.own_size
            elif col == 2:
                return calc_percent(node.own_size, self._total_size)
            elif col == 4:
                return _file_mtime(node.path)
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
        elif role == SEARCH_TERM_ROLE:
            if self._search_term and col in (3, 5):  # Name, Path
                return self._search_term

        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = order == Qt.DescendingOrder
        if column == 1 or column == 2:
            self._files.sort(key=lambda f: f.own_size, reverse=reverse)
        elif column == 3:
            self._files.sort(key=lambda f: f.name.lower(), reverse=reverse)
        elif column == 4:
            self._files.sort(key=lambda f: _file_mtime(f.path), reverse=reverse)
        elif column == 5:
            self._files.sort(key=lambda f: f.path.lower(), reverse=reverse)
        elif column == 6:
            self._files.sort(key=lambda f: f.extension.lower(), reverse=reverse)
        self.endResetModel()
