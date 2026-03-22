import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QModelIndex, Signal
from PySide6.QtGui import QColor, QStandardItemModel, QStandardItem, QAction, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QProgressBar, QLabel, QTreeView, QHeaderView, QMenu,
    QMessageBox, QAbstractItemView, QSizePolicy, QDialog,
    QRadioButton, QButtonGroup, QScrollArea, QFrame, QGridLayout,
)

_MOD = "⌘" if sys.platform == "darwin" else "Ctrl+"

from disk_analyzer.models.duplicate_finder import DuplicateFinder, MatchStrategy
from disk_analyzer.utils.colors import _HASH_PALETTE
from disk_analyzer.utils.formatting import format_size, format_count
from disk_analyzer.utils.finder import show_in_finder, move_to_trash, permanent_delete, google_search, FILE_MANAGER_LABEL


# Alternating group background colors (semi-transparent for dark theme)
_GROUP_COLORS = [
    QColor(r.red(), r.green(), r.blue(), 35)
    for r in _HASH_PALETTE[:8]
]

# Columns
COL_NAME = 0
COL_PATH = 1
COL_SIZE = 2
COL_DATE = 3
COLUMN_HEADERS = ["Name", "Path", "Size", "Date Modified"]

# Custom roles
FILE_NODE_ROLE = Qt.UserRole + 1
GROUP_INDEX_ROLE = Qt.UserRole + 2
SIZE_SORT_ROLE = Qt.UserRole + 3
DATE_SORT_ROLE = Qt.UserRole + 4


class DuplicateView(QWidget):
    """Widget for finding and managing duplicate files."""

    file_deleted = Signal()  # emitted when a file is deleted/trashed
    search_started = Signal()
    search_progress = Signal(str, int)  # stage_label, percent (0-1000)
    search_finished = Signal(str)  # summary text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_node = None
        self._worker = None
        self._duplicate_groups = []

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top panel: strategy selector + buttons ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        top_bar.addWidget(QLabel("Match by:"))

        self._strategy_combo = QComboBox()
        for strategy in MatchStrategy:
            self._strategy_combo.addItem(strategy.value, strategy)
        self._strategy_combo.setCurrentIndex(0)
        self._strategy_combo.setMinimumWidth(200)
        top_bar.addWidget(self._strategy_combo)

        self._find_btn = QPushButton("Find Duplicates")
        self._find_btn.setShortcut("Ctrl+D")
        self._find_btn.setToolTip(f"Scan a folder first, then click to find duplicates ({_MOD}D)")
        self._find_btn.clicked.connect(self._start_search)
        top_bar.addWidget(self._find_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setShortcut("Ctrl+.")
        self._cancel_btn.setToolTip(f"Cancel the duplicate search ({_MOD}.)")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_search)
        top_bar.addWidget(self._cancel_btn)

        top_bar.addStretch()

        self._delete_interactive_btn = QPushButton("Delete Interactively...")
        self._delete_interactive_btn.setEnabled(False)
        self._delete_interactive_btn.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; padding: 4px 12px; }"
            "QPushButton:hover { background: #1976d2; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._delete_interactive_btn.clicked.connect(self._delete_interactively)
        top_bar.addWidget(self._delete_interactive_btn)

        self._delete_all_btn = QPushButton("Delete All Duplicates (Keep First)")
        self._delete_all_btn.setEnabled(False)
        self._delete_all_btn.setStyleSheet(
            "QPushButton { background: #c62828; color: white; padding: 4px 12px; }"
            "QPushButton:hover { background: #e53935; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._delete_all_btn.clicked.connect(self._delete_all_duplicates)
        top_bar.addWidget(self._delete_all_btn)

        layout.addLayout(top_bar)

        # --- Stage indicator ---
        stage_bar = QHBoxLayout()
        stage_bar.setSpacing(8)

        self._stage_label = QLabel()
        self._stage_label.setStyleSheet("color: #4285F4; font-size: 12px; font-weight: bold;")
        self._stage_label.setVisible(False)
        stage_bar.addWidget(self._stage_label)

        self._stage_detail = QLabel()
        self._stage_detail.setStyleSheet("color: #888; font-size: 11px;")
        self._stage_detail.setVisible(False)
        stage_bar.addWidget(self._stage_detail)

        stage_bar.addStretch()
        layout.addLayout(stage_bar)

        # --- Progress bar ---
        _pbar_style = """
            QProgressBar {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                color: #ddd;
                font-size: 11px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a73e8, stop:1 #4285F4);
                border-radius: 3px;
            }
        """
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(18)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setStyleSheet(_pbar_style)
        layout.addWidget(self._progress_bar)

        # --- Progress label ---
        self._progress_label = QLabel()
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color: #888; font-size: 11px;")
        self._progress_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout.addWidget(self._progress_label)

        # --- Summary label ---
        self._summary_label = QLabel("Scan a folder first, then click Find Duplicates.")
        self._summary_label.setStyleSheet("color: #aaa; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._summary_label)

        # --- Results tree ---
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(COLUMN_HEADERS)

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setAlternatingRowColors(False)  # we handle group coloring ourselves
        self._tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tree.setUniformRowHeights(True)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.setSortingEnabled(True)

        header = self._tree.header()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_PATH, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_DATE, QHeaderView.ResizeToContents)
        header.resizeSection(COL_NAME, 200)

        layout.addWidget(self._tree, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_root(self, root_node):
        """Called by the main window after a scan completes."""
        self._root_node = root_node
        self._find_btn.setEnabled(True)
        self._clear_results()
        self._summary_label.setText(
            f"Ready to search {format_count(root_node.file_count)} files. "
            "Select a strategy and click Find Duplicates."
        )

    def clear(self):
        """Reset everything."""
        self._root_node = None
        self._clear_results()
        self._summary_label.setText("Scan a folder first, then click Find Duplicates.")

    # ------------------------------------------------------------------
    # Search lifecycle
    # ------------------------------------------------------------------

    def _start_search(self):
        if self._root_node is None:
            msg = QMessageBox(QMessageBox.Information, "No Scan Data",
                "Please scan a folder first (Disk Space tab), then come back to find duplicates.",
                QMessageBox.Ok, self)
            msg.exec()
            return
        if self._worker and self._worker.isRunning():
            return

        strategy = self._strategy_combo.currentData()
        self._clear_results()
        self.search_started.emit()

        self._find_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._stage_label.setVisible(True)
        self._stage_detail.setVisible(True)
        self._stage_label.setText("Starting...")
        self._stage_detail.setText("")
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText("")
        self._summary_label.setText("Searching for duplicates...")

        self._worker = DuplicateFinder(self._root_node, strategy)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_search(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(3000)
        self._find_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        self._stage_label.setVisible(False)
        self._stage_detail.setVisible(False)
        self._summary_label.setText("Search cancelled.")

    def _on_progress(self, stage_name, stage_num, total_stages, checked, total, eta, current_file):
        stage_text = f"Stage {stage_num}/{total_stages}: {stage_name}"
        detail_text = f"{format_count(checked)} / {format_count(total)} files"
        self._stage_label.setText(stage_text)
        self._stage_detail.setText(detail_text)
        pct = 0
        if total > 0:
            pct = min(int((checked / total) * 1000), 1000)
            self._progress_bar.setValue(pct)
        self._progress_label.setText(current_file)
        status = f"Dup {stage_num}/{total_stages}: {stage_name}"
        self.search_progress.emit(status, pct)

    def _on_finished(self, groups):
        self._find_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        self._stage_label.setVisible(False)
        self._stage_detail.setVisible(False)

        self._duplicate_groups = groups
        self._populate_tree(groups)

        # Summary
        total_groups = len(groups)
        total_files = sum(len(g) for g in groups)
        wasted = sum(
            sum(f.own_size for f in g[1:])  # everything except the "first" copy
            for g in groups
        )
        if total_groups > 0:
            summary = (
                f"Found {format_count(total_groups)} duplicate groups, "
                f"{format_count(total_files)} files, "
                f"{format_size(wasted)} wasted space"
            )
            self._summary_label.setText(summary)
            self._delete_all_btn.setEnabled(True)
            self._delete_interactive_btn.setEnabled(True)
            self.search_finished.emit(summary)
        else:
            self._summary_label.setText("No duplicates found.")
            self.search_finished.emit("No duplicates found.")

    def _on_error(self, msg):
        self._find_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        self._summary_label.setText(f"Error: {msg}")

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _populate_tree(self, groups):
        self._model.removeRows(0, self._model.rowCount())

        # Sort groups by total wasted size descending
        sorted_groups = sorted(
            groups,
            key=lambda g: sum(f.own_size for f in g),
            reverse=True,
        )

        for group_idx, group in enumerate(sorted_groups):
            bg_color = _GROUP_COLORS[group_idx % len(_GROUP_COLORS)]
            group_size = group[0].own_size if group else 0
            wasted = sum(f.own_size for f in group[1:])

            # Group parent row
            group_item = QStandardItem(
                f"Group {group_idx + 1}: {group[0].name}  "
                f"({len(group)} files, {format_size(wasted)} wasted)"
            )
            group_item.setEditable(False)
            group_item.setData(group_idx, GROUP_INDEX_ROLE)
            group_item.setBackground(bg_color)

            # Placeholder items for other columns in the group row
            group_path = QStandardItem("")
            group_path.setEditable(False)
            group_path.setBackground(bg_color)

            group_size_item = QStandardItem(format_size(group_size))
            group_size_item.setEditable(False)
            group_size_item.setData(group_size, SIZE_SORT_ROLE)
            group_size_item.setBackground(bg_color)
            group_size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            group_date = QStandardItem("")
            group_date.setEditable(False)
            group_date.setBackground(bg_color)

            self._model.appendRow([group_item, group_path, group_size_item, group_date])

            # Child rows (individual files)
            for fnode in group:
                mtime = _file_mtime_str(fnode.path)
                mtime_ts = _file_mtime_ts(fnode.path)

                name_item = QStandardItem(fnode.name)
                name_item.setEditable(False)
                name_item.setData(fnode, FILE_NODE_ROLE)
                name_item.setData(group_idx, GROUP_INDEX_ROLE)
                name_item.setBackground(bg_color)

                dir_path = os.path.dirname(fnode.path)
                path_item = QStandardItem(dir_path)
                path_item.setEditable(False)
                path_item.setBackground(bg_color)
                path_item.setForeground(QColor(170, 170, 170))

                size_item = QStandardItem(format_size(fnode.own_size))
                size_item.setEditable(False)
                size_item.setData(fnode.own_size, SIZE_SORT_ROLE)
                size_item.setBackground(bg_color)
                size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                date_item = QStandardItem(mtime)
                date_item.setEditable(False)
                date_item.setData(mtime_ts, DATE_SORT_ROLE)
                date_item.setBackground(bg_color)

                group_item.appendRow([name_item, path_item, size_item, date_item])

        self._tree.expandAll()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        index = self._tree.indexAt(pos)
        if not index.isValid():
            return

        # Get the name-column item for the clicked row
        name_index = index.siblingAtColumn(COL_NAME)
        item = self._model.itemFromIndex(name_index)
        if item is None:
            return

        fnode = item.data(FILE_NODE_ROLE)
        if fnode is None:
            # Clicked on a group header row, not a file
            return

        menu = QMenu(self)

        show_action = QAction(FILE_MANAGER_LABEL, self)
        show_action.triggered.connect(lambda: show_in_finder(fnode.path))
        menu.addAction(show_action)

        menu.addSeparator()

        trash_action = QAction("Move to Trash", self)
        trash_action.triggered.connect(lambda: self._trash_file(fnode, item))
        menu.addAction(trash_action)

        delete_action = QAction("Delete Permanently", self)
        delete_action.triggered.connect(lambda: self._permanently_delete(fnode, item))
        menu.addAction(delete_action)

        menu.addSeparator()

        google_action = QAction(f'Google "{fnode.name}"', self)
        google_action.triggered.connect(lambda: google_search(fnode.name))
        menu.addAction(google_action)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _trash_file(self, fnode, item):
        reply = QMessageBox.question(
            self, "Move to Trash",
            f"Move this file to Trash?\n\n{fnode.path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if move_to_trash(fnode.path):
                self._remove_item_from_tree(item)
                self.file_deleted.emit()
            else:
                QMessageBox.warning(self, "Error", f"Could not move to Trash:\n{fnode.path}")

    def _permanently_delete(self, fnode, item):
        reply = QMessageBox.warning(
            self, "Delete Permanently",
            f"Permanently delete this file? This cannot be undone.\n\n{fnode.path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if permanent_delete(fnode.path):
                self._remove_item_from_tree(item)
                self.file_deleted.emit()
            else:
                QMessageBox.warning(self, "Error", f"Could not delete:\n{fnode.path}")

    def _remove_item_from_tree(self, item):
        """Remove a file item from the tree. If group becomes < 2, remove the group."""
        parent = item.parent()
        if parent is not None:
            row = item.row()
            parent.removeRow(row)
            # If group now has fewer than 2 children, remove the group entirely
            if parent.rowCount() < 2:
                group_row = parent.row()
                self._model.removeRow(group_row)
        self._update_summary()

    def _update_summary(self):
        """Recount groups and files from the current tree state."""
        total_groups = self._model.rowCount()
        total_files = 0
        wasted = 0
        for row in range(total_groups):
            group_item = self._model.item(row, COL_NAME)
            if group_item is None:
                continue
            child_count = group_item.rowCount()
            total_files += child_count
            # Wasted = all but the first child in each group
            for c in range(1, child_count):
                child = group_item.child(c, COL_SIZE)
                if child is not None:
                    size = child.data(SIZE_SORT_ROLE)
                    if size is not None:
                        wasted += size

        if total_groups > 0:
            self._summary_label.setText(
                f"Found {format_count(total_groups)} duplicate groups, "
                f"{format_count(total_files)} files, "
                f"{format_size(wasted)} wasted space"
            )
            self._delete_all_btn.setEnabled(True)
        else:
            self._summary_label.setText("No duplicates remaining.")
            self._delete_all_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Bulk delete
    # ------------------------------------------------------------------

    def _delete_interactively(self):
        """Walk through each group one at a time, letting the user pick which to keep."""
        if not self._duplicate_groups:
            return
        dialog = _InteractiveDeleteDialog(self._duplicate_groups, self)
        dialog.exec()
        if dialog.deleted_files:
            self.file_deleted.emit()

    def _delete_all_duplicates(self):
        """Delete all duplicates, keeping the first file in each group."""
        total_groups = self._model.rowCount()
        if total_groups == 0:
            return

        # Count files to delete
        to_delete = 0
        for row in range(total_groups):
            group_item = self._model.item(row, COL_NAME)
            if group_item is not None:
                to_delete += max(0, group_item.rowCount() - 1)

        if to_delete == 0:
            return

        reply = QMessageBox.warning(
            self, "Delete All Duplicates",
            f"This will move {format_count(to_delete)} duplicate files to Trash, "
            f"keeping the first file in each group.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted = 0
        failed = 0

        # Process groups in reverse so row indices stay valid
        for row in range(total_groups - 1, -1, -1):
            group_item = self._model.item(row, COL_NAME)
            if group_item is None:
                continue
            # Delete children in reverse order, skipping the first (index 0)
            for c in range(group_item.rowCount() - 1, 0, -1):
                child = group_item.child(c, COL_NAME)
                if child is None:
                    continue
                fnode = child.data(FILE_NODE_ROLE)
                if fnode is None:
                    continue
                if move_to_trash(fnode.path):
                    group_item.removeRow(c)
                    deleted += 1
                else:
                    failed += 1

            # If group has fewer than 2 children, remove it
            if group_item.rowCount() < 2:
                self._model.removeRow(row)

        self._update_summary()
        self.file_deleted.emit()

        msg = f"Moved {format_count(deleted)} files to Trash."
        if failed > 0:
            msg += f"\n{format_count(failed)} files could not be deleted."
        QMessageBox.information(self, "Bulk Delete Complete", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_results(self):
        self._model.removeRows(0, self._model.rowCount())
        self._duplicate_groups = []
        self._delete_all_btn.setEnabled(False)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _file_mtime_str(path):
    """Format file modification time as a readable string."""
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


def _file_mtime_ts(path):
    """Return file modification timestamp for sorting."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


class _InteractiveDeleteDialog(QDialog):
    """Dialog that shows one duplicate group at a time for the user to pick which to keep."""

    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Duplicates Interactively")
        self.resize(850, 450)
        self._groups = groups
        self._current = 0
        self._deleted = []  # list of FileNode that were trashed

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        self._header = QLabel()
        self._header.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
        layout.addWidget(self._header)

        # Scroll area for file options
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self._scroll, 1)

        self._radio_group = QButtonGroup(self)

        # Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self._show_btn = QPushButton(FILE_MANAGER_LABEL)
        self._show_btn.clicked.connect(self._show_selected)
        btn_bar.addWidget(self._show_btn)

        btn_bar.addStretch()

        self._skip_btn = QPushButton("Skip")
        self._skip_btn.setToolTip("Skip this group without deleting anything")
        self._skip_btn.clicked.connect(self._skip)
        btn_bar.addWidget(self._skip_btn)

        self._keep_btn = QPushButton("Keep Selected, Delete Others")
        self._keep_btn.setStyleSheet(
            "QPushButton { background: #c62828; color: white; padding: 6px 16px; }"
            "QPushButton:hover { background: #e53935; }"
        )
        self._keep_btn.clicked.connect(self._delete_others)
        btn_bar.addWidget(self._keep_btn)

        layout.addLayout(btn_bar)

        # Progress
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._progress_label)

        self._load_group()

    def _load_group(self):
        if self._current >= len(self._groups):
            self._finish()
            return

        group = self._groups[self._current]
        self._header.setText(
            f"Group {self._current + 1} of {len(self._groups)}  —  "
            f"{len(group)} copies  —  {format_size(group[0].own_size)} each"
        )
        self._progress_label.setText(
            f"Deleted so far: {len(self._deleted)} files, "
            f"{format_size(sum(f.own_size for f in self._deleted))} freed"
        )

        # Clear old radios
        for btn in self._radio_group.buttons():
            self._radio_group.removeButton(btn)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(4, 4, 4, 4)

        # Column headers
        for col, header in enumerate(["", "Name", "Path", "Size", "Modified"]):
            lbl = QLabel(f"<b>{header}</b>")
            lbl.setStyleSheet("color: #aaa; font-size: 12px; padding: 4px 2px;")
            grid.addWidget(lbl, 0, col)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #555;")
        grid.addWidget(sep, 1, 0, 1, 5)

        for row, fnode in enumerate(group, 2):
            # Alternating row background
            bg = "background: #2a2a2a;" if (row % 2 == 0) else "background: #333;"

            radio = QRadioButton()
            if row == 2:
                radio.setChecked(True)
            radio.setProperty("fnode", fnode)
            self._radio_group.addButton(radio, row - 2)
            radio.setStyleSheet(bg)
            grid.addWidget(radio, row, 0)

            name_lbl = QLabel(fnode.name)
            name_lbl.setStyleSheet(f"color: #eee; font-size: 13px; font-weight: bold; padding: 6px 4px; {bg}")
            grid.addWidget(name_lbl, row, 1)

            path_lbl = QLabel(os.path.dirname(fnode.path))
            path_lbl.setStyleSheet(f"color: #aaa; font-size: 12px; padding: 6px 4px; {bg}")
            path_lbl.setWordWrap(True)
            grid.addWidget(path_lbl, row, 2)

            size_lbl = QLabel(format_size(fnode.own_size))
            size_lbl.setStyleSheet(f"color: #eee; font-size: 12px; padding: 6px 4px; {bg}")
            size_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(size_lbl, row, 3)

            mtime = _file_mtime_str(fnode.path)
            date_lbl = QLabel(mtime)
            date_lbl.setStyleSheet(f"color: #aaa; font-size: 12px; padding: 6px 4px; {bg}")
            grid.addWidget(date_lbl, row, 4)

        grid.setColumnStretch(2, 1)
        grid.setColumnMinimumWidth(1, 120)
        grid.setColumnMinimumWidth(3, 80)
        grid.setColumnMinimumWidth(4, 130)

        outer.addLayout(grid)
        outer.addStretch()
        self._scroll.setWidget(container)

    def _show_selected(self):
        checked = self._radio_group.checkedButton()
        if checked:
            fnode = checked.property("fnode")
            show_in_finder(fnode.path)

    def _skip(self):
        self._current += 1
        self._load_group()

    def _delete_others(self):
        checked = self._radio_group.checkedButton()
        if not checked:
            return

        keep_fnode = checked.property("fnode")
        group = self._groups[self._current]

        for fnode in group:
            if fnode is keep_fnode:
                continue
            if move_to_trash(fnode.path):
                self._deleted.append(fnode)

        self._current += 1
        self._load_group()

    def _finish(self):
        total_freed = sum(f.own_size for f in self._deleted)
        QMessageBox.information(
            self, "Interactive Delete Complete",
            f"Deleted {len(self._deleted)} files, freed {format_size(total_freed)}."
        )
        self.accept()

    @property
    def deleted_files(self):
        return self._deleted
