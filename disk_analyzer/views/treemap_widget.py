from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen, QAction
from PySide6.QtWidgets import QWidget, QToolTip, QVBoxLayout, QLabel, QHBoxLayout, QMenu

from disk_analyzer.algorithms.squarify import squarify
from disk_analyzer.utils.colors import color_for_extension, DIRECTORY_COLOR, darker_color, text_color_for_bg
from disk_analyzer.utils.formatting import format_size
from disk_analyzer.utils.finder import show_in_finder, google_search, FILE_MANAGER_LABEL
from disk_analyzer.utils.delete_helper import confirm_and_delete


MAX_DEPTH = 12
MAX_RECTS = 5000
PADDING = 2


class BreadcrumbBar(QWidget):
    path_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(2)
        self._nodes = []

    def set_path(self, node):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._nodes = []
        path_nodes = []
        n = node
        while n is not None:
            path_nodes.append(n)
            n = n.parent
        path_nodes.reverse()

        for i, pn in enumerate(path_nodes):
            if i > 0:
                sep = QLabel(">")
                sep.setStyleSheet("color: #888; padding: 0 2px;")
                self._layout.addWidget(sep)
            btn = QLabel(pn.name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "color: #2196F3; padding: 2px 4px;"
                "text-decoration: underline;"
            )
            btn.mousePressEvent = lambda e, n=pn: self.path_clicked.emit(n)
            self._layout.addWidget(btn)
            self._nodes.append(pn)

        self._layout.addStretch()


class TreemapWidget(QWidget):
    directory_selected = Signal(object)
    show_in_tree = Signal(object)  # FileNode - request to reveal in folder tree
    file_deleted = Signal(object)  # FileNode - file was moved to trash

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = None
        self._current = None
        self.setMouseTracking(True)
        self.setMinimumSize(200, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._breadcrumb = BreadcrumbBar()
        self._breadcrumb.path_clicked.connect(self._on_breadcrumb_click)
        layout.addWidget(self._breadcrumb)

        self._canvas = _TreemapCanvas(self)
        layout.addWidget(self._canvas, 1)

    def set_root(self, root_node):
        self._root = root_node
        self._current = root_node
        self._breadcrumb.set_path(root_node)
        self._canvas.set_node(root_node)

    def clear(self):
        self._root = None
        self._current = None
        self._canvas.clear()

    def highlight_extension(self, ext):
        self._canvas.set_highlighted_ext(ext)

    def _on_breadcrumb_click(self, node):
        self._current = node
        self._breadcrumb.set_path(node)
        self._canvas.set_node(node)

    def _drill_down(self, node):
        if node.is_dir and node.children:
            self._current = node
            self._breadcrumb.set_path(node)
            self._canvas.set_node(node)
            self.directory_selected.emit(node)


def _flatten_treemap(node, rect, depth, result, rect_count):
    if rect_count[0] >= MAX_RECTS:
        return

    if not node.is_dir or not node.children or depth >= MAX_DEPTH:
        result.append((node, QRectF(rect), depth))
        rect_count[0] += 1
        return

    inner = rect.adjusted(PADDING, PADDING, -PADDING, -PADDING)
    if inner.width() <= 4 or inner.height() <= 4:
        result.append((node, QRectF(rect), depth))
        rect_count[0] += 1
        return

    children = node.sorted_children()
    items = [(child, child.cumulative_size) for child in children if child.cumulative_size > 0]
    if not items:
        result.append((node, QRectF(rect), depth))
        rect_count[0] += 1
        return

    child_rects = squarify(items, inner, min_area=16)

    for child_node, child_rect in child_rects:
        if rect_count[0] >= MAX_RECTS:
            break
        _flatten_treemap(child_node, child_rect, depth + 1, result, rect_count)


class _TreemapCanvas(QWidget):
    def __init__(self, treemap_widget):
        super().__init__(treemap_widget)
        self._treemap = treemap_widget
        self._node = None
        self._rects = []
        self._hovered_idx = -1
        self._highlighted_ext = None
        self.setMouseTracking(True)
        self.setMinimumSize(200, 150)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_highlighted_ext(self, ext):
        self._highlighted_ext = ext
        self.update()

    def set_node(self, node):
        self._node = node
        self._highlighted_ext = None
        self._recompute()
        self.update()

    def clear(self):
        self._node = None
        self._rects = []
        self.update()

    def _recompute(self):
        if not self._node or not self._node.children:
            self._rects = []
            return

        canvas_rect = QRectF(0, 0, self.width(), self.height())
        self._rects = []
        rect_count = [0]
        _flatten_treemap(self._node, canvas_rect, 0, self._rects, rect_count)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute()

    def paintEvent(self, event):
        if not self._rects:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(40, 40, 40))
            if self._node is None:
                painter.setPen(QColor(150, 150, 150))
                painter.drawText(self.rect(), Qt.AlignCenter, "Select a folder and click Scan")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        font = QFont("Helvetica Neue", 13)
        small_font = QFont("Helvetica Neue", 11)
        fm = QFontMetrics(font)
        sfm = QFontMetrics(small_font)

        # Dark background for directory containers
        painter.fillRect(self.rect(), QColor(25, 25, 25))
        for i, (node, rect, depth) in enumerate(self._rects):
            if node.is_dir:
                bg = QColor(35, 35, 40)
                painter.fillRect(rect, bg)

        for i, (node, rect, depth) in enumerate(self._rects):
            if node.is_dir and depth < MAX_DEPTH and node.children:
                continue

            color = color_for_extension(node.extension) if not node.is_dir else self._dominant_color(node)

            # Dim non-matching rects when an extension is highlighted
            if self._highlighted_ext is not None:
                ext = node.extension if not node.is_dir else ""
                if ext != self._highlighted_ext:
                    color = QColor(50, 50, 50)

            if i == self._hovered_idx:
                color = color.lighter(140)

            painter.fillRect(rect, color)

            # Thin dark border for separation
            painter.setPen(QPen(QColor(25, 25, 25), 1))
            painter.drawRect(rect)

            rw, rh = rect.width(), rect.height()
            if rw > 50 and rh > 20:
                txt_color = text_color_for_bg(color)
                painter.setPen(txt_color)
                text_rect = rect.adjusted(4, 3, -4, -3)

                label = node.name
                size_label = format_size(node.cumulative_size if node.is_dir else node.own_size)

                if rh > 40:
                    painter.setFont(font)
                    elided = fm.elidedText(label, Qt.ElideMiddle, int(text_rect.width()))
                    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, elided)
                    painter.setFont(small_font)
                    painter.setPen(txt_color)
                    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom, size_label)
                else:
                    painter.setFont(small_font)
                    elided = sfm.elidedText(label, Qt.ElideMiddle, int(text_rect.width()))
                    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        painter.end()

    def _dominant_color(self, dir_node):
        ext_sizes = {}
        stack = list(dir_node.children)
        limit = 5000
        while stack and limit > 0:
            n = stack.pop()
            limit -= 1
            if n.is_dir:
                stack.extend(n.children)
            else:
                ext = n.extension or ""
                ext_sizes[ext] = ext_sizes.get(ext, 0) + n.own_size
        if not ext_sizes:
            return DIRECTORY_COLOR
        dominant_ext = max(ext_sizes, key=ext_sizes.get)
        return color_for_extension(dominant_ext) if dominant_ext else DIRECTORY_COLOR

    def _node_at(self, pos):
        # First try leaf nodes (files / max-depth dirs)
        for i in range(len(self._rects) - 1, -1, -1):
            node, rect, depth = self._rects[i]
            if node.is_dir and depth < MAX_DEPTH and node.children:
                continue
            if rect.contains(pos):
                return node, i
        # Fall back to any directory container (padding/border areas)
        for i in range(len(self._rects) - 1, -1, -1):
            node, rect, depth = self._rects[i]
            if rect.contains(pos):
                return node, i
        return None, -1

    def mouseMoveEvent(self, event):
        pos = event.position()
        old_idx = self._hovered_idx
        node, idx = self._node_at(pos)
        self._hovered_idx = idx

        if node:
            size = node.cumulative_size if node.is_dir else node.own_size
            tip = f"{node.name}\n{format_size(size)}"
            if node.is_dir:
                tip += f"\n{node.file_count:,} files"
            tip += f"\n{node.path}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)

        if old_idx != self._hovered_idx:
            self.update()

    def mouseDoubleClickEvent(self, event):
        node, _ = self._node_at(event.position())
        if node:
            target = node if node.is_dir else node.parent
            if target and target.children:
                self._treemap._drill_down(target)

    def mousePressEvent(self, event):
        if event.button() == Qt.BackButton:
            if self._treemap._current and self._treemap._current.parent:
                self._treemap._drill_down(self._treemap._current.parent)

    def _show_context_menu(self, pos):
        node, _ = self._node_at(pos.toPointF() if hasattr(pos, 'toPointF') else pos)
        if not node:
            return
        menu = QMenu(self)
        tree_action = menu.addAction("Show in Tree")
        tree_action.triggered.connect(lambda: self._treemap.show_in_tree.emit(node))
        finder_action = menu.addAction(FILE_MANAGER_LABEL)
        finder_action.triggered.connect(lambda: show_in_finder(node.path))
        menu.addSeparator()
        delete_action = menu.addAction("Move to Trash")
        delete_action.triggered.connect(lambda: self._delete_node(node, permanent=False))
        perm_delete_action = menu.addAction("Delete Permanently")
        perm_delete_action.triggered.connect(lambda: self._delete_node(node, permanent=True))
        menu.addSeparator()
        google_action = menu.addAction(f'Google "{node.name}"')
        google_action.triggered.connect(lambda: google_search(node.name))
        menu.exec(self.mapToGlobal(pos))

    def _delete_node(self, node, permanent=False):
        size = node.cumulative_size if node.is_dir else node.own_size
        if confirm_and_delete(self, node.name, node.path, size, permanent):
            self._treemap.file_deleted.emit(node)
