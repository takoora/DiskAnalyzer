import subprocess


def show_in_finder(path):
    """Reveal a file or folder in macOS Finder."""
    subprocess.Popen(["open", "-R", path])
