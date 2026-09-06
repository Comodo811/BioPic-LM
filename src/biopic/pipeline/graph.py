"""Dependency graph with downstream invalidation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from biopic.models.status import NodeStatus
from biopic.pipeline.node import ProcessingNode


@dataclass(slots=True)
class ProcessingGraph:
    """A directed acyclic graph of processing operations."""

    nodes: dict[str, ProcessingNode] = field(default_factory=dict)

    def add_node(self, node: ProcessingNode) -> None:
        """Add a node after checking dependencies and cycles."""
        missing = [node_id for node_id in node.inputs if node_id not in self.nodes]
        if missing:
            raise ValueError(f"Unknown input node(s): {', '.join(missing)}")
        self.nodes[node.id] = node
        if self._has_cycle():
            del self.nodes[node.id]
            raise ValueError(f"Adding node {node.id} would create a cycle")

    def update_node_parameters(self, node_id: str, parameters: dict[str, Any]) -> set[str]:
        """Update a node and mark descendants stale."""
        node = self.nodes[node_id]
        node.update_parameters(parameters)
        return self.invalidate_downstream(node_id)

    def invalidate_downstream(self, node_id: str) -> set[str]:
        """Mark all downstream dependencies stale."""
        dependents = self.dependents()
        stale: set[str] = set()
        queue: deque[str] = deque(dependents.get(node_id, set()))
        while queue:
            current = queue.popleft()
            if current in stale:
                continue
            stale.add(current)
            self.nodes[current].status = NodeStatus.STALE
            self.nodes[current].cache_key = None
            queue.extend(dependents.get(current, set()))
        return stale

    def dependents(self) -> dict[str, set[str]]:
        """Return reverse dependency edges."""
        reverse: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for node_id, node in self.nodes.items():
            for input_id in node.inputs:
                reverse.setdefault(input_id, set()).add(node_id)
        return reverse

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph."""
        return {"nodes": [node.to_dict() for node in self.nodes.values()]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingGraph:
        """Deserialize the graph.

        Saved projects can contain legacy graph nodes whose input references point to
        nodes that are no longer present in the manifest. Loading should preserve the
        recoverable project state instead of failing the whole document. Runtime graph
        mutation remains strict through add_node().
        """
        graph = cls()
        nodes = [
            ProcessingNode.from_dict(node_data)
            for node_data in data.get("nodes", [])
            if isinstance(node_data, dict)
        ]
        node_ids = {node.id for node in nodes}
        for node in nodes:
            missing_inputs = tuple(input_id for input_id in node.inputs if input_id not in node_ids)
            if missing_inputs:
                node.inputs = tuple(input_id for input_id in node.inputs if input_id in node_ids)
                node.status = NodeStatus.STALE
                node.cache_key = None
                node.provenance = {
                    **node.provenance,
                    "legacy_missing_inputs_removed": list(missing_inputs),
                }
            graph.nodes[node.id] = node
        if graph._has_cycle():
            graph._break_cycles()
        return graph

    def _has_cycle(self) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for input_id in self.nodes[node_id].inputs:
                if visit(input_id):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node_id) for node_id in self.nodes)

    def _break_cycles(self) -> None:
        """Remove legacy dependency edges that form cycles during project loading."""
        safe_inputs: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            visiting.add(node_id)
            node = self.nodes[node_id]
            removed: list[str] = []
            for input_id in node.inputs:
                if input_id not in self.nodes:
                    removed.append(input_id)
                    continue
                if input_id in visiting:
                    removed.append(input_id)
                    continue
                visit(input_id)
                safe_inputs[node_id].append(input_id)
            visiting.remove(node_id)
            visited.add(node_id)
            if removed:
                node.inputs = tuple(safe_inputs[node_id])
                node.status = NodeStatus.STALE
                node.cache_key = None
                node.provenance = {
                    **node.provenance,
                    "legacy_cycle_inputs_removed": removed,
                }

        for node_id in list(self.nodes):
            visit(node_id)
