"""Source image asset records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class ImageAssetKind(StrEnum):
    """Project image roles used by workspace filters and pipeline propagation."""

    DIRECT_IMPORT = "direct_import"
    STACK_SOURCE = "stack_source"
    STACK_RESULT = "stack_result"
    EDIT_DERIVATIVE = "edit_derivative"
    EXTERNAL_LINK = "external_link"


@dataclass(slots=True)
class ImageAsset:
    """A non-destructive reference to an imported source image."""

    path: str
    kind: ImageAssetKind = ImageAssetKind.DIRECT_IMPORT
    id: str = field(default_factory=lambda: str(uuid4()))
    checksum: str | None = None
    width: int | None = None
    height: int | None = None
    frames: int = 1
    dtype: str | None = None
    color_model: str | None = None
    display_name: str | None = None
    origin_node_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        """Return the display filename."""
        return self.display_name or Path(self.path).name

    @property
    def is_editable_browser_image(self) -> bool:
        """Return whether the image should appear in the Edit Image browser."""
        return self.kind is not ImageAssetKind.STACK_SOURCE

    def to_dict(self) -> dict[str, Any]:
        """Serialize the asset."""
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind.value,
            "checksum": self.checksum,
            "width": self.width,
            "height": self.height,
            "frames": self.frames,
            "dtype": self.dtype,
            "color_model": self.color_model,
            "display_name": self.display_name,
            "origin_node_id": self.origin_node_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageAsset:
        """Deserialize an asset."""
        return cls(
            id=str(data["id"]),
            path=str(data["path"]),
            kind=ImageAssetKind(data.get("kind", ImageAssetKind.DIRECT_IMPORT.value)),
            checksum=data.get("checksum"),
            width=data.get("width"),
            height=data.get("height"),
            frames=int(data.get("frames", 1)),
            dtype=data.get("dtype"),
            color_model=data.get("color_model"),
            display_name=data.get("display_name"),
            origin_node_id=data.get("origin_node_id"),
            metadata=dict(data.get("metadata", {})),
        )
