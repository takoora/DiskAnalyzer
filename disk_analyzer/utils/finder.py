import os
import sys
import subprocess
import webbrowser
from urllib.parse import quote_plus

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# OS-appropriate label for "Show in Finder" / "Show in File Explorer"
FILE_MANAGER_LABEL = "Show in Finder" if IS_MAC else "Show in File Explorer"


def show_in_file_manager(path):
    """Reveal a file or folder in the native file manager."""
    if IS_MAC:
        subprocess.Popen(["open", "-R", path])
    elif IS_WIN:
        subprocess.Popen(["explorer", "/select,", path])
    else:
        # Linux: try xdg-open on the parent directory
        parent = os.path.dirname(path)
        subprocess.Popen(["xdg-open", parent])


# Keep old name as alias for compatibility
show_in_finder = show_in_file_manager


def move_to_trash(path):
    """Move a file or folder to Trash/Recycle Bin. Returns True on success."""
    if IS_MAC:
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "Finder" to delete POSIX file "{path}"'],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
    elif IS_WIN:
        try:
            from send2trash import send2trash
            send2trash(path)
            return True
        except Exception:
            return False
    else:
        try:
            from send2trash import send2trash
            send2trash(path)
            return True
        except Exception:
            return False


def permanent_delete(path):
    """Permanently delete a file or folder (bypasses Trash). Returns True on success."""
    try:
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True
    except OSError:
        return False


def google_search(filename):
    """Open a Google search for the given filename."""
    query = quote_plus(f'"{filename}"')
    webbrowser.open(f"https://www.google.com/search?q={query}")
