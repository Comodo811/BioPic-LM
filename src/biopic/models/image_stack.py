"""Ordered microscopy image-stack records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class StackKind(StrEnum):
    """How a set of images should be interpreted."""

    FOCAL = "focal"
    TIME = "time"
    INDEPENDENT = "independent"


@dataclass(slots=True)
class ImageStack:
    """An ordered, non-destructive grouping of source assets."""

    asset_ids: list[str]
    kind: StackKind = StackKind.FOCAL
    enabled_asset_ids: list[str] | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "Image Stack"

    def __post_init__(self) -> None:
        if self.enabled_asset_ids is None:
            self.enabled_asset_ids = list(self.asset_ids)

    def is_enabled(self, asset_id: str) -> bool:
        """Return whether an asset participates in processing."""
        return asset_id in set(self.enabled_asset_ids or [])

    def to_dict(self) -> dict[str, Any]:
        """Serialize the stack."""
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "asset_ids": self.asset_ids,
            "enabled_asset_ids": self.enabled_asset_ids or [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageStack:
        """Deserialize the stack."""
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "Image Stack")),
            kind=StackKind(data.get("kind", StackKind.FOCAL.value)),
            asset_ids=[str(item) for item in data.get("asset_ids", [])],
            enabled_asset_ids=[str(item) for item in data.get("enabled_asset_ids", [])],
        )
