from PySide6.QtWidgets import QMessageBox, QApplication

from disk_analyzer.utils.formatting import format_size
from disk_analyzer.utils.finder import move_to_trash, permanent_delete
from disk_analyzer.views.loading_overlay import LoadingOverlay


def confirm_and_delete(parent_widget, name, path, size, permanent=False):
    """Show confirmation dialog, then delete with a loading overlay.
    Returns True if the file was successfully deleted/trashed."""
    if permanent:
        msg = (f"PERMANENTLY delete '{name}' ({format_size(size)})?\n\n"
               f"This cannot be undone!")
        reply = QMessageBox.warning(parent_widget, "Confirm Permanent Delete", msg,
                                    QMessageBox.Yes | QMessageBox.No)
    else:
        msg = f"Move '{name}' ({format_size(size)}) to Trash?"
        reply = QMessageBox.question(parent_widget, "Confirm Delete", msg,
                                     QMessageBox.Yes | QMessageBox.No)

    if reply != QMessageBox.Yes:
        return False

    action = "Deleting" if permanent else "Moving to Trash"
    overlay = LoadingOverlay()
    overlay.show_over(parent_widget, f"{action}: {name}...")

    if permanent:
        success = permanent_delete(path)
    else:
        success = move_to_trash(path)

    overlay.hide_overlay()
    return success


def bulk_delete_with_overlay(parent_widget, items, keep_fn=None):
    """Delete multiple items with a progress overlay.
    items: list of objects with .name, .path, .own_size attributes.
    keep_fn: optional callable(item) -> bool, if True skip that item.
    Returns list of successfully deleted items."""
    overlay = LoadingOverlay()
    overlay.show_over(parent_widget, "Deleting files...")

    deleted = []
    total = len(items)
    for i, item in enumerate(items):
        if keep_fn and keep_fn(item):
            continue
        overlay.set_text(f"Moving to Trash ({i + 1:,}/{total:,}): {item.name}")
        QApplication.processEvents()
        if move_to_trash(item.path):
            deleted.append(item)

    overlay.hide_overlay()
    return deleted
