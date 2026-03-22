import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QProgressBar,
    QTabWidget, QLabel, QStatusBar, QMenuBar, QSizePolicy,
    QSplitter,
)

from disk_analyzer.models.scan_worker import ScanWorker, NUM_WORKERS
from disk_analyzer.views.treemap_widget import TreemapWidget
from disk_analyzer.views.folder_tree_view import FolderTreeView
from disk_analyzer.views.file_list_view import FileListView
from disk_analyzer.views.file_type_view import FileTypeView
from disk_analyzer.utils.formatting import format_size, format_count


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DiskAnalyzer")
        self.resize(1200, 800)

        self._scan_worker = None
        self._root_node = None
        self._scan_start_time = 0
        self._disk_used = 0
        self._disk_total = 0

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._path_edit = QLineEdit("/")
        self._path_edit.setPlaceholderText("Select a folder to analyze...")
        self._path_edit.returnPressed.connect(self._start_scan)
        toolbar.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse  ⌘O")
        browse_btn.setShortcut(QKeySequence.Open)
        browse_btn.clicked.connect(self._browse)
        toolbar.addWidget(browse_btn)

        self._scan_btn = QPushButton("Scan  ⌘R")
        self._scan_btn.setShortcut(QKeySequence("Ctrl+R"))
        self._scan_btn.setDefault(True)
        self._scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self._scan_btn)

        self._cancel_btn = QPushButton("Cancel  ⌘.")
        self._cancel_btn.setShortcut(QKeySequence("Ctrl+."))
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_scan)
        toolbar.addWidget(self._cancel_btn)

        layout.addLayout(toolbar)

        # Progress bar (scan progress)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(18)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setStyleSheet("""
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
        """)
        layout.addWidget(self._progress_bar)

        # Progress label
        self._progress_label = QLabel()
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color: #888; font-size: 11px;")
        self._progress_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout.addWidget(self._progress_label)

        # Tabs
        self._tabs = QTabWidget()

        # --- "Disk Space" tab: composite layout ---
        disk_space_tab = QWidget()
        ds_layout = QVBoxLayout(disk_space_tab)
        ds_layout.setContentsMargins(0, 0, 0, 0)
        ds_layout.setSpacing(4)

        # Top row: Folder Tree | File Types (splitter)
        top_splitter = QSplitter(Qt.Horizontal)
        self._folder_tree = FolderTreeView()
        self._file_types = FileTypeView()
        top_splitter.addWidget(self._folder_tree)
        top_splitter.addWidget(self._file_types)
        top_splitter.setSizes([600, 400])

        # Bottom row: Treemap
        self._treemap = TreemapWidget()

        # Vertical splitter: top panels | treemap
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self._treemap)
        main_splitter.setSizes([300, 500])

        ds_layout.addWidget(main_splitter)
        self._tabs.addTab(disk_space_tab, "Disk Space")

        # --- File List tab ---
        self._file_list = FileListView()
        self._tabs.addTab(self._file_list, "File List")

        layout.addWidget(self._tabs, 1)

        # Cross-highlighting signals
        self._folder_tree.folder_selected.connect(self._on_folder_selected)
        self._file_types.extension_selected.connect(self._on_extension_selected)
        self._file_list.file_selected.connect(self._on_file_selected)
        self._treemap.show_in_tree.connect(self._on_show_in_tree)
        self._file_types.highlight_in_chart.connect(self._on_highlight_in_chart)
        self._file_types.reset_chart_highlight.connect(lambda: self._treemap.highlight_extension(None))

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")

        open_action = QAction("Open Folder...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._browse)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menubar.addMenu("View")
        for i in range(self._tabs.count()):
            action = QAction(self._tabs.tabText(i), self)
            action.setShortcut(f"Ctrl+{i + 1}")
            idx = i
            action.triggered.connect(lambda checked, idx=idx: self._tabs.setCurrentIndex(idx))
            view_menu.addAction(action)

    def _setup_statusbar(self):
        self._status_label = QLabel("Ready")
        self.statusBar().addWidget(self._status_label, 1)

        # Disk usage bar (shown after scan)
        self._disk_usage_bar = QProgressBar()
        self._disk_usage_bar.setMaximum(1000)
        self._disk_usage_bar.setFixedWidth(200)
        self._disk_usage_bar.setFixedHeight(16)
        self._disk_usage_bar.setTextVisible(False)
        self._disk_usage_bar.setVisible(False)
        self._disk_usage_bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e65100, stop:1 #ff9800);
                border-radius: 2px;
            }
        """)
        self.statusBar().addPermanentWidget(self._disk_usage_bar)

        self._disk_usage_label = QLabel("")
        self._disk_usage_label.setStyleSheet("color: #aaa; font-size: 11px; padding-right: 4px;")
        self._disk_usage_label.setVisible(False)
        self.statusBar().addPermanentWidget(self._disk_usage_label)

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet("color: #aaa; padding-right: 8px;")
        self.statusBar().addPermanentWidget(self._elapsed_label)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Folder to Analyze",
            self._path_edit.text() or os.path.expanduser("~"),
        )
        if path:
            self._path_edit.setText(path)
            self._start_scan()

    def _start_scan(self):
        path = self._path_edit.text().strip()
        if not path or not os.path.isdir(path):
            self._status_label.setText("Please select a valid folder")
            return

        if self._scan_worker and self._scan_worker.isRunning():
            return

        # Get disk info for status bar
        try:
            st = os.statvfs(path)
            self._disk_total = st.f_blocks * st.f_frsize
            self._disk_used = (st.f_blocks - st.f_bfree) * st.f_frsize
        except OSError:
            self._disk_total = 0
            self._disk_used = 0

        # Clear previous results
        self._treemap.clear()
        self._folder_tree.clear()
        self._file_list.clear()
        self._file_types.clear()
        self._root_node = None
        self._disk_usage_bar.setVisible(False)
        self._disk_usage_label.setVisible(False)

        # UI state
        self._scan_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._progress_label.setVisible(True)
        self._status_label.setText("Scanning...")
        self._scan_start_time = time.monotonic()
        self._elapsed_label.setText("0s")
        self._elapsed_timer.start()

        # Start worker
        self._scan_worker = ScanWorker(path)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _cancel_scan(self):
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.requestInterruption()
            self._scan_worker.wait(3000)
            self._elapsed_timer.stop()
            self._scan_btn.setEnabled(True)
            self._cancel_btn.setEnabled(False)
            self._progress_bar.setVisible(False)
            self._progress_label.setVisible(False)
            self._status_label.setText("Scan cancelled")

    def _poll_progress(self):
        if not self._scan_worker or not self._scan_worker.isRunning():
            return
        files, scanned, disk_used, threads, total_tasks, done_tasks = \
            self._scan_worker.get_snapshot()

        size_text = f"{format_size(scanned)} / {format_size(disk_used)}" if disk_used > 0 \
            else format_size(scanned)
        threads_info = f"Threads: {threads}/{NUM_WORKERS}"
        tasks_info = f"Tasks: {done_tasks}/{total_tasks}" if total_tasks > 0 else ""
        parts = [
            f"Scanned {files:,} files ({size_text})",
            threads_info,
            tasks_info,
        ]
        self._progress_label.setText("  |  ".join(p for p in parts if p))
        if total_tasks > 0:
            pct = min(int((done_tasks / total_tasks) * 1000), 1000)
            self._progress_bar.setValue(pct)

    def _on_scan_finished(self, root_node):
        self._elapsed_timer.stop()
        elapsed = time.monotonic() - self._scan_start_time
        self._elapsed_label.setText(self._format_elapsed(elapsed))

        self._root_node = root_node
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        self._status_label.setText(
            f"{format_count(root_node.file_count)} files, "
            f"{format_count(root_node.dir_count)} folders, "
            f"Total: {format_size(root_node.cumulative_size)}"
        )

        # Show disk usage bar in status bar
        if self._disk_total > 0:
            pct = min(int((self._disk_used / self._disk_total) * 1000), 1000)
            self._disk_usage_bar.setValue(pct)
            self._disk_usage_bar.setVisible(True)
            free = self._disk_total - self._disk_used
            free_pct = (free / self._disk_total) * 100 if self._disk_total > 0 else 0
            self._disk_usage_label.setText(
                f"{format_size(self._disk_used)} / {format_size(self._disk_total)} "
                f"({format_size(free)} free, {free_pct:.1f}%)"
            )
            self._disk_usage_label.setVisible(True)

        # Populate all views
        self._treemap.set_root(root_node)
        self._folder_tree.set_root(root_node)
        self._file_list.set_root(root_node)
        self._file_types.set_root(root_node)

    def _on_scan_error(self, error_msg):
        self._elapsed_timer.stop()
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        self._status_label.setText(f"Error: {error_msg}")

    def _update_elapsed(self):
        elapsed = time.monotonic() - self._scan_start_time
        self._elapsed_label.setText(self._format_elapsed(elapsed))
        self._poll_progress()

    @staticmethod
    def _format_elapsed(seconds):
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        return f"{m}m {s}s"

    # --- Cross-highlighting ---

    def _on_folder_selected(self, node):
        """Folder clicked: highlight all files in that folder across views."""
        paths = set()
        for f in node.all_files():
            paths.add(f.path)
        self._file_list.highlight_paths(paths)
        ext = self._dominant_ext(node) if node.is_dir else node.extension
        self._file_types.highlight_ext(ext)

    def _on_extension_selected(self, ext):
        """Extension clicked: highlight all files with that ext across views."""
        if not self._root_node:
            return
        paths = set()
        folder_paths = set()
        real_ext = ext if ext != "(no extension)" else ""
        for f in self._root_node.all_files():
            if f.extension == real_ext:
                paths.add(f.path)
                if f.parent:
                    folder_paths.add(f.parent.path)
        self._file_list.highlight_paths(paths)
        self._folder_tree.highlight_paths(folder_paths)

    def _on_file_selected(self, node):
        """File clicked: highlight that single file across views."""
        paths = {node.path}
        self._folder_tree.highlight_paths(paths)
        self._file_types.highlight_ext(node.extension or "(no extension)")

    def _on_show_in_tree(self, node):
        """Treemap context menu: reveal node in the folder tree."""
        self._folder_tree.reveal_node(node)
        self._folder_tree.highlight_paths({node.path})

    def _on_highlight_in_chart(self, ext):
        """Extension context menu: highlight files with this extension in treemap."""
        real_ext = ext if ext != "(no extension)" else ""
        self._treemap.highlight_extension(real_ext)

    @staticmethod
    def _dominant_ext(dir_node):
        ext_sizes = {}
        for f in dir_node.all_files():
            ext = f.extension or "(no extension)"
            ext_sizes[ext] = ext_sizes.get(ext, 0) + f.own_size
        if not ext_sizes:
            return ""
        return max(ext_sizes, key=ext_sizes.get)
