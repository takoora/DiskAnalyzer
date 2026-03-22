from PySide6.QtGui import QColor

# Vibrant, high-saturation colors for treemap visibility on dark background
EXTENSION_GROUPS = {
    "images": {
        "extensions": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico", ".heic", ".raw"},
        "color": QColor(41, 182, 246),       # Light Blue 400
    },
    "video": {
        "extensions": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"},
        "color": QColor(239, 83, 80),         # Red 400
    },
    "audio": {
        "extensions": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".aiff"},
        "color": QColor(255, 167, 38),        # Orange 400
    },
    "documents": {
        "extensions": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".txt", ".rtf", ".csv"},
        "color": QColor(102, 187, 106),       # Green 400
    },
    "archives": {
        "extensions": {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".dmg", ".iso", ".pkg"},
        "color": QColor(171, 71, 188),        # Purple 400
    },
    "code": {
        "extensions": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".swift", ".kt", ".cs", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".sh", ".sql"},
        "color": QColor(38, 198, 218),        # Cyan 400
    },
    "executables": {
        "extensions": {".app", ".exe", ".bin", ".dylib", ".so", ".dll", ".framework"},
        "color": QColor(141, 110, 99),        # Brown 300
    },
    "databases": {
        "extensions": {".db", ".sqlite", ".sqlite3", ".realm"},
        "color": QColor(255, 213, 79),        # Yellow 400
    },
    "system": {
        "extensions": {".plist", ".log", ".cache", ".tmp", ".lock"},
        "color": QColor(144, 164, 174),       # Blue Grey 300
    },
}

_EXT_TO_COLOR = {}
for group in EXTENSION_GROUPS.values():
    for ext in group["extensions"]:
        _EXT_TO_COLOR[ext] = group["color"]

# Wide variety hash palette — no greys, all saturated
_HASH_PALETTE = [
    QColor(92, 107, 192),     # Indigo 400
    QColor(77, 182, 172),     # Teal 300
    QColor(255, 112, 67),     # Deep Orange 400
    QColor(240, 98, 146),     # Pink 300
    QColor(149, 117, 205),    # Deep Purple 300
    QColor(79, 195, 247),     # Light Blue 300
    QColor(174, 213, 129),    # Light Green 300
    QColor(255, 183, 77),     # Orange 300
    QColor(77, 208, 225),     # Cyan 300
    QColor(220, 231, 117),    # Lime 300
    QColor(255, 138, 101),    # Deep Orange 300
    QColor(129, 199, 132),    # Green 300
    QColor(100, 181, 246),    # Blue 300
    QColor(186, 104, 200),    # Purple 300
    QColor(255, 241, 118),    # Yellow 300
    QColor(128, 222, 234),    # Cyan 200
]

DIRECTORY_COLOR = QColor(55, 71, 79)   # BlueGrey 800
UNKNOWN_COLOR = QColor(144, 164, 174)  # BlueGrey 300 (not grey — has color)


def color_for_extension(ext):
    if not ext:
        return UNKNOWN_COLOR
    ext = ext.lower()
    cached = _EXT_TO_COLOR.get(ext)
    if cached:
        return cached
    idx = hash(ext) % len(_HASH_PALETTE)
    color = _HASH_PALETTE[idx]
    _EXT_TO_COLOR[ext] = color
    return color


def darker_color(color, factor=150):
    return color.darker(factor)
