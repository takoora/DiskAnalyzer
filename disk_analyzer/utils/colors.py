from PySide6.QtGui import QColor


# ---------------------------------------------------------------------------
# WCAG 2.0 accessibility helpers
# ---------------------------------------------------------------------------

def _relative_luminance(r, g, b):
    """WCAG 2.0 relative luminance."""
    def adjust(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)


def text_color_for_bg(bg_color):
    """Return white or black QColor for readable text on the given background."""
    lum = _relative_luminance(bg_color.red(), bg_color.green(), bg_color.blue())
    if 1.05 / (lum + 0.05) >= 4.5:
        return QColor(255, 255, 255)
    return QColor(0, 0, 0)


def _ensure_accessible(color):
    """Darken a color if it doesn't have sufficient contrast with white text."""
    r, g, b = color.red(), color.green(), color.blue()
    lum = _relative_luminance(r, g, b)
    if 1.05 / (lum + 0.05) >= 4.5:
        return color
    c = QColor(color)
    for _ in range(10):
        c = c.darker(115)
        lum = _relative_luminance(c.red(), c.green(), c.blue())
        if 1.05 / (lum + 0.05) >= 4.5:
            return c
    return c


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

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

# Build extension-to-color map, ensuring all colors are accessible
_EXT_TO_COLOR = {}
for _group in EXTENSION_GROUPS.values():
    _acc_color = _ensure_accessible(_group["color"])
    for _ext in _group["extensions"]:
        _EXT_TO_COLOR[_ext] = _acc_color

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
UNKNOWN_COLOR = _ensure_accessible(QColor(144, 164, 174))  # BlueGrey 300

# Track used color RGB tuples to avoid duplicates
_USED_COLORS = set()
for _c in _EXT_TO_COLOR.values():
    _USED_COLORS.add((_c.red(), _c.green(), _c.blue()))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def color_for_extension(ext):
    if not ext:
        return UNKNOWN_COLOR
    ext = ext.lower()
    cached = _EXT_TO_COLOR.get(ext)
    if cached:
        return cached

    # Try palette slots starting from hash, skip if color already used
    start = hash(ext) % len(_HASH_PALETTE)
    for offset in range(len(_HASH_PALETTE)):
        idx = (start + offset) % len(_HASH_PALETTE)
        color = _ensure_accessible(_HASH_PALETTE[idx])
        key = (color.red(), color.green(), color.blue())
        if key not in _USED_COLORS:
            _USED_COLORS.add(key)
            _EXT_TO_COLOR[ext] = color
            return color

    # All palette colors used — generate a unique variant by hue-shifting
    base = _HASH_PALETTE[start]
    h, s, l, _ = base.getHslF()
    for i in range(1, 50):
        shifted = QColor.fromHslF((h + i * 0.037) % 1.0, max(s, 0.5), max(l * 0.7, 0.25))
        shifted = _ensure_accessible(shifted)
        key = (shifted.red(), shifted.green(), shifted.blue())
        if key not in _USED_COLORS:
            _USED_COLORS.add(key)
            _EXT_TO_COLOR[ext] = shifted
            return shifted

    # Fallback — shouldn't happen
    color = _ensure_accessible(_HASH_PALETTE[start])
    _EXT_TO_COLOR[ext] = color
    return color


def darker_color(color, factor=150):
    return color.darker(factor)
