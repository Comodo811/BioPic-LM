"""Processing graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from biopic.models.status import NodeStatus


@dataclass(slots=True)
class ProcessingNode:
    """An immutable-by-version operation in the non-destructive pipeline."""

    operation: str
    inputs: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1
    status: NodeStatus = NodeStatus.COMPLETE
    cache_key: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def update_parameters(self, parameters: dict[str, Any]) -> None:
        """Replace operation parameters and advance the node version."""
        self.parameters = dict(parameters)
        self.version += 1
        self.status = NodeStatus.MODIFIED
        self.cache_key = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the node."""
        return {
            "id": self.id,
            "operation": self.operation,
            "inputs": list(self.inputs),
            "parameters": self.parameters,
            "version": self.version,
            "status": self.status.value,
            "cache_key": self.cache_key,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingNode:
        """Deserialize the node."""
        return cls(
            id=str(data["id"]),
            operation=str(data["operation"]),
            inputs=tuple(str(item) for item in data.get("inputs", [])),
            parameters=dict(data.get("parameters", {})),
            version=int(data.get("version", 1)),
            status=NodeStatus(data.get("status", NodeStatus.COMPLETE.value)),
            cache_key=data.get("cache_key"),
            provenance=dict(data.get("provenance", {})),
        )
