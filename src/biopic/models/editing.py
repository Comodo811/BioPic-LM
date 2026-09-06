"""Non-destructive editing model objects."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

import numpy as np


class BlendMode(StrEnum):
    """Supported layer blend modes."""

    NORMAL = "normal"
    ADD = "add"
    MULTIPLY = "multiply"
    SCREEN = "screen"


class EditLayerType(StrEnum):
    """Editable document layer categories."""

    RASTER = "raster"
    RETOUCH = "retouch"
    ADJUSTMENT = "adjustment"
    ANNOTATION = "annotation"
    SCALE_BAR = "scale_bar"
    GROUP = "group"


class LayerContentKind(StrEnum):
    """How a layer obtains its pixels."""

    SOURCE = "source"
    RASTER = "raster"
    EMPTY = "empty"


class LayerLock(StrEnum):
    """Layer lock flags compatible with future granular locks."""

    ALL = "all"
    PIXELS = "pixels"
    POSITION = "position"
    ALPHA = "alpha"
    VISIBILITY = "visibility"


class MaskViewMode(StrEnum):
    """How a layer mask is currently presented/edited."""

    APPLY = "apply"
    EDIT = "edit"
    SHOW = "show"


class GroupCompositeMode(StrEnum):
    """How a group layer composites its children."""

    PASS_THROUGH = "pass_through"
    ISOLATED = "isolated"


def pixels_to_payload(pixels: np.ndarray | None) -> dict[str, Any] | None:
    """Serialize a numpy array into a JSON-safe payload."""
    if pixels is None:
        return None
    handle = io.BytesIO()
    np.save(handle, np.asarray(pixels), allow_pickle=False)
    return {"format": "npy-base64", "data": base64.b64encode(handle.getvalue()).decode("ascii")}


def payload_to_pixels(payload: dict[str, Any] | None) -> np.ndarray | None:
    """Deserialize a JSON-safe pixel payload."""
    if payload is None:
        return None
    if payload.get("format") != "npy-base64":
        raise ValueError("Unsupported raster payload format")
    data = base64.b64decode(str(payload["data"]).encode("ascii"))
    return np.load(io.BytesIO(data), allow_pickle=False)


@dataclass(slots=True)
class AdjustmentLayer:
    """A non-destructive, parameterized image adjustment layer."""

    name: str
    image_node_id: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    mask_node_id: str | None = None
    algorithm_version: int = 1
    color_space: str = "source"
    input_precision: str = "preserve"
    output_precision: str = "preserve"
    cache_key: str | None = None
    order: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        """Update the modified timestamp and invalidate cached render output."""
        self.modified_at = datetime.now(UTC).isoformat()
        self.cache_key = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the adjustment layer."""
        return {
            "id": self.id,
            "name": self.name,
            "image_node_id": self.image_node_id,
            "operation": self.operation,
            "parameters": self.parameters,
            "enabled": self.enabled,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode.value,
            "mask_node_id": self.mask_node_id,
            "algorithm_version": self.algorithm_version,
            "color_space": self.color_space,
            "input_precision": self.input_precision,
            "output_precision": self.output_precision,
            "cache_key": self.cache_key,
            "order": self.order,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdjustmentLayer:
        """Deserialize an adjustment layer."""
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            image_node_id=str(data["image_node_id"]),
            operation=str(data["operation"]),
            parameters=dict(data.get("parameters", {})),
            enabled=bool(data.get("enabled", True)),
            opacity=float(data.get("opacity", 1.0)),
            blend_mode=BlendMode(data.get("blend_mode", BlendMode.NORMAL.value)),
            mask_node_id=data.get("mask_node_id"),
            algorithm_version=int(data.get("algorithm_version", 1)),
            color_space=str(data.get("color_space", "source")),
            input_precision=str(data.get("input_precision", "preserve")),
            output_precision=str(data.get("output_precision", "preserve")),
            cache_key=data.get("cache_key"),
            order=int(data.get("order", 0)),
            created_at=str(data["created_at"]),
            modified_at=str(data["modified_at"]),
        )


@dataclass(slots=True)
class EditLayer:
    """An editable layer record backed by document data, not UI state."""

    name: str
    source_node_id: str | None = None
    layer_type: EditLayerType = EditLayerType.RASTER
    content_kind: LayerContentKind = LayerContentKind.EMPTY
    visible: bool = True
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    mask_node_id: str | None = None
    mask_content: dict[str, Any] | None = None
    mask_enabled: bool = True
    mask_edit_state: MaskViewMode = MaskViewMode.APPLY
    group_composite_mode: GroupCompositeMode = GroupCompositeMode.PASS_THROUGH
    lock_flags: set[LayerLock] = field(default_factory=set)
    order: int = 0
    parent_id: str | None = None
    offset_x: int = 0
    offset_y: int = 0
    image_item_id: str = field(default_factory=lambda: str(uuid4()))
    drawable_id: str = field(default_factory=lambda: str(uuid4()))
    tile_store_id: str = field(default_factory=lambda: str(uuid4()))
    graph_node_id: str = field(default_factory=lambda: str(uuid4()))
    generation: int = 0
    filter_operation: str | None = None
    filter_parameters: dict[str, Any] = field(default_factory=dict)
    content: dict[str, Any] | None = None
    alpha: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def locked(self) -> bool:
        """Return whether the layer is fully locked."""
        return LayerLock.ALL in self.lock_flags

    @locked.setter
    def locked(self, value: bool) -> None:
        if value:
            self.lock_flags.add(LayerLock.ALL)
        else:
            self.lock_flags.discard(LayerLock.ALL)

    def content_pixels(self) -> np.ndarray | None:
        """Return raster pixels stored on this layer."""
        return payload_to_pixels(self.content)

    def set_content_pixels(self, pixels: np.ndarray | None) -> None:
        """Replace raster pixels stored on this layer."""
        self.content = pixels_to_payload(pixels)
        if pixels is not None and self.content_kind is LayerContentKind.EMPTY:
            self.content_kind = LayerContentKind.RASTER
        self.bump_generation()

    def alpha_pixels(self) -> np.ndarray | None:
        """Return the layer alpha plane, if any."""
        return payload_to_pixels(self.alpha)

    def set_alpha_pixels(self, pixels: np.ndarray | None) -> None:
        """Replace the layer alpha plane."""
        self.alpha = pixels_to_payload(pixels)
        self.bump_generation()

    def mask_pixels(self) -> np.ndarray | None:
        """Return the independent grayscale layer mask drawable, if present."""
        return payload_to_pixels(self.mask_content)

    def set_mask_pixels(self, pixels: np.ndarray | None) -> None:
        """Replace the independent grayscale layer mask drawable."""
        self.mask_content = pixels_to_payload(pixels)
        self.bump_generation()

    def bump_generation(self) -> None:
        """Advance the layer generation after content or graph changes."""
        self.generation += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the layer."""
        return {
            "id": self.id,
            "name": self.name,
            "source_node_id": self.source_node_id,
            "layer_type": self.layer_type.value,
            "content_kind": self.content_kind.value,
            "visible": self.visible,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode.value,
            "mask_node_id": self.mask_node_id,
            "mask_content": self.mask_content,
            "mask_enabled": self.mask_enabled,
            "mask_edit_state": self.mask_edit_state.value,
            "group_composite_mode": self.group_composite_mode.value,
            "locked": self.locked,
            "lock_flags": [lock.value for lock in sorted(self.lock_flags, key=str)],
            "order": self.order,
            "parent_id": self.parent_id,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "image_item_id": self.image_item_id,
            "drawable_id": self.drawable_id,
            "tile_store_id": self.tile_store_id,
            "graph_node_id": self.graph_node_id,
            "generation": self.generation,
            "filter_operation": self.filter_operation,
            "filter_parameters": self.filter_parameters,
            "content": self.content,
            "alpha": self.alpha,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EditLayer:
        """Deserialize the layer."""
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            source_node_id=data.get("source_node_id"),
            layer_type=EditLayerType(data.get("layer_type", EditLayerType.RASTER.value)),
            content_kind=LayerContentKind(data.get("content_kind", LayerContentKind.EMPTY.value)),
            visible=bool(data.get("visible", True)),
            opacity=float(data.get("opacity", 1.0)),
            blend_mode=BlendMode(data.get("blend_mode", BlendMode.NORMAL.value)),
            mask_node_id=data.get("mask_node_id"),
            mask_content=data.get("mask_content"),
            mask_enabled=bool(data.get("mask_enabled", True)),
            mask_edit_state=MaskViewMode(data.get("mask_edit_state", MaskViewMode.APPLY.value)),
            group_composite_mode=GroupCompositeMode(
                data.get("group_composite_mode", GroupCompositeMode.PASS_THROUGH.value)
            ),
            lock_flags={
                LayerLock(value)
                for value in data.get(
                    "lock_flags",
                    [LayerLock.ALL.value] if data.get("locked", False) else [],
                )
            },
            order=int(data.get("order", 0)),
            parent_id=data.get("parent_id"),
            offset_x=int(data.get("offset_x", 0)),
            offset_y=int(data.get("offset_y", 0)),
            image_item_id=str(data.get("image_item_id", data["id"])),
            drawable_id=str(data.get("drawable_id", data["id"])),
            tile_store_id=str(data.get("tile_store_id", data["id"])),
            graph_node_id=str(data.get("graph_node_id", data["id"])),
            generation=int(data.get("generation", 0)),
            filter_operation=(
                str(data["filter_operation"])
                if data.get("filter_operation") is not None
                else None
            ),
            filter_parameters=dict(data.get("filter_parameters", {})),
            content=data.get("content"),
            alpha=data.get("alpha"),
        )


@dataclass(slots=True)
class RetouchStroke:
    """Stroke-level provenance for manual retouching tools."""

    image_node_id: str
    tool: str
    points: list[tuple[float, float]]
    radius: float
    opacity: float = 1.0
    source_points: list[tuple[float, float]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    layer_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the retouch stroke."""
        return {
            "id": self.id,
            "image_node_id": self.image_node_id,
            "tool": self.tool,
            "points": [list(point) for point in self.points],
            "radius": self.radius,
            "opacity": self.opacity,
            "source_points": [list(point) for point in self.source_points],
            "parameters": self.parameters,
            "layer_id": self.layer_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetouchStroke:
        """Deserialize a retouch stroke."""
        return cls(
            id=str(data["id"]),
            image_node_id=str(data["image_node_id"]),
            tool=str(data["tool"]),
            points=[(float(point[0]), float(point[1])) for point in data.get("points", [])],
            radius=float(data["radius"]),
            opacity=float(data.get("opacity", 1.0)),
            source_points=[
                (float(point[0]), float(point[1]))
                for point in data.get("source_points", [])
            ],
            parameters=dict(data.get("parameters", {})),
            layer_id=data.get("layer_id"),
            created_at=str(data["created_at"]),
        )


@dataclass(slots=True)
class SelectionMask:
    """Stored selection mask metadata."""

    width: int
    height: int
    mask_node_id: str
    feather_radius: float = 0.0
    source_node_id: str | None = None
    coverage: dict[str, Any] | None = None
    revision: int = 0
    inverted: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))

    def coverage_pixels(self) -> np.ndarray | None:
        """Return persisted float selection coverage, if present."""
        return payload_to_pixels(self.coverage)

    def set_coverage_pixels(self, coverage: np.ndarray | None) -> None:
        """Persist authoritative float selection coverage."""
        if coverage is None:
            self.coverage = None
            return
        self.coverage = pixels_to_payload(np.asarray(coverage, dtype=np.float32))
        self.revision += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the selection."""
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "mask_node_id": self.mask_node_id,
            "feather_radius": self.feather_radius,
            "source_node_id": self.source_node_id,
            "coverage": self.coverage,
            "revision": self.revision,
            "inverted": self.inverted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelectionMask:
        """Deserialize the selection."""
        return cls(
            id=str(data["id"]),
            width=int(data["width"]),
            height=int(data["height"]),
            mask_node_id=str(data["mask_node_id"]),
            feather_radius=float(data.get("feather_radius", 0.0)),
            source_node_id=data.get("source_node_id"),
            coverage=data.get("coverage"),
            revision=int(data.get("revision", 0)),
            inverted=bool(data.get("inverted", False)),
        )
