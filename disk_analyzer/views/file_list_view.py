from PySide6.QtWidgets import QTableView, QHeaderView, QAbstractItemView, QMenu
from PySide6.QtCore import Qt, Signal

from disk_analyzer.models.file_table_model import FileTableModel
from disk_analyzer.utils.finder import show_in_finder
from disk_analyzer.views.color_delegate import ColorSwatchDelegate
from disk_analyzer.views.progress_delegate import PercentBarDelegate


class FileListView(QTableView):
    file_selected = Signal(object)  # FileNode

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = FileTableModel()
        self.setModel(self._model)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Color swatch delegate for column 0
        self._color_delegate = ColorSwatchDelegate(self)
        self.setItemDelegateForColumn(0, self._color_delegate)

        # Progress bar delegate for % column (2)
        self._pct_delegate = PercentBarDelegate(self)
        self.setItemDelegateForColumn(2, self._pct_delegate)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 22)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Size
        header.setSectionResizeMode(2, QHeaderView.Interactive)       # %
        header.resizeSection(2, 120)
        header.setSectionResizeMode(3, QHeaderView.Interactive)       # Name
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # Path
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Extension

        self.sortByColumn(1, Qt.DescendingOrder)
        self.clicked.connect(self._on_clicked)

    def set_root(self, root_node):
        self._model.set_root(root_node)
        self.resizeColumnToContents(1)

    def clear(self):
        self._model.clear()

    def highlight_paths(self, paths):
        self._model.set_highlighted_paths(paths)

    def _on_clicked(self, index):
        if not index.isValid():
            return
        node = self._model.node_at(index.row())
        if node:
            self.file_selected.emit(node)

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        node = self._model.node_at(index.row())
        if not node:
            return
        menu = QMenu(self)
        action = menu.addAction("Show in Finder")
        action.triggered.connect(lambda: show_in_finder(node.path))
        menu.exec(self.viewport().mapToGlobal(pos))
