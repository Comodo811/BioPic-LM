"""Measurement and scale-bar model objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import hypot
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

    def length_pixels(self) -> float:
        """Return line/polyline length in pixels."""
        if len(self.points) < 2:
            return 0.0
        return sum(
            hypot(b.x - a.x, b.y - a.y)
            for a, b in zip(self.points[:-1], self.points[1:], strict=True)
        )

    def length_physical(self) -> float:
        """Return line/polyline length in physical units."""
        return self.length_pixels() * self.calibration.unit_per_pixel

    def area_pixels(self) -> float:
        """Return area in square pixels for polygon-like measurements."""
        if self.kind is MeasurementKind.RECTANGLE and len(self.points) >= 2:
            a, b = self.points[0], self.points[1]
            return abs((b.x - a.x) * (b.y - a.y))
        if self.kind is not MeasurementKind.POLYGON or len(self.points) < 3:
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the measurement."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "points": [point.to_dict() for point in self.points],
            "image_node_id": self.image_node_id,
            "calibration": self.calibration.to_dict(),
            "label": self.label,
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
        )


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
