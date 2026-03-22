import os
import sys

from PySide6.QtCore import Qt, QAbstractTableModel, Signal, QThread
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel, QSplitter, QTabWidget, QTableView, QHeaderView,
    QAbstractItemView, QMessageBox, QSizePolicy, QProgressBar,
)

from disk_analyzer.models.snapshot import (
    save_snapshot, load_snapshot, list_snapshots, compare_snapshots,
    ComparisonResult,
)
from disk_analyzer.utils.formatting import format_size


# Material colors for dark theme
COLOR_RED = "#ef5350"
COLOR_GREEN = "#66bb6a"
COLOR_TEXT = "#dddddd"
COLOR_MUTED = "#999999"

_MOD = "⌘" if sys.platform == "darwin" else "Ctrl+"
_MOD_SHIFT = "⌘⇧" if sys.platform == "darwin" else "Ctrl+Shift+"


class _SaveWorker(QThread):
    """Saves a snapshot in a background thread."""
    finished = Signal(str)  # filepath
    error = Signal(str)

    def __init__(self, root_node, root_path, parent=None):
        super().__init__(parent)
        self._root_node = root_node
        self._root_path = root_path

    def run(self):
        try:
            filepath = save_snapshot(self._root_node, self._root_path)
            self.finished.emit(filepath)
        except Exception as e:
            self.error.emit(str(e))


class _CompareWorker(QThread):
    """Loads and compares two snapshots in a background thread."""
    finished = Signal(object)  # ComparisonResult
    error = Signal(str)

    def __init__(self, old_path, new_path, parent=None):
        super().__init__(parent)
        self._old_path = old_path
        self._new_path = new_path

    def run(self):
        try:
            old_snap = load_snapshot(self._old_path)
            new_snap = load_snapshot(self._new_path)
            result = compare_snapshots(old_snap, new_snap)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Table models
# ---------------------------------------------------------------------------

class _NewDeletedModel(QAbstractTableModel):
    """Model for New Files / Deleted Files tabs: columns Path, Size."""

    COLUMNS = ["Path", "Size"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # [(path, size), ...]

    def set_data(self, items):
        self.beginResetModel()
        self._data = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return 2

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None
        path, size = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return path
            elif col == 1:
                return format_size(size)
        elif role == Qt.UserRole:
            if col == 1:
                return size
        elif role == Qt.TextAlignmentRole:
            if col == 1:
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = order == Qt.DescendingOrder
        if column == 0:
            self._data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        elif column == 1:
            self._data.sort(key=lambda x: x[1], reverse=reverse)
        self.endResetModel()


class _ChangedModel(QAbstractTableModel):
    """Model for Grown / Shrunk tabs: columns Path, Old Size, New Size, Delta."""

    COLUMNS = ["Path", "Old Size", "New Size", "Delta"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # [(path, old_size, new_size), ...]

    def set_data(self, items):
        self.beginResetModel()
        self._data = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None
        path, old_size, new_size = self._data[index.row()]
        delta = new_size - old_size
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return path
            elif col == 1:
                return format_size(old_size)
            elif col == 2:
                return format_size(new_size)
            elif col == 3:
                prefix = "+" if delta > 0 else ""
                return f"{prefix}{format_size(abs(delta))}" if delta != 0 else "0 B"
        elif role == Qt.UserRole:
            if col == 1:
                return old_size
            elif col == 2:
                return new_size
            elif col == 3:
                return abs(delta)
        elif role == Qt.ForegroundRole:
            if col == 3:
                return QColor(COLOR_RED) if delta > 0 else QColor(COLOR_GREEN)
        elif role == Qt.TextAlignmentRole:
            if col in (1, 2, 3):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = order == Qt.DescendingOrder
        if column == 0:
            self._data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        elif column == 1:
            self._data.sort(key=lambda x: x[1], reverse=reverse)
        elif column == 2:
            self._data.sort(key=lambda x: x[2], reverse=reverse)
        elif column == 3:
            self._data.sort(key=lambda x: abs(x[2] - x[1]), reverse=reverse)
        self.endResetModel()


# ---------------------------------------------------------------------------
# Bar chart widget (QPainter-based)
# ---------------------------------------------------------------------------

class _SizeChangeBarChart(QWidget):
    """Custom-painted horizontal bar chart showing top 10 folders by size change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars = []  # [(label, delta_bytes), ...] already sorted
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, comparison_result):
        """Build top-10 folder deltas from a ComparisonResult."""
        folder_deltas = {}

        # Accumulate deltas per parent folder
        for path, size in comparison_result.new_files:
            folder = os.path.dirname(path)
            folder_deltas[folder] = folder_deltas.get(folder, 0) + size

        for path, size in comparison_result.deleted_files:
            folder = os.path.dirname(path)
            folder_deltas[folder] = folder_deltas.get(folder, 0) - size

        for path, old_size, new_size in comparison_result.grown_files:
            folder = os.path.dirname(path)
            folder_deltas[folder] = folder_deltas.get(folder, 0) + (new_size - old_size)

        for path, old_size, new_size in comparison_result.shrunk_files:
            folder = os.path.dirname(path)
            folder_deltas[folder] = folder_deltas.get(folder, 0) + (new_size - old_size)

        # Sort by absolute delta descending, take top 10
        sorted_deltas = sorted(folder_deltas.items(), key=lambda x: abs(x[1]), reverse=True)
        self._bars = sorted_deltas[:10]
        self.update()

    def clear(self):
        self._bars = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self._bars:
            painter.setPen(QColor(COLOR_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "No comparison data")
            painter.end()
            return

        font = QFont("Helvetica Neue", 11)
        small_font = QFont("Helvetica Neue", 10)
        painter.setFont(font)
        fm = QFontMetrics(font)

        max_abs = max(abs(d) for _, d in self._bars) if self._bars else 1
        if max_abs == 0:
            max_abs = 1

        margin_left = 10
        margin_right = 10
        margin_top = 10
        margin_bottom = 10
        label_width = 180  # space for folder name on left
        value_width = 90   # space for size label on right

        available_width = self.width() - margin_left - margin_right - label_width - value_width
        if available_width < 40:
            available_width = 40

        bar_count = len(self._bars)
        total_height = self.height() - margin_top - margin_bottom
        bar_height = min(max(int(total_height / max(bar_count, 1)) - 4, 12), 28)
        spacing = max(int((total_height - bar_count * bar_height) / max(bar_count, 1)), 2)

        y = margin_top

        for folder, delta in self._bars:
            # Folder label (left side)
            label = os.path.basename(folder) or folder
            painter.setFont(small_font)
            painter.setPen(QColor(COLOR_TEXT))
            elided = fm.elidedText(label, Qt.ElideMiddle, label_width - 4)
            label_rect = self.rect().adjusted(margin_left, y, 0, 0)
            label_rect.setWidth(label_width)
            label_rect.setHeight(bar_height)
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

            # Bar
            bar_x = margin_left + label_width
            bar_w = int((abs(delta) / max_abs) * available_width)
            bar_w = max(bar_w, 2)

            if delta > 0:
                color = QColor(COLOR_RED)
            elif delta < 0:
                color = QColor(COLOR_GREEN)
            else:
                color = QColor(COLOR_MUTED)

            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(bar_x, y + 1, bar_w, bar_height - 2, 3, 3)

            # Size delta label (right of bar)
            painter.setFont(small_font)
            painter.setPen(color)
            prefix = "+" if delta > 0 else ("-" if delta < 0 else "")
            size_text = f"{prefix}{format_size(abs(delta))}"
            value_rect = self.rect().adjusted(0, y, -margin_right, 0)
            value_rect.setLeft(bar_x + available_width + 4)
            value_rect.setHeight(bar_height)
            painter.drawText(value_rect, Qt.AlignLeft | Qt.AlignVCenter, size_text)

            y += bar_height + spacing

        painter.end()


# ---------------------------------------------------------------------------
# Main snapshot view widget
# ---------------------------------------------------------------------------

class SnapshotView(QWidget):
    """Snapshot comparison panel: save, select, compare, and visualize."""

    snapshot_saved = Signal(str)  # filepath of the saved snapshot

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_node = None
        self._root_path = None
        self._snapshot_map = {}  # combo index -> filepath

        self._setup_ui()
        self._refresh_snapshots()

    def set_root(self, root_node, root_path=None):
        """Set the current scan root node (needed for saving snapshots)."""
        self._root_node = root_node
        self._root_path = root_path or (root_node.path if root_node else None)

    def clear(self):
        self._root_node = None
        self._root_path = None

    # ---- UI setup ----

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Top panel: save / select / compare ---
        top_panel = QHBoxLayout()
        top_panel.setSpacing(8)

        self._save_btn = QPushButton("Save Snapshot")
        self._save_btn.setShortcut("Ctrl+S")
        self._save_btn.setToolTip(f"Save current scan as a snapshot ({_MOD}S)")
        self._save_btn.setFixedWidth(130)
        self._save_btn.clicked.connect(self._on_save)
        top_panel.addWidget(self._save_btn)

        self._save_progress = QProgressBar()
        self._save_progress.setMaximum(0)  # indeterminate
        self._save_progress.setFixedWidth(120)
        self._save_progress.setFixedHeight(16)
        self._save_progress.setTextVisible(False)
        self._save_progress.setVisible(False)
        self._save_progress.setStyleSheet("""
            QProgressBar { background: #2a2a2a; border: 1px solid #444; border-radius: 3px; }
            QProgressBar::chunk { background: #4285F4; border-radius: 2px; }
        """)
        top_panel.addWidget(self._save_progress)

        self._save_status = QLabel("")
        self._save_status.setStyleSheet("color: #888; font-size: 11px;")
        self._save_status.setVisible(False)
        top_panel.addWidget(self._save_status)

        top_panel.addSpacing(16)

        top_panel.addWidget(QLabel("Old:"))
        self._old_combo = QComboBox()
        self._old_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_panel.addWidget(self._old_combo, 1)

        top_panel.addWidget(QLabel("New:"))
        self._new_combo = QComboBox()
        self._new_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_panel.addWidget(self._new_combo, 1)

        self._compare_btn = QPushButton("Compare")
        self._compare_btn.setShortcut("Ctrl+Shift+C")
        self._compare_btn.setToolTip(f"Compare selected snapshots ({_MOD_SHIFT}C)")
        self._compare_btn.setFixedWidth(100)
        self._compare_btn.clicked.connect(self._on_compare)
        top_panel.addWidget(self._compare_btn)

        self._compare_progress = QProgressBar()
        self._compare_progress.setMaximum(0)
        self._compare_progress.setFixedWidth(120)
        self._compare_progress.setFixedHeight(16)
        self._compare_progress.setTextVisible(False)
        self._compare_progress.setVisible(False)
        self._compare_progress.setStyleSheet("""
            QProgressBar { background: #2a2a2a; border: 1px solid #444; border-radius: 3px; }
            QProgressBar::chunk { background: #4285F4; border-radius: 2px; }
        """)
        top_panel.addWidget(self._compare_progress)

        self._compare_status = QLabel("")
        self._compare_status.setStyleSheet("color: #888; font-size: 11px;")
        self._compare_status.setVisible(False)
        top_panel.addWidget(self._compare_status)

        layout.addLayout(top_panel)

        # --- Summary panel ---
        self._summary_widget = QWidget()
        summary_layout = QHBoxLayout(self._summary_widget)
        summary_layout.setContentsMargins(8, 4, 8, 4)
        summary_layout.setSpacing(20)

        self._old_total_label = QLabel()
        self._old_total_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 13px;")
        summary_layout.addWidget(self._old_total_label)

        self._new_total_label = QLabel()
        self._new_total_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 13px;")
        summary_layout.addWidget(self._new_total_label)

        self._delta_label = QLabel()
        self._delta_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        summary_layout.addWidget(self._delta_label)

        summary_layout.addStretch()
        self._summary_widget.setVisible(False)
        layout.addWidget(self._summary_widget)

        # --- Split view: bar chart | tabbed tables ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: bar chart
        self._bar_chart = _SizeChangeBarChart()
        splitter.addWidget(self._bar_chart)

        # Right: tabbed tables
        self._tab_widget = QTabWidget()

        self._new_table = self._make_table(_NewDeletedModel())
        self._tab_widget.addTab(self._new_table, "New Files")

        self._deleted_table = self._make_table(_NewDeletedModel())
        self._tab_widget.addTab(self._deleted_table, "Deleted Files")

        self._grown_table = self._make_table(_ChangedModel())
        self._tab_widget.addTab(self._grown_table, "Grown")

        self._shrunk_table = self._make_table(_ChangedModel())
        self._tab_widget.addTab(self._shrunk_table, "Shrunk")

        splitter.addWidget(self._tab_widget)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter, 1)

    @staticmethod
    def _make_table(model):
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # Default sort: size / delta descending
        sort_col = model.columnCount() - 1
        table.sortByColumn(sort_col, Qt.DescendingOrder)

        return table

    # ---- Snapshot management ----

    def _refresh_snapshots(self):
        self._old_combo.clear()
        self._new_combo.clear()
        self._snapshot_map = {}

        snapshots = list_snapshots()
        for i, (filepath, root_path, timestamp, total_size) in enumerate(snapshots):
            label = f"{root_path}  [{timestamp}]  ({format_size(total_size)})"
            self._old_combo.addItem(label)
            self._new_combo.addItem(label)
            self._snapshot_map[i] = filepath

        # Pre-select: old = second newest, new = newest (if available)
        if len(snapshots) >= 2:
            self._old_combo.setCurrentIndex(1)
            self._new_combo.setCurrentIndex(0)
        elif len(snapshots) == 1:
            self._old_combo.setCurrentIndex(0)
            self._new_combo.setCurrentIndex(0)

    def _on_save(self):
        if self._root_node is None:
            QMessageBox.information(self, "No Scan Data",
                                    "Run a scan first before saving a snapshot.")
            return

        self._save_btn.setEnabled(False)
        self._save_progress.setVisible(True)
        self._save_status.setText("Saving...")
        self._save_status.setVisible(True)

        self._save_worker = _SaveWorker(self._root_node, self._root_path)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.error.connect(self._on_save_error)
        self._save_worker.start()

    def _on_save_finished(self, filepath):
        self._save_btn.setEnabled(True)
        self._save_progress.setVisible(False)
        self._save_status.setText("Saved!")
        self._save_status.setStyleSheet("color: #66bb6a; font-size: 11px;")
        self._refresh_snapshots()
        self.snapshot_saved.emit(filepath)

    def _on_save_error(self, error_msg):
        self._save_btn.setEnabled(True)
        self._save_progress.setVisible(False)
        self._save_status.setText("Failed!")
        self._save_status.setStyleSheet("color: #ef5350; font-size: 11px;")
        QMessageBox.critical(self, "Save Error", f"Failed to save snapshot:\n{error_msg}")

    def _on_compare(self):
        old_idx = self._old_combo.currentIndex()
        new_idx = self._new_combo.currentIndex()

        if old_idx < 0 or new_idx < 0:
            QMessageBox.information(self, "Select Snapshots",
                                    "Please select two snapshots to compare.")
            return

        old_path = self._snapshot_map.get(old_idx)
        new_path = self._snapshot_map.get(new_idx)

        if not old_path or not new_path:
            return

        self._compare_btn.setEnabled(False)
        self._compare_progress.setVisible(True)
        self._compare_status.setText("Comparing...")
        self._compare_status.setStyleSheet("color: #888; font-size: 11px;")
        self._compare_status.setVisible(True)

        self._compare_worker = _CompareWorker(old_path, new_path)
        self._compare_worker.finished.connect(self._on_compare_finished)
        self._compare_worker.error.connect(self._on_compare_error)
        self._compare_worker.start()

    def _on_compare_finished(self, result):
        self._compare_btn.setEnabled(True)
        self._compare_progress.setVisible(False)
        self._compare_status.setText("Done!")
        self._compare_status.setStyleSheet("color: #66bb6a; font-size: 11px;")
        self._show_result(result)

    def _on_compare_error(self, error_msg):
        self._compare_btn.setEnabled(True)
        self._compare_progress.setVisible(False)
        self._compare_status.setText("Failed!")
        self._compare_status.setStyleSheet("color: #ef5350; font-size: 11px;")
        QMessageBox.warning(self, "Compare Error", f"Failed to compare snapshots:\n{error_msg}")

    def _show_result(self, result):
        # Summary
        self._old_total_label.setText(f"Old Total: {format_size(result.total_old_size)}")
        self._new_total_label.setText(f"New Total: {format_size(result.total_new_size)}")

        delta = result.size_delta
        if delta > 0:
            prefix = "+"
            color = COLOR_RED
        elif delta < 0:
            prefix = "-"
            color = COLOR_GREEN
        else:
            prefix = ""
            color = COLOR_MUTED

        self._delta_label.setText(f"Delta: {prefix}{format_size(abs(delta))}")
        self._delta_label.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold;"
        )
        self._summary_widget.setVisible(True)

        # Bar chart
        self._bar_chart.set_data(result)

        # Tables
        self._new_table.model().set_data(result.new_files)
        self._deleted_table.model().set_data(result.deleted_files)
        self._grown_table.model().set_data(result.grown_files)
        self._shrunk_table.model().set_data(result.shrunk_files)

        # Update tab labels with counts
        self._tab_widget.setTabText(0, f"New Files ({len(result.new_files)})")
        self._tab_widget.setTabText(1, f"Deleted Files ({len(result.deleted_files)})")
        self._tab_widget.setTabText(2, f"Grown ({len(result.grown_files)})")
        self._tab_widget.setTabText(3, f"Shrunk ({len(result.shrunk_files)})")
