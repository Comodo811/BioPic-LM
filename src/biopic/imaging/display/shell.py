"""GIMP-style display-shell state for a canvas view."""

from __future__ import annotations

from dataclasses import dataclass, field

DisplayRect = tuple[int, int, int, int]


@dataclass(slots=True)
class DisplayShellState:
    """Separate image display state from document pixels and Qt items."""

    image_width: int = 1
    image_height: int = 1
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    render_scale: int = 1
    rotation_degrees: float = 0.0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    generation: int = 0
    invalid_regions: list[DisplayRect] = field(default_factory=list)

    def set_image_size(self, width: int, height: int) -> None:
        """Set displayed image dimensions and invalidate the whole shell."""
        width = max(1, int(width))
        height = max(1, int(height))
        if (width, height) == (self.image_width, self.image_height):
            return
        self.image_width = width
        self.image_height = height
        self.invalidate_full()

    def set_offsets(self, offset_x: float, offset_y: float) -> None:
        """Store canvas pan/preview offsets without touching pixel cache state."""
        self.offset_x = float(offset_x)
        self.offset_y = float(offset_y)

    def set_scale(self, scale_x: float, scale_y: float | None = None) -> None:
        """Store view scale and invalidate render-cache state if it changes."""
        scale_x = max(0.001, float(scale_x))
        scale_y = scale_x if scale_y is None else max(0.001, float(scale_y))
        render_scale = self._render_scale_for(scale_x, scale_y)
        if (
            abs(self.scale_x - scale_x) < 1e-9
            and abs(self.scale_y - scale_y) < 1e-9
            and self.render_scale == render_scale
        ):
            return
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.render_scale = render_scale
        self.invalidate_full()

    def zoom_by(self, factor: float) -> None:
        """Scale the display shell uniformly."""
        self.set_scale(self.scale_x * factor, self.scale_y * factor)

    def actual_size(self) -> None:
        """Set display scale to one image pixel per screen pixel."""
        self.set_scale(1.0, 1.0)

    def invalidate_full(self) -> None:
        """Invalidate the whole image-space render region."""
        self.generation += 1
        self.invalid_regions = [self.image_rect()]

    def invalidate_area(self, rect: DisplayRect) -> DisplayRect | None:
        """Invalidate a clipped image-space region."""
        clipped = self.clip_rect(rect)
        if clipped is None:
            return None
        self.invalid_regions.append(clipped)
        return clipped

    def take_invalid_regions(self) -> list[DisplayRect]:
        """Return and clear queued invalid regions."""
        regions = list(self.invalid_regions)
        self.invalid_regions.clear()
        return regions

    def image_rect(self) -> DisplayRect:
        """Return the full image rect in image coordinates."""
        return (0, 0, self.image_width, self.image_height)

    def clip_rect(self, rect: DisplayRect) -> DisplayRect | None:
        """Clip an image-space rect to the displayed image bounds."""
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return None
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.image_width, int(x + width))
        y1 = min(self.image_height, int(y + height))
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def _render_scale_for(scale_x: float, scale_y: float) -> int:
        """Choose a small integer render scale like GIMP's display shell cache."""
        scale = max(scale_x, scale_y)
        if scale <= 1.0:
            return 1
        if scale <= 2.0:
            return 2
        if scale <= 4.0:
            return 4
        return 8
