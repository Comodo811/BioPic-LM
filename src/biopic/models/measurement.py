"""Measurement and scale-bar model objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import cos, hypot, pi, sin
from typing import Any
from uuid import uuid4

from biopic.models.calibration import Calibration, normalize_unit


class MeasurementKind(StrEnum):
    """Supported measurement object types."""

    LINE = "line"
    POLYLINE = "polyline"
    ANGLE = "angle"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    POLYGON = "polygon"


class MeasurementLabelAlignment(StrEnum):
    """How measurement labels are oriented on the image."""

    ALIGNED = "aligned"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True, slots=True)
class Point:
    """Image-space point in pixels."""

    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        """Serialize the point."""
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Point:
        """Deserialize the point."""
        return cls(x=float(data["x"]), y=float(data["y"]))


@dataclass(slots=True)
class Measurement:
    """A vector measurement linked to calibration."""

    kind: MeasurementKind
    points: list[Point]
    image_node_id: str
    calibration: Calibration
    id: str = field(default_factory=lambda: str(uuid4()))
    label: str = ""
    display_unit: str = "\u00b5m"
    area_display_unit: str = "\u00b5m\u00b2"
    label_alignment: MeasurementLabelAlignment = MeasurementLabelAlignment.HORIZONTAL
    rotation: float = 0.0
    color: str = "#ffe36d"
    line_width: float = 2.0
    font_family: str = "Arial"
    font_size: float = 13.0
    bold: bool = False
    italic: bool = False
    show_side_lengths: bool = False
    show_label: bool = True
    label_offset: tuple[float, float] = (0.0, 0.0)
    value_offset: tuple[float, float] = (0.0, 0.0)
    decimal_places: int = 2

    def length_pixels(self) -> float:
        """Return line/polyline length in pixels."""
        if self.kind is MeasurementKind.RECTANGLE:
            sides = self.rectangle_side_lengths_pixels()
            return 2.0 * (sides[0] + sides[1])
        if self.kind is MeasurementKind.ELLIPSE:
            major, minor = self.ellipse_axes_pixels()
            a = major / 2.0
            b = minor / 2.0
            return pi * (3.0 * (a + b) - ((3.0 * a + b) * (a + 3.0 * b)) ** 0.5)
        if len(self.points) < 2:
            return 0.0
        return sum(
            hypot(b.x - a.x, b.y - a.y)
            for a, b in zip(self.points[:-1], self.points[1:], strict=True)
        )

    def length_physical(self) -> float:
        """Return line/polyline length in physical units."""
        return self.length_pixels() * self.calibration.unit_per_pixel

    def length_display(self, unit: str | None = None) -> float:
        """Return length in requested display unit."""
        unit = normalize_length_unit(unit or self.display_unit)
        if unit == "px":
            return self.length_pixels()
        return convert_length_from_calibration_unit(
            self.length_physical(),
            self.calibration.unit,
            unit,
        )

    def area_pixels(self) -> float:
        """Return area in square pixels for polygon-like measurements."""
        if self.kind is MeasurementKind.RECTANGLE and len(self.points) >= 2:
            width, height = self.rectangle_side_lengths_pixels()
            return width * height
        if self.kind is MeasurementKind.ELLIPSE and len(self.points) >= 2:
            major, minor = self.ellipse_axes_pixels()
            return pi * (major / 2.0) * (minor / 2.0)
        if self.kind not in {MeasurementKind.POLYGON, MeasurementKind.POLYLINE} or len(self.points) < 3:
            return 0.0
        total = 0.0
        points = self.points + [self.points[0]]
        for a, b in zip(points[:-1], points[1:], strict=True):
            total += a.x * b.y - b.x * a.y
        return abs(total) / 2.0

    def area_physical(self) -> float:
        """Return area in squared physical units."""
        scale = self.calibration.unit_per_pixel
        return self.area_pixels() * scale * scale

    def area_display(self, unit: str | None = None) -> float:
        """Return area in requested display unit."""
        unit = normalize_area_unit(unit or self.area_display_unit)
        if unit == "px²":
            return self.area_pixels()
        return convert_area_from_calibration_unit(
            self.area_physical(),
            self.calibration.unit,
            unit,
        )

    def rectangle_side_lengths_pixels(self) -> tuple[float, float]:
        """Return width and height for a rectangle measurement."""
        if len(self.points) >= 4:
            p0, p1, p2 = self.points[0], self.points[1], self.points[2]
            return hypot(p1.x - p0.x, p1.y - p0.y), hypot(p2.x - p1.x, p2.y - p1.y)
        if len(self.points) >= 2:
            a, b = self.points[0], self.points[1]
            return abs(b.x - a.x), abs(b.y - a.y)
        return 0.0, 0.0

    def rectangle_side_lengths_display(self, unit: str | None = None) -> tuple[float, float]:
        """Return rectangle side lengths in requested display unit."""
        unit = normalize_length_unit(unit or self.display_unit)
        width, height = self.rectangle_side_lengths_pixels()
        if unit == "px":
            return width, height
        return (
            convert_length_from_calibration_unit(width * self.calibration.unit_per_pixel, self.calibration.unit, unit),
            convert_length_from_calibration_unit(height * self.calibration.unit_per_pixel, self.calibration.unit, unit),
        )

    def ellipse_axes_pixels(self) -> tuple[float, float]:
        """Return major and minor full-axis lengths for an ellipse."""
        if len(self.points) >= 3:
            center, major_point, minor_point = self.points[0], self.points[1], self.points[2]
            return (
                2.0 * hypot(major_point.x - center.x, major_point.y - center.y),
                2.0 * hypot(minor_point.x - center.x, minor_point.y - center.y),
            )
        if len(self.points) >= 2:
            a, b = self.points[0], self.points[1]
            return abs(b.x - a.x), abs(b.y - a.y)
        return 0.0, 0.0

    def display_text(self) -> str:
        """Return the label text shown next to the measurement geometry."""
        prefix = f"{self.label} - " if self.show_label and self.label else ""
        value = self.value_text()
        return f"{prefix}{value}"

    def value_text(self) -> str:
        """Return the numeric value text without the optional label prefix."""
        decimals = max(0, min(6, int(self.decimal_places)))
        if self.kind in {MeasurementKind.LINE, MeasurementKind.POLYLINE, MeasurementKind.ANGLE}:
            unit = normalize_length_unit(self.display_unit)
            return f"{self.length_display(unit):.{decimals}f} {unit}"
        unit = normalize_area_unit(self.area_display_unit)
        return f"{self.area_display(unit):.{decimals}f} {unit}"

    def label_text(self) -> str:
        """Return the optional label text."""
        return self.label if self.show_label else ""

    def line_angle_degrees(self) -> float:
        """Return line/label angle in degrees for aligned labels."""
        if len(self.points) < 2:
            return 0.0
        a, b = self.points[0], self.points[1]
        angle = float(np_degrees_atan2(b.y - a.y, b.x - a.x))
        if angle > 90.0 or angle < -90.0:
            angle += 180.0
        return angle

    def to_dict(self) -> dict[str, Any]:
        """Serialize the measurement."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "points": [point.to_dict() for point in self.points],
            "image_node_id": self.image_node_id,
            "calibration": self.calibration.to_dict(),
            "label": self.label,
            "display_unit": self.display_unit,
            "area_display_unit": self.area_display_unit,
            "label_alignment": self.label_alignment.value,
            "rotation": self.rotation,
            "color": self.color,
            "line_width": self.line_width,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "show_side_lengths": self.show_side_lengths,
            "show_label": self.show_label,
            "label_offset": list(self.label_offset),
            "value_offset": list(self.value_offset),
            "decimal_places": self.decimal_places,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Measurement:
        """Deserialize the measurement."""
        return cls(
            id=str(data["id"]),
            kind=MeasurementKind(data["kind"]),
            points=[Point.from_dict(item) for item in data.get("points", [])],
            image_node_id=str(data["image_node_id"]),
            calibration=Calibration.from_dict(data["calibration"]),
            label=str(data.get("label", "")),
            display_unit=normalize_length_unit(str(data.get("display_unit", data.get("unit", "\u00b5m")))),
            area_display_unit=normalize_area_unit(str(data.get("area_display_unit", "\u00b5m\u00b2"))),
            label_alignment=MeasurementLabelAlignment(str(data.get("label_alignment", "horizontal"))),
            rotation=float(data.get("rotation", 0.0)),
            color=str(data.get("color", "#ffe36d")),
            line_width=float(data.get("line_width", 2.0)),
            font_family=str(data.get("font_family", "Arial")),
            font_size=float(data.get("font_size", 13.0)),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            show_side_lengths=bool(data.get("show_side_lengths", False)),
            show_label=bool(data.get("show_label", True)),
            label_offset=_tuple2(data.get("label_offset", (0.0, 0.0))),
            value_offset=_tuple2(data.get("value_offset", (0.0, 0.0))),
            decimal_places=int(data.get("decimal_places", 2)),
        )


def _tuple2(value: object) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return 0.0, 0.0


def np_degrees_atan2(y: float, x: float) -> float:
    """Small local atan2 helper to avoid pulling numpy into model code."""
    from math import atan2, degrees

    return degrees(atan2(y, x))


def normalize_length_unit(unit: str) -> str:
    """Normalize supported length display units."""
    text = (
        normalize_unit(unit)
        .replace("Âµ", "\u00b5")
        .replace("Î¼", "\u00b5")
        .replace("μ", "\u00b5")
    )
    if text in {"um", "\u00b5m"}:
        return "\u00b5m"
    if text in {"px", "mm"}:
        return text
    return "px" if text.startswith("px") else "\u00b5m"


def normalize_area_unit(unit: str) -> str:
    """Normalize supported area display units."""
    text = (
        normalize_unit(unit)
        .replace("Âµ", "\u00b5")
        .replace("Î¼", "\u00b5")
        .replace("μ", "\u00b5")
        .replace("^2", "\u00b2")
    )
    if text in {"px2", "px\u00b2"}:
        return "px\u00b2"
    if text in {"um2", "\u00b5m2", "\u00b5m\u00b2"}:
        return "\u00b5m\u00b2"
    if text in {"mm2", "mm\u00b2"}:
        return "mm\u00b2"
    return "\u00b5m\u00b2"


def convert_length_from_calibration_unit(value: float, calibration_unit: str, target_unit: str) -> float:
    """Convert a physical length from calibration unit to target unit."""
    source = normalize_length_unit(calibration_unit)
    target = normalize_length_unit(target_unit)
    if source == target:
        return value
    micrometers = value * (1000.0 if source == "mm" else 1.0)
    if target == "mm":
        return micrometers / 1000.0
    return micrometers


def convert_area_from_calibration_unit(value: float, calibration_unit: str, target_unit: str) -> float:
    """Convert a physical area from calibration unit squared to target unit squared."""
    source = normalize_length_unit(calibration_unit)
    target = normalize_area_unit(target_unit)
    micrometer_area = value * (1_000_000.0 if source == "mm" else 1.0)
    if target == "mm²":
        return micrometer_area / 1_000_000.0
    return micrometer_area


def rotated_rectangle_points(
    center: Point,
    width: float,
    height: float,
    angle_degrees: float,
) -> list[Point]:
    """Return four rectangle corner points for a rotated rectangle."""
    angle = angle_degrees * pi / 180.0
    ux, uy = cos(angle), sin(angle)
    vx, vy = -sin(angle), cos(angle)
    half_w = width / 2.0
    half_h = height / 2.0
    offsets = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
    return [
        Point(center.x + dx * ux + dy * vx, center.y + dx * uy + dy * vy)
        for dx, dy in offsets
    ]


@dataclass(slots=True)
class ScaleBar:
    """Vector-like scale bar linked to image calibration."""

    image_node_id: str
    physical_length: float
    unit: str
    calibration: Calibration
    orientation: str = "horizontal"
    width_px: float = 4.0
    location: str = "Lower Right"
    offset_x: float = 24.0
    offset_y: float = 24.0
    foreground: str = "#ffffff"
    background: str | None = "#00000080"
    display_length: bool = True
    font_family: str = "Arial"
    font_size: float = 12.0
    bold: bool = False
    italic: bool = False
    opacity: float = 1.0
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.unit = normalize_unit(self.unit)

    @property
    def pixel_length(self) -> float:
        """Return rendered length in source image pixels."""
        if normalize_unit(self.unit) != normalize_unit(self.calibration.unit):
            raise ValueError("unit conversion is not implemented for differing scale-bar units")
        return self.calibration.physical_to_pixels(self.physical_length)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scale bar."""
        return {
            "id": self.id,
            "image_node_id": self.image_node_id,
            "physical_length": self.physical_length,
            "unit": self.unit,
            "calibration": self.calibration.to_dict(),
            "orientation": self.orientation,
            "width_px": self.width_px,
            "location": self.location,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "foreground": self.foreground,
            "background": self.background,
            "display_length": self.display_length,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScaleBar:
        """Deserialize the scale bar."""
        return cls(
            id=str(data["id"]),
            image_node_id=str(data["image_node_id"]),
            physical_length=float(data["physical_length"]),
            unit=normalize_unit(str(data["unit"])),
            calibration=Calibration.from_dict(data["calibration"]),
            orientation=str(data.get("orientation", "horizontal")),
            width_px=float(data.get("width_px", 4.0)),
            location=str(data.get("location", "Lower Right")),
            offset_x=float(data.get("offset_x", 24.0)),
            offset_y=float(data.get("offset_y", 24.0)),
            foreground=str(data.get("foreground", "#ffffff")),
            background=data.get("background"),
            display_length=bool(data.get("display_length", True)),
            font_family=str(data.get("font_family", "Arial")),
            font_size=float(data.get("font_size", 12.0)),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            opacity=float(data.get("opacity", 1.0)),
        )


def scale_bar_origin(
    scale_bar: ScaleBar,
    image_width: float,
    image_height: float,
    bar_width: float,
    bar_height: float,
) -> tuple[float, float]:
    """Return the scale-bar origin in source image coordinates."""
    offset_x = float(scale_bar.offset_x)
    offset_y = float(scale_bar.offset_y)
    if scale_bar.location == "Upper Left":
        return offset_x, offset_y
    if scale_bar.location == "Upper Right":
        return image_width - bar_width - offset_x, offset_y
    if scale_bar.location == "Lower Left":
        return offset_x, image_height - bar_height - offset_y
    return image_width - bar_width - offset_x, image_height - bar_height - offset_y


def scale_bar_panel_geometry(
    scale_bar: ScaleBar,
    source_width: float,
    source_height: float,
    panel_rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Map saved source-image scale-bar geometry into a figure-board panel."""
    source_width = max(1.0, float(source_width))
    source_height = max(1.0, float(source_height))
    length = max(1.0, float(scale_bar.pixel_length))
    thickness = max(1.0, float(scale_bar.width_px))
    is_vertical = scale_bar.orientation == "vertical"
    source_bar_width = thickness if is_vertical else length
    source_bar_height = length if is_vertical else thickness
    source_x, source_y = scale_bar_origin(
        scale_bar,
        source_width,
        source_height,
        source_bar_width,
        source_bar_height,
    )
    panel_x, panel_y, panel_width, panel_height = panel_rect
    x = panel_x + (source_x / source_width) * panel_width
    y = panel_y + (source_y / source_height) * panel_height
    width = (source_bar_width / source_width) * panel_width
    height = (source_bar_height / source_height) * panel_height
    return x, y, max(1.0, width), max(1.0, height)
