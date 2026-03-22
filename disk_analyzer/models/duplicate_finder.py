import os
import hashlib
import time
from enum import Enum
from collections import defaultdict

from PySide6.QtCore import QThread, Signal

from disk_analyzer.models.file_node import FileNode

# Threshold for using quick hash (first 4KB + last 4KB) before full hash
QUICK_HASH_THRESHOLD = 8192


class MatchStrategy(Enum):
    CONTENT_HASH = "Content Hash (SHA-256)"
    NAME_ONLY = "Same Filename"
    NAME_AND_SIZE = "Same Name + Size"
    SIZE_ONLY = "Same File Size"
    NAME_SIZE_DATE = "Same Name + Size + Date"


def _file_mtime(path):
    """Return file modification time, or 0 on error."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _quick_hash(path, file_size):
    """Hash first 4KB + last 4KB + file size as a fast fingerprint."""
    h = hashlib.sha256()
    h.update(file_size.to_bytes(8, "little"))
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            h.update(head)
            if file_size > 8192:
                f.seek(-4096, 2)
                tail = f.read(4096)
                h.update(tail)
    except (OSError, PermissionError):
        return None
    return h.hexdigest()


def _full_hash(path):
    """Compute full SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, PermissionError):
        return None
    return h.hexdigest()


def _format_eta(seconds):
    if seconds < 0:
        return ""
    s = int(seconds)
    if s < 60:
        return f"~{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"~{m}m {s}s"
    h, m = divmod(m, 60)
    return f"~{h}h {m}m"


class DuplicateFinder(QThread):
    """QThread worker that finds duplicate files under a FileNode tree."""

    # stage_name, stage_num, total_stages, files_checked, total_files, eta_str, current_file
    progress = Signal(str, int, int, int, int, str, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, root_node, strategy=MatchStrategy.CONTENT_HASH, parent=None):
        super().__init__(parent)
        self._root_node = root_node
        self._strategy = strategy
        self._cancelled = False

    def requestInterruption(self):
        self._cancelled = True
        super().requestInterruption()

    def run(self):
        try:
            all_files = list(self._root_node.all_files())
            total = len(all_files)

            if self._strategy == MatchStrategy.CONTENT_HASH:
                groups = self._find_by_content_hash(all_files, total)
            elif self._strategy == MatchStrategy.NAME_ONLY:
                groups = self._find_by_key(
                    all_files, total, key_fn=lambda f: f.name
                )
            elif self._strategy == MatchStrategy.NAME_AND_SIZE:
                groups = self._find_by_key(
                    all_files, total, key_fn=lambda f: (f.name, f.own_size)
                )
            elif self._strategy == MatchStrategy.SIZE_ONLY:
                groups = self._find_by_key(
                    all_files, total, key_fn=lambda f: f.own_size
                )
            elif self._strategy == MatchStrategy.NAME_SIZE_DATE:
                groups = self._find_by_key(
                    all_files, total,
                    key_fn=lambda f: (f.name, f.own_size, int(_file_mtime(f.path)))
                )
            else:
                groups = []

            if not self._cancelled:
                self.finished.emit(groups)
        except Exception as e:
            self.error.emit(str(e))

    def _find_by_key(self, all_files, total, key_fn):
        buckets = defaultdict(list)
        t0 = time.monotonic()
        for i, fnode in enumerate(all_files):
            if self._cancelled:
                return []
            if i % 500 == 0:
                eta = self._calc_eta(t0, i, total)
                self.progress.emit("Grouping", 1, 1, i + 1, total, eta, fnode.path)
            key = key_fn(fnode)
            buckets[key].append(fnode)
        return [group for group in buckets.values() if len(group) > 1]

    def _find_by_content_hash(self, all_files, total):
        # Phase 1: group by size (instant, in-memory)
        size_buckets = defaultdict(list)
        for i, fnode in enumerate(all_files):
            if self._cancelled:
                return []
            if i % 2000 == 0:
                self.progress.emit("Size grouping", 1, 3, i + 1, total, "", fnode.path)
            if fnode.own_size > 0:
                size_buckets[fnode.own_size].append(fnode)

        candidates = []
        for size, nodes in size_buckets.items():
            if len(nodes) > 1:
                candidates.extend(nodes)

        candidate_total = len(candidates)
        if candidate_total == 0:
            self.progress.emit("Complete", 3, 3, total, total, "", "")
            return []

        # Phase 2: quick hash — bytes-based ETA
        quick_buckets = defaultdict(list)
        full_hash_list = []
        total_quick_bytes = sum(min(f.own_size, 8192) for f in candidates)
        bytes_done = 0
        t0 = time.monotonic()

        for i, fnode in enumerate(candidates):
            if self._cancelled:
                return []

            file_cost = min(fnode.own_size, 8192)
            bytes_done += file_cost

            if i % 100 == 0:
                eta = self._calc_eta_bytes(t0, bytes_done, total_quick_bytes)
                self.progress.emit("Quick hash", 2, 3, i + 1, candidate_total, eta, fnode.path)

            if fnode.own_size > QUICK_HASH_THRESHOLD:
                qh = _quick_hash(fnode.path, fnode.own_size)
                if qh is not None:
                    quick_buckets[qh].append(fnode)
            else:
                full_hash_list.append(fnode)

        needs_full_hash = list(full_hash_list)
        for qh, nodes in quick_buckets.items():
            if len(nodes) > 1:
                needs_full_hash.extend(nodes)

        # Phase 3: full hash — bytes-based ETA (most accurate here)
        hash_buckets = defaultdict(list)
        full_total = len(needs_full_hash)
        total_full_bytes = sum(f.own_size for f in needs_full_hash)
        bytes_done = 0
        t0 = time.monotonic()

        for i, fnode in enumerate(needs_full_hash):
            if self._cancelled:
                return []

            bytes_done += fnode.own_size

            if i % 20 == 0:
                eta = self._calc_eta_bytes(t0, bytes_done, total_full_bytes)
                self.progress.emit("Full hash", 3, 3, i + 1, full_total, eta, fnode.path)

            fh = _full_hash(fnode.path)
            if fh is not None:
                hash_buckets[fh].append(fnode)

        return [group for group in hash_buckets.values() if len(group) > 1]

    @staticmethod
    def _calc_eta(t0, done, total):
        if done <= 0:
            return ""
        elapsed = time.monotonic() - t0
        if elapsed < 0.5:
            return ""
        rate = done / elapsed
        remaining = (total - done) / rate
        return _format_eta(remaining)

    @staticmethod
    def _calc_eta_bytes(t0, bytes_done, bytes_total):
        if bytes_done <= 0:
            return ""
        elapsed = time.monotonic() - t0
        if elapsed < 1.0:
            return ""
        rate = bytes_done / elapsed
        remaining = (bytes_total - bytes_done) / rate
        return _format_eta(remaining)
