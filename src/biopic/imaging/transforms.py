"""Clean-room transform primitives for interactive image-editing tools.

Matrix convention: column vectors in image coordinates. Matrix composition
``A @ B`` means "apply B first, then A".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import atan2, ceil, cos, floor, isfinite, pi, sin


class TransformTargetType(StrEnum):
    """Targets supported by transform tools."""

    LAYER = "layer"
    SELECTION = "selection"
    PATH = "path"
    IMAGE = "image"


class TransformDirection(StrEnum):
    """Semantic transform direction."""

    FORWARD = "forward"
    BACKWARD = "backward"


class TransformClipMode(StrEnum):
    """Result-boundary policy for a committed transform."""

    ADJUST = "adjust"
    CLIP = "clip"
    CROP_TO_RESULT = "crop_to_result"
    CROP_WITH_ASPECT = "crop_with_aspect"


class InterpolationMode(StrEnum):
    """Raster interpolation mode."""

    NONE = "none"
    LINEAR = "linear"
    CUBIC = "cubic"
    NO_HALO = "no_halo"
    LO_HALO = "lo_halo"


class TransformInteractionState(StrEnum):
    """Interactive transform state-machine states."""

    INACTIVE = "inactive"
    HOVERING = "hovering"
    DRAGGING = "dragging"
    AWAITING_COMMIT = "awaiting_commit"
    COMMITTING = "committing"


class TransformPreviewMode(StrEnum):
    """Non-destructive transform preview quality."""

    OUTLINE_ONLY = "outline_only"
    LOW_RESOLUTION = "low_resolution"
    FULL_QUALITY = "full_quality"


class TransformError(StrEnum):
    """Validation failure codes."""

    NONE = "none"
    MISSING_TARGET = "missing_target"
    LOCKED_TARGET = "locked_target"
    HIDDEN_TARGET = "hidden_target"
    INVALID_MATRIX = "invalid_matrix"
    SINGULAR_MATRIX = "singular_matrix"
    UNSAFE_OUTPUT = "unsafe_output"


@dataclass(frozen=True, slots=True)
class Vec2:
    """Double-precision 2D point or vector."""

    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class RectD:
    """Double-precision rectangle."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Vec2:
        return Vec2(self.x + self.width / 2.0, self.y + self.height / 2.0)

    def corners(self) -> tuple[Vec2, Vec2, Vec2, Vec2]:
        return (
            Vec2(self.x, self.y),
            Vec2(self.right, self.y),
            Vec2(self.right, self.bottom),
            Vec2(self.x, self.bottom),
        )

    def union(self, other: RectD) -> RectD:
        x0 = min(self.x, other.x)
        y0 = min(self.y, other.y)
        x1 = max(self.right, other.right)
        y1 = max(self.bottom, other.bottom)
        return RectD(x0, y0, x1 - x0, y1 - y0)

    def rounded_outward(self) -> tuple[int, int, int, int]:
        x0 = floor(self.x)
        y0 = floor(self.y)
        x1 = ceil(self.right)
        y1 = ceil(self.bottom)
        return (x0, y0, x1 - x0, y1 - y0)


@dataclass(frozen=True, slots=True)
class Mat3:
    """Affine 3x3 matrix using column-vector convention."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    @staticmethod
    def identity() -> Mat3:
        return Mat3()

    @staticmethod
    def translation(tx: float, ty: float) -> Mat3:
        return Mat3(tx=tx, ty=ty)

    @staticmethod
    def scale(sx: float, sy: float) -> Mat3:
        return Mat3(a=sx, d=sy)

    @staticmethod
    def rotation(radians: float) -> Mat3:
        cos_t = cos(radians)
        sin_t = sin(radians)
        return Mat3(a=cos_t, b=sin_t, c=-sin_t, d=cos_t)

    def __matmul__(self, other: Mat3) -> Mat3:
        return Mat3(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            tx=self.a * other.tx + self.c * other.ty + self.tx,
            ty=self.b * other.tx + self.d * other.ty + self.ty,
        )

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> Mat3:
        det = self.determinant()
        if abs(det) <= self.singularity_epsilon():
            raise ValueError("Cannot invert a near-singular transform matrix")
        inv_a = self.d / det
        inv_b = -self.b / det
        inv_c = -self.c / det
        inv_d = self.a / det
        return Mat3(
            a=inv_a,
            b=inv_b,
            c=inv_c,
            d=inv_d,
            tx=-(inv_a * self.tx + inv_c * self.ty),
            ty=-(inv_b * self.tx + inv_d * self.ty),
        )

    def singularity_epsilon(self) -> float:
        scale = max(abs(self.a), abs(self.b), abs(self.c), abs(self.d), 1.0)
        return 1e-12 * scale * scale

    def is_finite(self) -> bool:
        return all(
            isfinite(value)
            for value in (self.a, self.b, self.c, self.d, self.tx, self.ty)
        )

    def is_approximately_identity(self, epsilon: float = 1e-9) -> bool:
        return (
            abs(self.a - 1.0) <= epsilon
            and abs(self.b) <= epsilon
            and abs(self.c) <= epsilon
            and abs(self.d - 1.0) <= epsilon
            and abs(self.tx) <= epsilon
            and abs(self.ty) <= epsilon
        )

    def transform_point(self, point: Vec2) -> Vec2:
        return Vec2(
            self.a * point.x + self.c * point.y + self.tx,
            self.b * point.x + self.d * point.y + self.ty,
        )


@dataclass(slots=True)
class TransformValidationResult:
    """Result of validating transform targets and matrices."""

    valid: bool
    code: TransformError = TransformError.NONE
    message: str = ""
    offending_item: str | None = None


@dataclass(slots=True)
class TransformSession:
    """Persistent state for one interactive transform."""

    target_type: TransformTargetType = TransformTargetType.LAYER
    direction: TransformDirection = TransformDirection.FORWARD
    clip_mode: TransformClipMode = TransformClipMode.ADJUST
    interpolation: InterpolationMode = InterpolationMode.LINEAR
    original_matrix: Mat3 = field(default_factory=Mat3.identity)
    current_matrix: Mat3 = field(default_factory=Mat3.identity)
    original_bounds: RectD = field(default_factory=lambda: RectD(0.0, 0.0, 0.0, 0.0))
    transformed_bounds: RectD = field(default_factory=lambda: RectD(0.0, 0.0, 0.0, 0.0))
    pivot: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    drag_start_image: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    last_pointer_image: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    active_handle: str | None = None
    state: TransformInteractionState = TransformInteractionState.INACTIVE
    matrix_valid: bool = True
    preview_enabled: bool = True
    show_grid: bool = True
    constrain: bool = False
    from_center: bool = False
    source_generation: int = 0
    session_generation: int = 0

    def update_matrix(self, matrix: Mat3) -> TransformValidationResult:
        validation = validate_matrix(matrix)
        self.matrix_valid = validation.valid
        if not validation.valid:
            return validation
        self.current_matrix = matrix
        self.transformed_bounds = transform_bounds(self.original_bounds, matrix)
        self.session_generation += 1
        return validation


@dataclass(frozen=True, slots=True)
class ScaleParameters:
    """Canonical scale model: source rectangle plus destination rectangle."""

    source: RectD
    destination: RectD
    lock_aspect_ratio: bool = True
    scale_from_center: bool = False

    def matrix(self) -> Mat3:
        if abs(self.source.width) <= 1e-12 or abs(self.source.height) <= 1e-12:
            raise ValueError("Cannot scale an empty source rectangle")
        sx = self.destination.width / self.source.width
        sy = self.destination.height / self.source.height
        return (
            Mat3.translation(self.destination.x, self.destination.y)
            @ Mat3.scale(sx, sy)
            @ Mat3.translation(-self.source.x, -self.source.y)
        )


@dataclass(frozen=True, slots=True)
class RotationParameters:
    """Canonical rotation model."""

    angle_radians: float
    pivot: Vec2
    snap_angles: bool = False

    def matrix(self) -> Mat3:
        return (
            Mat3.translation(self.pivot.x, self.pivot.y)
            @ Mat3.rotation(self.angle_radians)
            @ Mat3.translation(-self.pivot.x, -self.pivot.y)
        )


@dataclass(frozen=True, slots=True)
class MoveSnapshot:
    """Constant-size metadata snapshot for moving an item."""

    item_id: str
    original_offset: Vec2


@dataclass(slots=True)
class MoveToolCore:
    """Core move interaction using total displacement from press point."""

    original_items: list[MoveSnapshot] = field(default_factory=list)
    drag_start_image: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    current_delta: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    active: bool = False

    def begin_move(self, items: list[MoveSnapshot], pointer_image: Vec2) -> None:
        self.original_items = list(items)
        self.drag_start_image = pointer_image
        self.current_delta = Vec2(0.0, 0.0)
        self.active = True

    def update_move(self, pointer_image: Vec2) -> dict[str, tuple[int, int]]:
        if not self.active:
            return {}
        self.current_delta = pointer_image - self.drag_start_image
        return {
            item.item_id: (
                int(round(item.original_offset.x + self.current_delta.x)),
                int(round(item.original_offset.y + self.current_delta.y)),
            )
            for item in self.original_items
        }

    def cancel_move(self) -> dict[str, tuple[int, int]]:
        self.active = False
        return {
            item.item_id: (
                int(round(item.original_offset.x)),
                int(round(item.original_offset.y)),
            )
            for item in self.original_items
        }


@dataclass(frozen=True, slots=True)
class OutputSafety:
    """Safety evaluation before allocating transformed output."""

    valid: bool
    estimated_bytes: int = 0
    requires_confirmation: bool = False
    message: str = ""


def validate_matrix(matrix: Mat3) -> TransformValidationResult:
    """Reject NaN, infinity and near-singular affine matrices."""
    if not matrix.is_finite():
        return TransformValidationResult(
            False, TransformError.INVALID_MATRIX, "The transform matrix contains NaN or infinity."
        )
    if abs(matrix.determinant()) <= matrix.singularity_epsilon():
        return TransformValidationResult(
            False, TransformError.SINGULAR_MATRIX, "The transform matrix is singular."
        )
    return TransformValidationResult(True)


def transform_bounds(bounds: RectD, matrix: Mat3) -> RectD:
    """Transform all four corners and return the axis-aligned bounds."""
    transformed = [matrix.transform_point(point) for point in bounds.corners()]
    x0 = min(point.x for point in transformed)
    y0 = min(point.y for point in transformed)
    x1 = max(point.x for point in transformed)
    y1 = max(point.y for point in transformed)
    return RectD(x0, y0, x1 - x0, y1 - y0)


def calculate_output_bounds(
    matrix: Mat3,
    input_bounds: tuple[int, int, int, int],
    clip_mode: TransformClipMode,
) -> tuple[int, int, int, int]:
    """Calculate deterministic integer output bounds for a committed transform."""
    rect = RectD(
        float(input_bounds[0]),
        float(input_bounds[1]),
        float(input_bounds[2]),
        float(input_bounds[3]),
    )
    if clip_mode is TransformClipMode.CLIP:
        return input_bounds
    return transform_bounds(rect, matrix).rounded_outward()


def checked_pixel_count(
    width: int,
    height: int,
    bytes_per_pixel: int,
    *,
    max_dimension: int = 1_000_000,
    max_bytes: int = 8 * 1024 * 1024 * 1024,
) -> OutputSafety:
    """Validate transformed output dimensions before allocation."""
    if width <= 0 or height <= 0 or bytes_per_pixel <= 0:
        return OutputSafety(False, message="Transform output dimensions must be positive.")
    if width > max_dimension or height > max_dimension:
        return OutputSafety(False, message=f"Transform output {width} x {height} is too large.")
    estimated = width * height * bytes_per_pixel
    if estimated > max_bytes:
        return OutputSafety(
            False,
            estimated_bytes=estimated,
            message=f"Transform output would require about {estimated} bytes.",
        )
    return OutputSafety(
        True,
        estimated_bytes=estimated,
        requires_confirmation=estimated > max_bytes // 2,
        message=f"Transform output will require about {estimated} bytes.",
    )


def rotation_drag_angle(start: Vec2, current: Vec2, pivot: Vec2) -> float:
    """Return signed rotation delta using atan2(cross, dot)."""
    v0 = start - pivot
    v1 = current - pivot
    if v0.x * v0.x + v0.y * v0.y < 1e-12 or v1.x * v1.x + v1.y * v1.y < 1e-12:
        return 0.0
    cross = v0.x * v1.y - v0.y * v1.x
    dot = v0.x * v1.x + v0.y * v1.y
    return atan2(cross, dot)


def snap_angle(angle: float, increment: float = pi / 12.0) -> float:
    """Snap an angle to the nearest increment."""
    if increment <= 0:
        return angle
    return increment * round(angle / increment)
