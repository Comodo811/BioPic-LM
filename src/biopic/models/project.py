"""Project document model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from biopic.models.annotations import AnnotationDefinition, AnnotationObject
from biopic.models.calibration import Calibration, ScalePreset
from biopic.models.editing import AdjustmentLayer, EditLayer, RetouchStroke, SelectionMask
from biopic.models.figure_board import FigureBoard, FigurePanel
from biopic.models.image_asset import ImageAsset
from biopic.models.image_stack import ImageStack
from biopic.models.measurement import Measurement, ScaleBar
from biopic.pipeline.graph import ProcessingGraph
from biopic.pipeline.node import ProcessingNode

PROJECT_SCHEMA_VERSION = 1


@dataclass(slots=True)
class Project:
    """Complete non-destructive BioPic LM project state."""

    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = PROJECT_SCHEMA_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    assets: dict[str, ImageAsset] = field(default_factory=dict)
    stacks: dict[str, ImageStack] = field(default_factory=dict)
    graph: ProcessingGraph = field(default_factory=ProcessingGraph)
    calibrations: dict[str, Calibration] = field(default_factory=dict)
    scale_presets: dict[str, ScalePreset] = field(default_factory=dict)
    measurements: dict[str, Measurement] = field(default_factory=dict)
    scale_bars: dict[str, ScaleBar] = field(default_factory=dict)
    adjustment_layers: dict[str, AdjustmentLayer] = field(default_factory=dict)
    edit_layers: dict[str, EditLayer] = field(default_factory=dict)
    retouch_strokes: dict[str, RetouchStroke] = field(default_factory=dict)
    selections: dict[str, SelectionMask] = field(default_factory=dict)
    annotation_definitions: dict[str, AnnotationDefinition] = field(default_factory=dict)
    annotations: dict[str, AnnotationObject] = field(default_factory=dict)
    figure_panels: dict[str, FigurePanel] = field(default_factory=dict)
    figure_boards: dict[str, FigureBoard] = field(default_factory=dict)
    active_edit_layers: dict[str, str] = field(default_factory=dict)
    metadata_presets: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "equipment": [],
            "location": [],
            "collector": [],
            "preparation": [],
        }
    )
    undo_stack: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def new(cls, name: str) -> Project:
        """Create a new project."""
        return cls(name=name)

    def touch(self) -> None:
        """Update modification timestamp."""
        self.modified_at = datetime.now(UTC).isoformat()

    def add_asset(self, asset: ImageAsset) -> None:
        """Add a source image asset."""
        self.assets[asset.id] = asset
        self.graph.add_node(
            ProcessingNode(operation="source_image", parameters={"asset_id": asset.id})
        )
        self.touch()

    def source_node_id_for_asset(self, asset_id: str) -> str | None:
        """Return the processing-node id that represents an imported source asset."""
        for node_id, node in self.graph.nodes.items():
            if node.operation == "source_image" and node.parameters.get("asset_id") == asset_id:
                return node_id
        return None

    def add_stack(self, stack: ImageStack) -> None:
        """Add an ordered image stack."""
        missing = [asset_id for asset_id in stack.asset_ids if asset_id not in self.assets]
        if missing:
            raise ValueError(f"Unknown stack asset(s): {', '.join(missing)}")
        self.stacks[stack.id] = stack
        self.touch()

    def adjustment_layers_for_image(self, image_node_id: str) -> list[AdjustmentLayer]:
        """Return adjustment layers for an image node in render order."""
        return sorted(
            (
                layer
                for layer in self.adjustment_layers.values()
                if layer.image_node_id == image_node_id
            ),
            key=lambda layer: layer.order,
        )

    def add_adjustment_layer(self, layer: AdjustmentLayer) -> None:
        """Add a non-destructive adjustment layer and invalidate downstream caches."""
        self.adjustment_layers[layer.id] = layer
        if layer.image_node_id in self.graph.nodes:
            self.graph.invalidate_downstream(layer.image_node_id)
        self.touch()

    def update_adjustment_layer(
        self,
        layer_id: str,
        parameters: dict[str, Any] | None = None,
        *,
        enabled: bool | None = None,
    ) -> set[str]:
        """Update an adjustment layer and mark affected graph descendants stale."""
        layer = self.adjustment_layers[layer_id]
        if parameters is not None:
            layer.parameters = dict(parameters)
        if enabled is not None:
            layer.enabled = enabled
        layer.touch()
        stale = (
            self.graph.invalidate_downstream(layer.image_node_id)
            if layer.image_node_id in self.graph.nodes
            else set()
        )
        self.touch()
        return stale

    def to_dict(self) -> dict[str, Any]:
        """Serialize the project manifest."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "assets": [asset.to_dict() for asset in self.assets.values()],
            "stacks": [stack.to_dict() for stack in self.stacks.values()],
            "graph": self.graph.to_dict(),
            "calibrations": {
                key: calibration.to_dict() for key, calibration in self.calibrations.items()
            },
            "scale_presets": [preset.to_dict() for preset in self.scale_presets.values()],
            "measurements": [
                measurement.to_dict() for measurement in self.measurements.values()
            ],
            "scale_bars": [scale_bar.to_dict() for scale_bar in self.scale_bars.values()],
            "adjustment_layers": [
                layer.to_dict() for layer in self.adjustment_layers.values()
            ],
            "edit_layers": [layer.to_dict() for layer in self.edit_layers.values()],
            "retouch_strokes": [
                stroke.to_dict() for stroke in self.retouch_strokes.values()
            ],
            "selections": [selection.to_dict() for selection in self.selections.values()],
            "annotation_definitions": [
                definition.to_dict() for definition in self.annotation_definitions.values()
            ],
            "annotations": [annotation.to_dict() for annotation in self.annotations.values()],
            "figure_panels": [panel.to_dict() for panel in self.figure_panels.values()],
            "figure_boards": [board.to_dict() for board in self.figure_boards.values()],
            "active_edit_layers": self.active_edit_layers,
            "metadata_presets": self.metadata_presets,
            "undo_stack": self.undo_stack,
            "redo_stack": self.redo_stack,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        """Deserialize a project manifest."""
        project = cls(
            id=str(data["id"]),
            name=str(data["name"]),
            schema_version=int(data.get("schema_version", PROJECT_SCHEMA_VERSION)),
            created_at=str(data["created_at"]),
            modified_at=str(data["modified_at"]),
            assets={
                asset.id: asset
                for asset in (ImageAsset.from_dict(item) for item in data.get("assets", []))
            },
            stacks={
                stack.id: stack
                for stack in (ImageStack.from_dict(item) for item in data.get("stacks", []))
            },
            graph=ProcessingGraph.from_dict(data.get("graph", {})),
            calibrations={
                str(key): Calibration.from_dict(value)
                for key, value in data.get("calibrations", {}).items()
            },
            scale_presets={
                preset.id: preset
                for preset in (
                    ScalePreset.from_dict(item) for item in data.get("scale_presets", [])
                )
            },
            measurements={
                measurement.id: measurement
                for measurement in (
                    Measurement.from_dict(item) for item in data.get("measurements", [])
                )
            },
            scale_bars={
                scale_bar.id: scale_bar
                for scale_bar in (
                    ScaleBar.from_dict(item) for item in data.get("scale_bars", [])
                )
            },
            adjustment_layers={
                layer.id: layer
                for layer in (
                    AdjustmentLayer.from_dict(item)
                    for item in data.get("adjustment_layers", [])
                )
            },
            edit_layers={
                layer.id: layer
                for layer in (EditLayer.from_dict(item) for item in data.get("edit_layers", []))
            },
            retouch_strokes={
                stroke.id: stroke
                for stroke in (
                    RetouchStroke.from_dict(item)
                    for item in data.get("retouch_strokes", [])
                )
            },
            selections={
                selection.id: selection
                for selection in (
                    SelectionMask.from_dict(item) for item in data.get("selections", [])
                )
            },
            annotation_definitions={
                definition.id: definition
                for definition in (
                    AnnotationDefinition.from_dict(item)
                    for item in data.get("annotation_definitions", [])
                )
            },
            annotations={
                annotation.id: annotation
                for annotation in (
                    AnnotationObject.from_dict(item) for item in data.get("annotations", [])
                )
            },
            figure_panels={
                panel.id: panel
                for panel in (FigurePanel.from_dict(item) for item in data.get("figure_panels", []))
            },
            figure_boards={
                board.id: board
                for board in (FigureBoard.from_dict(item) for item in data.get("figure_boards", []))
            },
            active_edit_layers={
                str(key): str(value)
                for key, value in data.get("active_edit_layers", {}).items()
            },
            metadata_presets={
                category: [
                    {str(key): value for key, value in preset.items()}
                    for preset in presets
                    if isinstance(preset, dict)
                ]
                for category, presets in data.get(
                    "metadata_presets",
                    {"equipment": [], "location": [], "collector": [], "preparation": []},
                ).items()
                if isinstance(presets, list)
            },
            undo_stack=list(data.get("undo_stack", [])),
            redo_stack=list(data.get("redo_stack", [])),
            history=list(data.get("history", [])),
        )
        return project
