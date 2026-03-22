import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal

from disk_analyzer.models.file_node import FileNode
from disk_analyzer.models.bulk_readdir import bulk_readdir

SKIP_DIRS = {
    ".Spotlight-V100", ".fseventsd", ".Trashes",
    ".DocumentRevisions-V100", ".TemporaryItems",
}

# APFS firmlink targets and system volumes to skip:
# - /System/Volumes/Data: mirrors root via firmlinks (avoids double-counting)
# - /System/Volumes/Preboot: macOS boot/cryptex volumes (not user data)
# - /System/Volumes/Recovery: macOS recovery partition
# - /System/Volumes/VM: virtual memory swap files
# - /System/Volumes/Update: macOS update staging
SKIP_PATHS = {
    "/System/Volumes/Data",
    "/System/Volumes/Preboot",
    "/System/Volumes/Recovery",
    "/System/Volumes/VM",
    "/System/Volumes/Update",
    "/System/Volumes/xarts",
    "/System/Volumes/iSCPreboot",
    "/System/Volumes/Hardware",
    "/System/Volumes/BaseSystem",
    "/System/Volumes/FieldService",
    "/System/Volumes/FieldServiceDiagnostic",
    "/System/Volumes/FieldServiceRepair",
}

PARALLEL_DEPTH = 3
NUM_WORKERS = 4


class ScanWorker(QThread):
    finished = Signal(object)  # root FileNode
    error = Signal(str)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.root_path = root_path
        self._cancelled = False
        self._disk_used = 0

        self._lock = threading.Lock()
        self._files_scanned = 0
        self._total_size = 0
        self._active_threads = 0
        self._total_tasks = 0
        self._completed_tasks = 0

    def run(self):
        try:
            self._disk_used = self._get_disk_used(self.root_path)

            # Phase 1: shallow scan to discover work items
            root_node, work_items = self._shallow_scan(self.root_path, depth=0)

            if self._cancelled:
                return

            self._total_tasks = len(work_items)

            # Phase 2: parallel deep scan
            if work_items:
                with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
                    future_to_item = {}
                    for parent_node, dir_path in work_items:
                        if self._cancelled:
                            break
                        future = pool.submit(self._deep_scan, dir_path)
                        future_to_item[future] = parent_node

                    for future in as_completed(future_to_item):
                        if self._cancelled:
                            pool.shutdown(wait=False, cancel_futures=True)
                            break
                        parent_node = future_to_item[future]
                        try:
                            child_node = future.result()
                            parent_node.add_child_fast(child_node)
                        except Exception:
                            pass
                        with self._lock:
                            self._completed_tasks += 1

            if not self._cancelled:
                # Phase 3: single post-order pass to compute cumulative stats
                root_node.finalize()
                self.finished.emit(root_node)
        except Exception as e:
            self.error.emit(str(e))

    def requestInterruption(self):
        self._cancelled = True
        super().requestInterruption()

    def _get_disk_used(self, path):
        try:
            st = os.statvfs(path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bfree * st.f_frsize
            return total - free
        except OSError:
            return 0

    def _shallow_scan(self, dir_path, depth):
        dir_name = os.path.basename(dir_path) or dir_path
        node = FileNode(dir_name, dir_path, is_dir=True)
        work_items = []

        try:
            entries = bulk_readdir(dir_path)
        except (PermissionError, OSError) as e:
            node.error = str(e)
            return node, work_items

        for name, is_dir, alloc_size in entries:
            if self._cancelled:
                break
            if name in SKIP_DIRS:
                continue
            full_path = os.path.join(dir_path, name)
            if full_path in SKIP_PATHS:
                continue
            if is_dir:
                if depth < PARALLEL_DEPTH:
                    child_node, child_work = self._shallow_scan(full_path, depth + 1)
                    node.add_child_fast(child_node)
                    work_items.extend(child_work)
                else:
                    work_items.append((node, full_path))
            else:
                child = FileNode(name, full_path, own_size=alloc_size)
                node.add_child_fast(child)
                self._increment_counters(1, alloc_size)

        return node, work_items

    def _deep_scan(self, dir_path):
        with self._lock:
            self._active_threads += 1
        try:
            return self._scan_recursive(dir_path)
        finally:
            with self._lock:
                self._active_threads -= 1

    def _scan_recursive(self, dir_path):
        dir_name = os.path.basename(dir_path) or dir_path
        node = FileNode(dir_name, dir_path, is_dir=True)

        try:
            entries = bulk_readdir(dir_path)
        except (PermissionError, OSError) as e:
            node.error = str(e)
            return node

        for name, is_dir, alloc_size in entries:
            if self._cancelled:
                return node
            if name in SKIP_DIRS:
                continue
            full_path = os.path.join(dir_path, name)
            if full_path in SKIP_PATHS:
                continue
            if is_dir:
                child = self._scan_recursive(full_path)
                node.add_child_fast(child)
            else:
                child = FileNode(name, full_path, own_size=alloc_size)
                node.add_child_fast(child)
                self._increment_counters(1, alloc_size)

        return node

    def _increment_counters(self, file_count, size_bytes):
        with self._lock:
            self._files_scanned += file_count
            self._total_size += size_bytes

    def get_snapshot(self):
        with self._lock:
            return (
                self._files_scanned,
                self._total_size,
                self._disk_used,
                self._active_threads,
                self._total_tasks,
                self._completed_tasks,
            )
