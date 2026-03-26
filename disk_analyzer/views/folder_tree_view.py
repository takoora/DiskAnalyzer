from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex, Signal
from PySide6.QtWidgets import QTreeView, QHeaderView, QMenu, QApplication
from PySide6.QtGui import QAction, QColor, QIcon

from disk_analyzer.utils.formatting import format_size, format_percent, calc_percent
from disk_analyzer.utils.finder import show_in_finder, google_search, FILE_MANAGER_LABEL
from disk_analyzer.utils.delete_helper import confirm_and_delete
from disk_analyzer.views.progress_delegate import PercentBarDelegate


class FolderTreeModel(QAbstractItemModel):
    COLUMNS = ["Name", "Size", "Files", "%"]
    NAME_COL = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = None
        self._highlighted_paths = set()
        # Cache icons from system
        style = QApplication.style()
        self._folder_icon = style.standardIcon(style.StandardPixmap.SP_DirIcon)
        self._file_icon = style.standardIcon(style.StandardPixmap.SP_FileIcon)

    def set_root(self, root_node):
        self.beginResetModel()
        self._root = root_node
        self._highlighted_paths = set()
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._root = None
        self._highlighted_paths = set()
        self.endResetModel()

    def set_highlighted_paths(self, paths):
        self._highlighted_paths = paths
        self.layoutChanged.emit()

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def rowCount(self, parent=QModelIndex()):
        if not self._root:
            return 0
        node = self._node_from_index(parent)
        if node is None:
            return 0
        return len(node.children)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        if parent_node is None or row >= len(parent_node.children):
            return QModelIndex()
        child = self._sorted_children(parent_node)[row]
        return self.createIndex(row, column, child)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if node is None or node.parent is None or node.parent is self._root:
            return QModelIndex()
        parent = node.parent
        grandparent = parent.parent
        if grandparent is None:
            return QModelIndex()
        siblings = self._sorted_children(grandparent)
        for i, s in enumerate(siblings):
            if s is parent:
                return self.createIndex(i, 0, parent)
        return QModelIndex()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return node.name
            elif col == 1:
                return format_size(node.cumulative_size)
            elif col == 2:
                return f"{node.file_count:,}"
            elif col == 3:
                if self._root:
                    return format_percent(node.cumulative_size, self._root.cumulative_size)
                return "0.0%"
        elif role == Qt.UserRole:
            if col == 1:
                return node.cumulative_size
            elif col == 2:
                return node.file_count
            elif col == 3:
                if self._root:
                    return calc_percent(node.cumulative_size, self._root.cumulative_size)
                return 0.0
        elif role == Qt.DecorationRole:
            if col == 0:
                return self._folder_icon if node.is_dir else self._file_icon
        elif role == Qt.BackgroundRole:
            if self._highlighted_paths and node.path in self._highlighted_paths:
                return QColor(25, 118, 210, 60)
        elif role == Qt.TextAlignmentRole:
            if col in (1, 2):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def _node_from_index(self, index):
        if not index.isValid():
            return self._root
        return index.internalPointer()

    @staticmethod
    def _sorted_children(node):
        """Sort: directories first (by size desc), then files (by size desc)."""
        dirs = []
        files = []
        for c in node.children:
            if c.is_dir:
                dirs.append(c)
            else:
                files.append(c)
        dirs.sort(key=lambda c: c.cumulative_size, reverse=True)
        files.sort(key=lambda c: c.own_size, reverse=True)
        return dirs + files



class FolderTreeView(QTreeView):
    folder_selected = Signal(object)  # FileNode
    file_deleted = Signal(object)  # FileNode

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = FolderTreeModel()
        self.setModel(self._model)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Progress bar delegate for % column
        self._pct_delegate = PercentBarDelegate(self)
        self.setItemDelegateForColumn(3, self._pct_delegate)

        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(FolderTreeModel.COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.clicked.connect(self._on_clicked)

    def set_root(self, root_node):
        self._model.set_root(root_node)
        self.expandToDepth(0)

    def clear(self):
        self._model.clear()

    def highlight_paths(self, paths):
        self._model.set_highlighted_paths(paths)

    def reveal_node(self, target_node):
        """Expand the tree to reveal a node and select it."""
        # Build ancestor chain from root to target (or its parent dir)
        chain = []
        n = target_node
        while n is not None and n is not self._model._root:
            chain.append(n)
            n = n.parent
        chain.reverse()

        if not chain:
            return

        # Expand each ancestor
        parent_idx = QModelIndex()
        for ancestor in chain:
            parent_node = self._model._node_from_index(parent_idx)
            if not parent_node:
                return
            sorted_kids = self._model._sorted_children(parent_node)
            row = -1
            for i, kid in enumerate(sorted_kids):
                if kid is ancestor:
                    row = i
                    break
            if row < 0:
                return
            idx = self._model.index(row, 0, parent_idx)
            self.expand(idx)
            parent_idx = idx

        # Select and scroll to the final node (Name column)
        if parent_idx.isValid():
            name_idx = self._model.index(
                parent_idx.row(), FolderTreeModel.NAME_COL, parent_idx.parent()
            )
            if name_idx.isValid():
                self.setCurrentIndex(name_idx)
                self.scrollTo(name_idx)

    def _on_clicked(self, index):
        if not index.isValid():
            return
        node = index.internalPointer()
        if node:
            self.folder_selected.emit(node)

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        node = index.internalPointer()
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
        menu.exec(self.viewport().mapToGlobal(pos))

    def _delete_node(self, node, permanent=False):
        size = node.cumulative_size if node.is_dir else node.own_size
        if confirm_and_delete(self, node.name, node.path, size, permanent):
            self.file_deleted.emit(node)
