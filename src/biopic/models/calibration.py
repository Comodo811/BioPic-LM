"""Calibration, permanent scale presets, and scale-bar calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Calibration:
    """Physical calibration for an image."""

    unit_per_pixel: float
    unit: str = "μm"
    pixel_aspect_ratio: float = 1.0
    source: str = "manual"

    @classmethod
    def from_known_distance(
        cls, distance_pixels: float, known_distance: float, unit: str = "μm"
    ) -> Calibration:
        """Create a calibration from a measured pixel line and known distance."""
        if distance_pixels <= 0:
            raise ValueError("distance_pixels must be greater than zero")
        if known_distance <= 0:
            raise ValueError("known_distance must be greater than zero")
        return cls(unit_per_pixel=known_distance / distance_pixels, unit=normalize_unit(unit))

    @property
    def pixels_per_unit(self) -> float:
        """Return pixels per physical unit."""
        return 1.0 / self.unit_per_pixel

    def physical_to_pixels(self, length: float) -> float:
        """Convert a physical length to pixels."""
        if length <= 0:
            raise ValueError("length must be greater than zero")
        return length / self.unit_per_pixel

    def to_dict(self) -> dict[str, Any]:
        """Serialize calibration."""
        return {
            "unit_per_pixel": self.unit_per_pixel,
            "unit": self.unit,
            "pixel_aspect_ratio": self.pixel_aspect_ratio,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Calibration:
        """Deserialize calibration."""
        return cls(
            unit_per_pixel=float(data["unit_per_pixel"]),
            unit=normalize_unit(str(data.get("unit", "μm"))),
            pixel_aspect_ratio=float(data.get("pixel_aspect_ratio", 1.0)),
            source=str(data.get("source", "manual")),
        )


@dataclass(frozen=True, slots=True)
class MagnificationScale:
    """A permanent scale row for a camera and microscope preset."""

    magnification: float
    distance_pixels: float
    known_distance: float
    unit: str = "μm"
    fluid: str = "Water"
    unit_per_pixel: float | None = None
    objective: str = ""
    imaging_method: str = ""

    def __post_init__(self) -> None:
        if self.magnification <= 0:
            raise ValueError("magnification must be greater than zero")
        if self.distance_pixels <= 0:
            raise ValueError("distance_pixels must be greater than zero")
        if self.known_distance <= 0:
            raise ValueError("known_distance must be greater than zero")
        if self.unit_per_pixel is None:
            object.__setattr__(self, "unit_per_pixel", self.known_distance / self.distance_pixels)
        object.__setattr__(self, "unit", normalize_unit(self.unit))

    @property
    def pixels_per_unit(self) -> float:
        """Return pixels per selected physical unit."""
        if self.unit_per_pixel is not None:
            return 1.0 / self.unit_per_pixel
        return self.distance_pixels / self.known_distance

    def to_calibration(self, source: str) -> Calibration:
        """Convert this row to a calibration."""
        unit_per_pixel = self.unit_per_pixel
        if unit_per_pixel is None:
            unit_per_pixel = self.known_distance / self.distance_pixels
        return Calibration(
            unit_per_pixel=float(unit_per_pixel),
            unit=self.unit,
            source=source,
        )

    def menu_label(self) -> str:
        """Return menu label such as `40x (Water)`."""
        value = int(self.magnification) if self.magnification.is_integer() else self.magnification
        return f"{value}x ({self.fluid})"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scale row."""
        return {
            "magnification": self.magnification,
            "fluid": self.fluid,
            "distance_pixels": self.distance_pixels,
            "known_distance": self.known_distance,
            "unit": self.unit,
            "pixels_per_unit": self.pixels_per_unit,
            "unit_per_pixel": self.unit_per_pixel,
            "objective": self.objective,
            "imaging_method": self.imaging_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MagnificationScale:
        """Deserialize the scale row."""
        return cls(
            magnification=parse_magnification(data["magnification"]),
            fluid=str(data.get("fluid", "Water")),
            distance_pixels=float(data["distance_pixels"]),
            known_distance=float(data["known_distance"]),
            unit=normalize_unit(str(data.get("unit", "μm"))),
            unit_per_pixel=float(data["unit_per_pixel"])
            if data.get("unit_per_pixel") is not None
            else None,
            objective=str(data.get("objective", "")),
            imaging_method=str(data.get("imaging_method", "")),
        )


@dataclass(slots=True)
class ScalePreset:
    """Permanent camera and microscope scale preset."""

    name: str
    camera_name: str = ""
    microscope_name: str = ""
    imaging_method: str = ""
    notes: str = ""
    scales: list[MagnificationScale] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the preset."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "camera_name": self.camera_name,
            "microscope_name": self.microscope_name,
            "imaging_method": self.imaging_method,
            "notes": self.notes,
            "scales": [scale.to_dict() for scale in self.scales],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScalePreset:
        """Deserialize the preset."""
        return cls(
            id=str(data["id"]),
            schema_version=int(data.get("schema_version", 1)),
            name=str(data["name"]),
            camera_name=str(data.get("camera_name", "")),
            microscope_name=str(data.get("microscope_name", "")),
            imaging_method=str(data.get("imaging_method", "")),
            notes=str(data.get("notes", "")),
            scales=[MagnificationScale.from_dict(item) for item in data.get("scales", [])],
        )


def parse_magnification(value: object) -> float:
    """Parse magnification values such as `10`, `10x`, `10 x`, or `10x`."""
    if isinstance(value, (int, float)):
        magnification = float(value)
    else:
        text = str(value).strip().lower().replace("×", "x")
        text = text.replace("×", "x")
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*x?", text)
        if match is None:
            raise ValueError(f"Invalid magnification: {value}")
        magnification = float(match.group(1))
    if magnification <= 0:
        raise ValueError("magnification must be greater than zero")
    return magnification


def normalize_unit(unit: str) -> str:
    """Normalize common unit spellings for display and storage."""
    text = unit.strip()
    if text in {"um", "µm"}:
        return "μm"
    return text
