"""Clean-room painting engine primitives for long-stroke responsiveness."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from math import atan2, cos, fmod, hypot, sin
from threading import Condition
from uuid import uuid4

from biopic.imaging.regions import DirtyRegion, Rect, align_rect_outward
from biopic.native.stroke_backend import spacing_dabs


@dataclass(frozen=True, slots=True)
class PaintCoordinates:
    """Image-space pointer sample with dynamic stylus properties."""

    x: float
    y: float
    pressure: float = 1.0
    x_tilt: float = 0.0
    y_tilt: float = 0.0
    wheel: float = 0.0
    velocity: float = 0.0
    direction: float = 0.0
    timestamp: int = 0


class PaintState(StrEnum):
    """Stroke lifecycle state for a submitted paint sample."""

    INITIALIZE = "initialize"
    MOTION = "motion"
    FINISH = "finish"


class PaintWorkType(StrEnum):
    """Ordered paint work item kind."""

    INTERPOLATE = "interpolate"
    FINISH_BARRIER = "finish_barrier"
    CANCEL = "cancel"


class PaintApplicationMode(StrEnum):
    """How overlapping dabs combine within one stroke."""

    CONSTANT = "constant"
    INCREMENTAL = "incremental"


@dataclass(frozen=True, slots=True)
class BrushState:
    """Effective brush parameters used by spacing interpolation."""

    size: float
    aspect_ratio: float = 1.0
    angle_radians: float = 0.0
    hardness: float = 1.0
    opacity: float = 1.0
    force: float = 1.0
    spacing: float = 0.15
    dynamic_spacing: bool = False

    def spacing_pixels(self, *, minimum: float = 0.5) -> float:
        return max(minimum, self.size * max(0.01, self.spacing))


@dataclass(slots=True)
class StrokeState:
    """Persistent state for spacing continuity and affected bounds."""

    start: PaintCoordinates
    previous_input: PaintCoordinates
    previous_dab: PaintCoordinates
    current_input: PaintCoordinates
    normalized_distance: float = 0.0
    pixel_distance: float = 0.0
    affected_bounds: Rect | None = None
    has_painted: bool = False
    generation: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))

    def include(self, rect: Rect) -> None:
        if not self.has_painted:
            self.affected_bounds = rect
            self.has_painted = True
            return
        assert self.affected_bounds is not None
        x0 = min(self.affected_bounds[0], rect[0])
        y0 = min(self.affected_bounds[1], rect[1])
        x1 = max(self.affected_bounds[0] + self.affected_bounds[2], rect[0] + rect[2])
        y1 = max(self.affected_bounds[1] + self.affected_bounds[3], rect[1] + rect[3])
        self.affected_bounds = (x0, y0, x1 - x0, y1 - y0)


@dataclass(frozen=True, slots=True)
class PaintWorkItem:
    """One ordered item in the paint queue."""

    type: PaintWorkType
    stroke: str
    coordinates: PaintCoordinates
    sequence: int


@dataclass(slots=True)
class InterpolationLimits:
    """Safety limits for spacing-based dab generation."""

    minimum_spacing_pixels: float = 0.5
    maximum_dabs_per_segment: int = 4096
    maximum_dabs_per_stroke: int = 1_000_000


@dataclass(slots=True)
class SpacingAccumulator:
    """Residual distance continuity across pointer events."""

    distance_since_last_dab: float = 0.0
    total_stroke_distance: float = 0.0
    generated_dabs: int = 0


@dataclass(slots=True)
class DrawablePaintSession:
    """Accumulated paint-copy and display-update regions for one drawable."""

    drawable: str
    tile_width: int = 256
    tile_height: int = 256
    display_chunk_width: int = 32
    display_chunk_height: int = 32
    copy_region: DirtyRegion = field(default_factory=DirtyRegion)
    update_region: DirtyRegion = field(default_factory=DirtyRegion)
    nesting_count: int = 0
    active: bool = False

    def begin(self) -> None:
        self.nesting_count += 1
        self.active = True

    def mark_dirty(self, rect: Rect) -> None:
        self.copy_region.add(align_rect_outward(rect, self.tile_width, self.tile_height))
        self.update_region.add(
            align_rect_outward(rect, self.display_chunk_width, self.display_chunk_height)
        )

    def flush_regions(self) -> tuple[list[Rect], list[Rect]]:
        copy_rects = self.copy_region.rectangles()
        update_rects = self.update_region.rectangles()
        self.copy_region.clear()
        self.update_region.clear()
        return copy_rects, update_rects

    def end(self) -> None:
        self.nesting_count = max(0, self.nesting_count - 1)
        self.active = self.nesting_count > 0


@dataclass(slots=True)
class PaintMetrics:
    """Counters and timings collected by the paint engine."""

    pointer_events: int = 0
    coalesced_events: int = 0
    generated_dabs: int = 0
    copied_tile_regions: int = 0
    update_rectangles: int = 0
    maximum_queue_depth: int = 0


class StrokeInterpolator:
    """Spacing-based interpolation with residual continuity."""

    def __init__(
        self,
        brush: BrushState,
        limits: InterpolationLimits | None = None,
    ) -> None:
        self.brush = brush
        self.limits = limits or InterpolationLimits()
        self.accumulator = SpacingAccumulator()

    def interpolate_segment(
        self,
        start: PaintCoordinates,
        end: PaintCoordinates,
        emit: Callable[[PaintCoordinates], None],
    ) -> int:
        dx = end.x - start.x
        dy = end.y - start.y
        length = hypot(dx, dy)
        if length <= 1e-12:
            return 0
        spacing = self.brush.spacing_pixels(minimum=self.limits.minimum_spacing_pixels)
        distance_to_next = spacing - self.accumulator.distance_since_last_dab
        emitted = 0
        while distance_to_next <= length and emitted < self.limits.maximum_dabs_per_segment:
            if self.accumulator.generated_dabs >= self.limits.maximum_dabs_per_stroke:
                break
            t = distance_to_next / length
            emit(_interpolate_coordinates(start, end, t))
            emitted += 1
            self.accumulator.generated_dabs += 1
            distance_to_next += spacing
        self.accumulator.distance_since_last_dab = fmod(
            self.accumulator.distance_since_last_dab + length,
            spacing,
        )
        self.accumulator.total_stroke_distance += length
        return emitted


class GimpPaintCore:
    """GIMP-style stateful paint core for one interactive brush stroke.

    The UI submits float input samples. The paint core owns last/current coords,
    brush spacing remainder, and generated-dab accounting. It returns only the
    dab centers that should be rasterized for the current segment.
    """

    def __init__(self) -> None:
        self.stroke_id: str | None = None
        self.last_coords: PaintCoordinates | None = None
        self.current_coords: PaintCoordinates | None = None
        self.spacing_remainder = 0.0
        self.pixel_distance = 0.0
        self.generated_dabs = 0

    def begin(self, coords: PaintCoordinates | None = None) -> None:
        self.stroke_id = str(uuid4())
        self.last_coords = coords
        self.current_coords = coords
        self.spacing_remainder = 0.0
        self.pixel_distance = 0.0
        self.generated_dabs = 0

    def motion(self, coords: PaintCoordinates, radius: int) -> list[tuple[int, int]]:
        if self.stroke_id is None:
            self.begin()
        previous = self.current_coords
        self.current_coords = coords
        if previous is None:
            self.last_coords = coords
            self.generated_dabs += 1
            return [_rounded_coords(coords)]
        self.spacing_remainder, points = spacing_dabs(
            (previous.x, previous.y),
            (coords.x, coords.y),
            radius,
            self.spacing_remainder,
        )
        self.pixel_distance += hypot(coords.x - previous.x, coords.y - previous.y)
        self.last_coords = coords
        self.generated_dabs += len(points)
        return points

    def finish(self) -> None:
        self.stroke_id = None
        self.last_coords = None
        self.current_coords = None
        self.spacing_remainder = 0.0

    def reset(self) -> None:
        self.finish()
        self.pixel_distance = 0.0
        self.generated_dabs = 0


class PaintWorkQueue:
    """Ordered paint queue with safe motion coalescing and finish barriers."""

    def __init__(self, *, coalesce_after: int = 96) -> None:
        self._condition = Condition()
        self._queue: deque[PaintWorkItem] = deque()
        self.coalesce_after = max(1, coalesce_after)
        self.maximum_depth = 0
        self.coalesced_events = 0

    def push(self, item: PaintWorkItem) -> None:
        with self._condition:
            self._queue.append(item)
            self.maximum_depth = max(self.maximum_depth, len(self._queue))
            self._condition.notify()

    def push_motion(self, item: PaintWorkItem) -> None:
        with self._condition:
            if self._can_merge_with_tail(item):
                self._queue[-1] = item
                self.coalesced_events += 1
            else:
                self._queue.append(item)
            self.maximum_depth = max(self.maximum_depth, len(self._queue))
            self._condition.notify()

    def wait_and_pop(self) -> PaintWorkItem:
        with self._condition:
            while not self._queue:
                self._condition.wait()
            return self._queue.popleft()

    def pop_nowait(self) -> PaintWorkItem | None:
        with self._condition:
            if not self._queue:
                return None
            return self._queue.popleft()

    def depth(self) -> int:
        """Return the current number of queued work items."""
        with self._condition:
            return len(self._queue)

    def clear(self) -> None:
        """Drop all queued work items."""
        with self._condition:
            self._queue.clear()
            self._condition.notify_all()

    def insert_finish_barrier(self, stroke: str, sequence: int) -> None:
        self.push(
            PaintWorkItem(
                PaintWorkType.FINISH_BARRIER,
                stroke,
                PaintCoordinates(0.0, 0.0),
                sequence,
            )
        )

    def _can_merge_with_tail(self, item: PaintWorkItem) -> bool:
        if item.type is not PaintWorkType.INTERPOLATE or not self._queue:
            return False
        if len(self._queue) < self.coalesce_after:
            return False
        tail = self._queue[-1]
        return tail.type is PaintWorkType.INTERPOLATE and tail.stroke == item.stroke


def constrain_line_angle(
    start: PaintCoordinates,
    end: PaintCoordinates,
    increment_radians: float,
) -> PaintCoordinates:
    """Constrain a straight line endpoint to an angle increment."""
    dx = end.x - start.x
    dy = end.y - start.y
    radius = hypot(dx, dy)
    if radius <= 1e-12 or increment_radians <= 0:
        return end
    angle = increment_radians * round(atan2(dy, dx) / increment_radians)
    return PaintCoordinates(
        x=start.x + radius * cos(angle),
        y=start.y + radius * sin(angle),
        pressure=end.pressure,
        x_tilt=end.x_tilt,
        y_tilt=end.y_tilt,
        wheel=end.wheel,
        velocity=end.velocity,
        direction=angle,
        timestamp=end.timestamp,
    )


def _interpolate_coordinates(
    start: PaintCoordinates, end: PaintCoordinates, t: float
) -> PaintCoordinates:
    return PaintCoordinates(
        x=start.x + (end.x - start.x) * t,
        y=start.y + (end.y - start.y) * t,
        pressure=start.pressure + (end.pressure - start.pressure) * t,
        x_tilt=start.x_tilt + (end.x_tilt - start.x_tilt) * t,
        y_tilt=start.y_tilt + (end.y_tilt - start.y_tilt) * t,
        wheel=start.wheel + (end.wheel - start.wheel) * t,
        velocity=start.velocity + (end.velocity - start.velocity) * t,
        direction=start.direction + (end.direction - start.direction) * t,
        timestamp=int(round(start.timestamp + (end.timestamp - start.timestamp) * t)),
    )


def _rounded_coords(coords: PaintCoordinates) -> tuple[int, int]:
    return int(round(coords.x)), int(round(coords.y))
