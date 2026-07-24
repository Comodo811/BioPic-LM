"""Small rectangle-region helpers for localized image invalidation."""

from __future__ import annotations

from dataclasses import dataclass, field

Rect = tuple[int, int, int, int]


@dataclass(slots=True)
class DirtyRegion:
    """A compact mutable collection of dirty rectangles."""

    _rects: list[Rect] = field(default_factory=list)

    def add(self, rect: Rect | None) -> None:
        """Add a non-empty rectangle, merging overlapping entries."""
        if rect is None:
            return
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return
        pending = (x, y, width, height)
        merged: list[Rect] = []
        for existing in self._rects:
            if _rects_overlap_or_touch(existing, pending) and _should_merge(existing, pending):
                pending = union_rect(existing, pending)
            else:
                merged.append(existing)
        merged.append(pending)
        self._rects = merged

    def rectangles(self) -> list[Rect]:
        """Return the current dirty rectangles."""
        return list(self._rects)

    def bounds(self) -> Rect | None:
        """Return the total dirty bounds."""
        return union_rects(self._rects)

    def clear(self) -> None:
        """Clear all dirty rectangles."""
        self._rects.clear()


def union_rects(rects: list[Rect]) -> Rect | None:
    """Return the bounding rectangle for a list of rectangles."""
    if not rects:
        return None
    x_min = min(rect[0] for rect in rects)
    y_min = min(rect[1] for rect in rects)
    x_max = max(rect[0] + rect[2] for rect in rects)
    y_max = max(rect[1] + rect[3] for rect in rects)
    return (x_min, y_min, x_max - x_min, y_max - y_min)


def align_rect_outward(rect: Rect, grid_width: int, grid_height: int) -> Rect:
    """Align a dirty rectangle outward to a coarse update grid."""
    x, y, width, height = rect
    grid_width = max(1, grid_width)
    grid_height = max(1, grid_height)
    x0 = (x // grid_width) * grid_width
    y0 = (y // grid_height) * grid_height
    x1 = _ceil_div(x + width, grid_width) * grid_width
    y1 = _ceil_div(y + height, grid_height) * grid_height
    return (x0, y0, x1 - x0, y1 - y0)


def union_rect(first: Rect, second: Rect) -> Rect:
    """Return the bounding rectangle of two rectangles."""
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    x0 = min(ax, bx)
    y0 = min(ay, by)
    x1 = max(ax + aw, bx + bw)
    y1 = max(ay + ah, by + bh)
    return (x0, y0, x1 - x0, y1 - y0)


def _rects_overlap_or_touch(first: Rect, second: Rect) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax <= bx + bw and bx <= ax + aw and ay <= by + bh and by <= ay + ah


def _should_merge(first: Rect, second: Rect) -> bool:
    union = union_rect(first, second)
    union_area = union[2] * union[3]
    source_area = first[2] * first[3] + second[2] * second[3]
    return union_area <= max(source_area * 2, source_area + 1024)


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)
