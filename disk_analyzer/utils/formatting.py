def format_size(size_bytes):
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def format_count(n):
    return f"{n:,}"


def format_percent(value, total):
    if total == 0:
        return "0.0%"
    pct = min((value / total) * 100, 100.0)
    return f"{pct:.1f}%"


def calc_percent(value, total):
    if total == 0:
        return 0.0
    return min((value / total) * 100, 100.0)
