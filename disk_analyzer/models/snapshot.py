import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


SNAPSHOT_DIR = os.path.join(os.path.expanduser("~"), ".diskanalyzer", "snapshots")
SNAPSHOT_VERSION = 1


@dataclass
class ComparisonResult:
    new_files: list = field(default_factory=list)        # [(path, size), ...]
    deleted_files: list = field(default_factory=list)     # [(path, size), ...]
    grown_files: list = field(default_factory=list)       # [(path, old_size, new_size), ...]
    shrunk_files: list = field(default_factory=list)      # [(path, old_size, new_size), ...]
    total_old_size: int = 0
    total_new_size: int = 0
    size_delta: int = 0


def _node_to_dict(node):
    """Recursively convert a FileNode tree into a serializable dict."""
    d = {
        "name": node.name,
        "path": node.path,
        "size": node.cumulative_size if node.is_dir else node.own_size,
        "is_dir": node.is_dir,
    }
    if node.is_dir:
        d["children"] = [_node_to_dict(child) for child in node.children]
    else:
        d["children"] = []
    return d


def _flatten_snapshot(tree_data, result=None):
    """Flatten tree data into a dict of {path: size} for all leaf files."""
    if result is None:
        result = {}
    if not tree_data.get("is_dir", False):
        result[tree_data["path"]] = tree_data["size"]
    else:
        for child in tree_data.get("children", []):
            _flatten_snapshot(child, result)
    return result


def save_snapshot(root_node, root_path):
    """Save a scan result as a JSON snapshot. Returns the filepath."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    folder_name = os.path.basename(os.path.normpath(root_path)) or "root"
    # Sanitize folder name for use in filename
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in folder_name)
    filename = f"{safe_name}_{timestamp}.json"
    filepath = os.path.join(SNAPSHOT_DIR, filename)

    snapshot = {
        "version": SNAPSHOT_VERSION,
        "timestamp": now.isoformat(),
        "root_path": root_path,
        "scan_date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "tree": _node_to_dict(root_node),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)

    return filepath


def load_snapshot(filepath):
    """Load a snapshot from a JSON file. Returns the raw dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_snapshots():
    """List all saved snapshots.

    Returns a list of (filepath, root_path, timestamp, total_size) tuples,
    sorted by timestamp descending (newest first).
    """
    if not os.path.isdir(SNAPSHOT_DIR):
        return []

    results = []
    for fname in os.listdir(SNAPSHOT_DIR):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(SNAPSHOT_DIR, fname)
        try:
            data = load_snapshot(filepath)
            root_path = data.get("root_path", "")
            timestamp = data.get("scan_date", "")
            total_size = data.get("tree", {}).get("size", 0)
            results.append((filepath, root_path, timestamp, total_size))
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def compare_snapshots(old_snapshot, new_snapshot):
    """Compare two snapshot dicts and return a ComparisonResult.

    Parameters are raw snapshot dicts as returned by load_snapshot().
    """
    old_files = _flatten_snapshot(old_snapshot["tree"])
    new_files = _flatten_snapshot(new_snapshot["tree"])

    old_paths = set(old_files.keys())
    new_paths = set(new_files.keys())

    new_only = new_paths - old_paths
    deleted_only = old_paths - new_paths
    common = old_paths & new_paths

    result = ComparisonResult()

    result.new_files = [(p, new_files[p]) for p in new_only]
    result.new_files.sort(key=lambda x: x[1], reverse=True)

    result.deleted_files = [(p, old_files[p]) for p in deleted_only]
    result.deleted_files.sort(key=lambda x: x[1], reverse=True)

    for p in common:
        old_size = old_files[p]
        new_size = new_files[p]
        if new_size > old_size:
            result.grown_files.append((p, old_size, new_size))
        elif new_size < old_size:
            result.shrunk_files.append((p, old_size, new_size))

    result.grown_files.sort(key=lambda x: x[2] - x[1], reverse=True)
    result.shrunk_files.sort(key=lambda x: x[1] - x[2], reverse=True)

    result.total_old_size = old_snapshot["tree"].get("size", 0)
    result.total_new_size = new_snapshot["tree"].get("size", 0)
    result.size_delta = result.total_new_size - result.total_old_size

    return result
