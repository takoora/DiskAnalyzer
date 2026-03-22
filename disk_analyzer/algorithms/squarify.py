from PySide6.QtCore import QRectF


def squarify(items, rect, min_area=9):
    """Compute squarified treemap layout.

    Args:
        items: list of (node, size) tuples, will be sorted by size descending.
        rect: QRectF bounding rectangle.
        min_area: minimum pixel area to include a rectangle.

    Returns:
        list of (node, QRectF) tuples.
    """
    if not items or rect.width() <= 0 or rect.height() <= 0:
        return []

    items = sorted(items, key=lambda x: x[1], reverse=True)
    total = sum(s for _, s in items)
    if total <= 0:
        return []

    area = rect.width() * rect.height()
    scaled = [(node, (size / total) * area) for node, size in items]
    scaled = [(node, s) for node, s in scaled if s >= min_area]

    if not scaled:
        return []

    result = []
    _squarify_recursive(scaled, rect, result)
    return result


def _squarify_recursive(items, rect, result):
    if not items:
        return

    if len(items) == 1:
        result.append((items[0][0], QRectF(rect)))
        return

    total_area = sum(s for _, s in items)
    w = min(rect.width(), rect.height())

    row = []
    row_area = 0
    remaining = list(items)

    row.append(remaining.pop(0))
    row_area = row[0][1]

    while remaining:
        candidate = remaining[0]
        new_row = row + [candidate]
        new_area = row_area + candidate[1]

        if _worst_ratio(row, row_area, w) >= _worst_ratio(new_row, new_area, w):
            row = new_row
            row_area = new_area
            remaining.pop(0)
        else:
            break

    layout_rect, leftover_rect = _layout_row(row, row_area, total_area, rect)

    x, y = layout_rect.x(), layout_rect.y()
    if layout_rect.width() <= layout_rect.height():
        h_per = layout_rect.height()
        for node, size in row:
            item_h = (size / row_area) * h_per if row_area > 0 else 0
            result.append((node, QRectF(x, y, layout_rect.width(), item_h)))
            y += item_h
    else:
        w_per = layout_rect.width()
        for node, size in row:
            item_w = (size / row_area) * w_per if row_area > 0 else 0
            result.append((node, QRectF(x, y, item_w, layout_rect.height())))
            x += item_w

    if remaining and leftover_rect.width() > 0 and leftover_rect.height() > 0:
        _squarify_recursive(remaining, leftover_rect, result)


def _worst_ratio(row, row_area, w):
    if w == 0 or row_area == 0:
        return float("inf")
    s2 = row_area * row_area
    w2 = w * w
    worst = 0
    for _, size in row:
        if size == 0:
            continue
        r = max((w2 * size) / s2, s2 / (w2 * size))
        if r > worst:
            worst = r
    return worst


def _layout_row(row, row_area, total_area, rect):
    if total_area == 0:
        return rect, QRectF()

    fraction = row_area / total_area

    if rect.width() <= rect.height():
        row_h = rect.height() * fraction
        layout = QRectF(rect.x(), rect.y(), rect.width(), row_h)
        leftover = QRectF(rect.x(), rect.y() + row_h, rect.width(), rect.height() - row_h)
    else:
        row_w = rect.width() * fraction
        layout = QRectF(rect.x(), rect.y(), row_w, rect.height())
        leftover = QRectF(rect.x() + row_w, rect.y(), rect.width() - row_w, rect.height())

    return layout, leftover
