from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QAbstractItemView, QMenu, QLineEdit, QCheckBox, QLabel,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer

from disk_analyzer.models.file_table_model import FileTableModel
from disk_analyzer.utils.finder import show_in_finder, google_search, FILE_MANAGER_LABEL
from disk_analyzer.utils.delete_helper import confirm_and_delete
from disk_analyzer.utils.formatting import format_count
from disk_analyzer.views.color_delegate import ColorSwatchDelegate
from disk_analyzer.views.progress_delegate import PercentBarDelegate
from disk_analyzer.views.search_highlight_delegate import SearchHighlightDelegate


class FileListView(QWidget):
    file_selected = Signal(object)  # FileNode
    file_deleted = Signal(object)  # FileNode

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Search bar ---
        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)
        search_bar.setContentsMargins(4, 4, 4, 0)

        search_bar.addWidget(QLabel("Search:"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Type to filter files...")
        self._search_input.setClearButtonEnabled(True)
        search_bar.addWidget(self._search_input, 1)

        self._filename_only_cb = QCheckBox("Filename only")
        self._filename_only_cb.setChecked(False)
        search_bar.addWidget(self._filename_only_cb)

        self._result_count = QLabel("")
        self._result_count.setStyleSheet("color: #888; font-size: 11px; padding-right: 4px;")
        search_bar.addWidget(self._result_count)

        layout.addLayout(search_bar)

        # --- Table ---
        self._table = QTableView()
        self._model = FileTableModel()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        # Color swatch delegate for column 0
        self._color_delegate = ColorSwatchDelegate(self._table)
        self._table.setItemDelegateForColumn(0, self._color_delegate)

        # Progress bar delegate for % column (2)
        self._pct_delegate = PercentBarDelegate(self._table)
        self._table.setItemDelegateForColumn(2, self._pct_delegate)

        # Search highlight delegate for Name (3) and Path (5) columns
        self._highlight_delegate = SearchHighlightDelegate(self._table)
        self._table.setItemDelegateForColumn(3, self._highlight_delegate)
        self._table.setItemDelegateForColumn(5, self._highlight_delegate)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 22)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Size
        header.setSectionResizeMode(2, QHeaderView.Interactive)       # %
        header.resizeSection(2, 120)
        header.setSectionResizeMode(3, QHeaderView.Interactive)       # Name
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Modified
        header.setSectionResizeMode(5, QHeaderView.Stretch)           # Path
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Extension

        self._table.sortByColumn(1, Qt.DescendingOrder)
        self._table.clicked.connect(self._on_clicked)

        layout.addWidget(self._table, 1)

        # Debounce search to avoid filtering on every keystroke
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)

        self._search_input.textChanged.connect(lambda: self._search_timer.start())
        self._filename_only_cb.toggled.connect(lambda: self._apply_filter())

    def _apply_filter(self):
        term = self._search_input.text().strip()
        filename_only = self._filename_only_cb.isChecked()
        self._model.set_filter(term, filename_only)
        count = self._model.rowCount()
        if term:
            self._result_count.setText(f"{format_count(count)} matches")
        else:
            self._result_count.setText("")

    def set_root(self, root_node):
        self._search_input.clear()
        self._model.set_root(root_node)

    def clear(self):
        self._search_input.clear()
        self._model.clear()
        self._result_count.setText("")

    def highlight_paths(self, paths):
        self._model.set_highlighted_paths(paths)

    def _on_clicked(self, index):
        if not index.isValid():
            return
        node = self._model.node_at(index.row())
        if node:
            self.file_selected.emit(node)

    def _show_context_menu(self, pos):
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        node = self._model.node_at(index.row())
        if not node:
            return
        menu = QMenu(self)
        action = menu.addAction(FILE_MANAGER_LABEL)
        action.triggered.connect(lambda: show_in_finder(node.path))
        menu.addSeparator()
        delete_action = menu.addAction("Move to Trash")
        delete_action.triggered.connect(lambda: self._delete_node(node, permanent=False))
        perm_delete_action = menu.addAction("Delete Permanently")
        perm_delete_action.triggered.connect(lambda: self._delete_node(node, permanent=True))
        menu.addSeparator()
        google_action = menu.addAction(f'Google "{node.name}"')
        google_action.triggered.connect(lambda: google_search(node.name))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _delete_node(self, node, permanent=False):
        if confirm_and_delete(self, node.name, node.path, node.own_size, permanent):
            self.file_deleted.emit(node)
