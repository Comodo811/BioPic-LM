"""Operation application helpers for the edit workspace."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

import numpy as np

from biopic.imaging.editing import (
    apply_edit_operation,
    flat_field_correction_estimated,
    rotated_content_crop_rect,
    subtract_background_estimated,
)
from biopic.imaging.io import read_image_asset
from biopic.imaging.layer_buffers import set_layer_buffers
from biopic.imaging.project_render import render_edit_layers
from biopic.models.editing import AdjustmentLayer, EditLayer, LayerContentKind
from biopic.pipeline.node import ProcessingNode
from biopic.ui.workspace_helpers.operations import (
    is_adjustment_operation as _is_adjustment_operation,
)
from biopic.ui.workspace_helpers.operations import (
    is_filter_result_layer_operation as _is_filter_result_layer_operation,
)
from biopic.ui.workspace_helpers.operations import (
    operation_layer_name as _operation_layer_name,
)

LOGGER = logging.getLogger(__name__)


class EditOperationsMixin:
    """Apply edit operations and persist their resulting layers/nodes."""

    def apply_current_operation(self) -> None:
        """Apply an edit operation, display it, and record a processing node."""
        if self._current_pixels is None or self._current_asset_id is None:
            return
        operation = str(self.operation_combo.currentData())
        parameters = self._parameters(operation)
        if operation == "uniform_background_outside_selection":
            self.create_uniform_background_outside_selection_layer()
            return
        if operation == "healed_uniform_background_outside_selection":
            self.create_healed_uniform_background_outside_selection_layer()
            return
        if _is_filter_result_layer_operation(operation):
            if operation in {
                "flat_field_correction_estimated",
                "subtract_background_estimated",
            }:
                start = perf_counter()
                result = self._run_computation_with_progress(
                    f"Applying {operation.replace('_', ' ')}...",
                    lambda progress: self._apply_background_correction_with_progress(
                        operation,
                        parameters,
                        progress,
                    ),
                    accepts_progress=True,
                )
                LOGGER.debug(
                    "edit filter %s computed in %.3fs for shape=%s dtype=%s",
                    operation,
                    perf_counter() - start,
                    getattr(result, "shape", None),
                    getattr(result, "dtype", None),
                )
                if isinstance(result, np.ndarray):
                    self._commit_filter_result_layer(result, operation, parameters)
                return

            def apply_filter_layer() -> None:
                start = perf_counter()
                result = apply_edit_operation(
                    self._filter_operation_source_pixels(),
                    operation,
                    parameters,
                )
                LOGGER.debug(
                    "edit filter %s computed in %.3fs for shape=%s dtype=%s",
                    operation,
                    perf_counter() - start,
                    getattr(result, "shape", None),
                    getattr(result, "dtype", None),
                )
                self._commit_filter_result_layer(result, operation, parameters)

            self._run_with_progress(
                f"Applying {operation.replace('_', ' ')}...",
                apply_filter_layer,
            )
            return
        if _is_adjustment_operation(operation):
            def apply_adjustment() -> None:
                self._upsert_adjustment_layer_from_operation(operation, parameters)
                self._render_current_adjustment_preview()

            self._run_with_progress(
                f"Applying {operation.replace('_', ' ')}...",
                apply_adjustment,
            )
            self._refresh_adjustments()
            return
        def apply_operation() -> None:
            result = apply_edit_operation(self._current_pixels, operation, parameters)
            self._commit_edit_result(
                result,
                operation,
                parameters,
                adjustment_operation=_is_adjustment_operation(operation),
            )

        self._run_with_progress(
            f"Applying {operation.replace('_', ' ')}...",
            apply_operation,
        )

    def _apply_background_correction_with_progress(
        self,
        operation: str,
        parameters: dict[str, object],
        progress: Callable[[str, float], None],
    ) -> np.ndarray:
        if self._current_pixels is None:
            raise ValueError("No image is loaded")
        source_pixels = self._filter_operation_source_pixels()
        if operation == "flat_field_correction_estimated":
            return flat_field_correction_estimated(
                source_pixels,
                sigma=float(parameters.get("sigma", 24.0)),
                strength=float(parameters.get("strength", parameters.get("amount", 1.0))),
                preserve_mean=bool(parameters.get("preserve_mean", True)),
                progress=progress,
            )
        if operation == "subtract_background_estimated":
            return subtract_background_estimated(
                source_pixels,
                sigma=float(parameters.get("sigma", 24.0)),
                amount=float(parameters.get("amount", 1.0)),
                progress=progress,
            )
        return apply_edit_operation(source_pixels, operation, parameters)

    def rotate_current_image(self, angle: float) -> None:
        """Commit the current interactive canvas rotation."""
        if self._current_pixels is None:
            return
        self.apply_named_operation("rotate_free", {"angle": float(angle)})

    def crop_rotated_image(self) -> None:
        """Crop transparent rotation corners to the largest axis-aligned rectangle."""
        if self._current_pixels is None:
            return
        self.apply_named_operation("crop_rotated_image")
        self.canvas.clear_crop_cut_preview()

    def fill_rotated_background(self) -> None:
        """Fill transparent rotation corners using extrapolated edge background."""
        if self._current_pixels is None:
            return
        self.apply_named_operation("fill_rotated_background")
        self.canvas.clear_crop_cut_preview()

    def show_rotated_crop_preview(self) -> None:
        """Preview which transparent corners will be removed by the crop button."""
        if self._current_pixels is None:
            self.canvas.clear_crop_cut_preview()
            return
        self.canvas.set_crop_cut_preview_rect(rotated_content_crop_rect(self._current_pixels))

    def _filter_operation_source_pixels(self) -> np.ndarray:
        """Return pixels for raster filters before global adjustment layers are applied."""
        if self._current_source_node_id is not None and self._base_pixels is not None:
            return render_edit_layers(
                self.project,
                self._current_source_node_id,
                self._base_pixels,
            ).copy()
        if self._current_pixels is None:
            raise ValueError("No image is loaded")
        return self._current_pixels.copy()

    def _parameters(self, operation: str) -> dict[str, object]:
        value = self.primary_spin.value()
        secondary = self.secondary_spin.value()
        if operation == "gamma":
            return {"gamma": value}
        if operation == "white_balance":
            parameters: dict[str, object] = {
                "red": value,
                "green": 1.0,
                "blue": secondary,
                "normalize": True,
            }
            raw_metadata = self._white_balance_raw_metadata()
            if raw_metadata:
                parameters["raw_metadata"] = raw_metadata
            return parameters
        if operation == "color_saturation":
            return {
                "range": "all",
                "hue": 0.0,
                "saturation": value,
                "lightness": secondary,
                "overlap": 0.0,
            }
        if operation == "levels":
            return {
                "black_point": 0.0,
                "white_point": 1.0,
                "midtone": max(value, 0.01),
                "output_black": 0.0,
                "output_white": 1.0,
                "channel": "rgb",
            }
        if operation == "curve":
            return {"points": [(0.0, 0.0), (0.5, value / 2.0), (1.0, 1.0)], "channel": "rgb"}
        if operation == "auto_levels":
            return {"percentile": value}
        if operation == "high_pass":
            return {
                "sigma": self.high_pass_radius_spin.value(),
                "amount": self.high_pass_amount_spin.value(),
            }
        if operation == "gaussian":
            return {"sigma": value}
        if operation == "median":
            return {"radius": int(round(value))}
        if operation == "threshold":
            return {"threshold": value}
        if operation == "sharpen":
            return {"sigma": max(value, 0.01), "amount": 1.0}
        if operation == "denoise":
            return {"method": "gimp", "strength": int(round(value))}
        if operation == "total_variation":
            return {"weight": value}
        if operation == "wavelet_sharpen":
            return {
                "levels": 4,
                "amount": value,
                "threshold": 0.01,
                "luminance_only": False,
            }
        if operation == "local_contrast":
            return {
                "radius": value,
                "amount": 0.25,
                "threshold": 0.01,
                "shadow_protection": 0.25,
                "highlight_protection": 0.05,
                "halo_suppression": 0.25,
                "luminance_only": True,
            }
        if operation == "deconvolution":
            return {"radius": value, "iterations": 8, "amount": 0.5, "damping": 0.001}
        if operation == "rotate_90":
            return {"turns": int(round(value))}
        if operation == "scale_uniform":
            return {"scale": max(0.05, value / 100.0)}
        if operation == "crop" and self._selection_rect is not None:
            x, y, width, height = self._selection_rect
            return {"x": x, "y": y, "width": width, "height": height}
        if operation == "flat_field_correction_estimated":
            return {"sigma": value, "strength": 1.0, "preserve_mean": True}
        if operation == "subtract_background_estimated":
            return {"sigma": value, "amount": 1.0}
        if operation in {
            "uniform_background_outside_selection",
            "healed_uniform_background_outside_selection",
        }:
            return {"selection_mask": self._selection_mask()}
        return {}

    def _white_balance_raw_metadata(self) -> dict[str, object]:
        if self._current_asset_id is None:
            return {}
        asset = self.project.assets.get(self._current_asset_id)
        if asset is None:
            return {}
        raw_keys = {
            "black_level_per_channel",
            "camera_whitebalance",
            "daylight_whitebalance",
            "white_level",
        }
        metadata: dict[str, object] = {}
        for key, value in asset.metadata.items():
            if key.startswith("raw_") or key in raw_keys:
                metadata[key] = value
        return metadata

    def apply_named_operation(
        self, operation: str, parameters_override: dict[str, object] | None = None
    ) -> None:
        """Apply an operation directly from a context-toolbar menu."""
        if self._current_pixels is None:
            return
        index = self.operation_combo.findData(operation)
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        parameters = self._parameters(operation)
        if parameters_override:
            parameters.update(parameters_override)
        if operation == "uniform_background_outside_selection":
            self.create_uniform_background_outside_selection_layer()
            return
        if operation == "healed_uniform_background_outside_selection":
            self.create_healed_uniform_background_outside_selection_layer()
            return
        if _is_adjustment_operation(operation):
            def apply_adjustment() -> None:
                self._upsert_adjustment_layer_from_operation(operation, parameters)
                self._render_current_adjustment_preview()

            self._run_with_progress(
                f"Applying {operation.replace('_', ' ')}...",
                apply_adjustment,
            )
            self._refresh_adjustments()
            return
        if operation in {
            "flat_field_correction_estimated",
            "subtract_background_estimated",
        }:
            result = self._run_computation_with_progress(
                f"Applying {operation.replace('_', ' ')}...",
                lambda progress: self._apply_background_correction_with_progress(
                    operation,
                    parameters,
                    progress,
                ),
                accepts_progress=True,
            )
            if isinstance(result, np.ndarray):
                self._commit_filter_result_layer(result, operation, parameters)
            return

        def apply_operation() -> None:
            source_pixels = (
                self._filter_operation_source_pixels()
                if _is_filter_result_layer_operation(operation)
                else self._current_pixels
            )
            result = apply_edit_operation(source_pixels, operation, parameters)
            if _is_filter_result_layer_operation(operation):
                self._commit_filter_result_layer(result, operation, parameters)
            else:
                self._commit_edit_result(result, operation, parameters)

        self._run_with_progress(
            f"Applying {operation.replace('_', ' ')}...",
            apply_operation,
        )

    def _commit_edit_result(
        self,
        result: np.ndarray,
        operation: str,
        parameters: dict[str, object],
        *,
        adjustment_operation: bool = False,
    ) -> None:
        self._current_pixels = result
        self.canvas.set_pixels(result, f"{operation} preview")
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        inputs = () if source_node is None else (source_node,)
        node = ProcessingNode(
            operation=f"edit.{operation}",
            inputs=inputs,
            parameters=parameters,
            provenance={"non_destructive": True, "tool": self._selected_tool},
        )
        self.project.graph.add_node(node)
        if adjustment_operation:
            self._add_adjustment_layer(operation, parameters, node)
        self.project.touch()
        self._refresh_history()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

    def _commit_filter_result_layer(
        self, result: np.ndarray, operation: str, parameters: dict[str, object]
    ) -> None:
        """Store an applied correction/filter as a separate raster result layer."""
        commit_start = perf_counter()
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        before = self._snapshot_edit_state()
        node = ProcessingNode(
            operation=f"filter-layer.{operation}",
            inputs=(source_node,),
            parameters=dict(parameters),
            provenance={
                "non_destructive": True,
                "layer_result": True,
                "source": "current rendered edit image",
            },
        )
        self.project.graph.add_node(node)
        layer = EditLayer(
            name=_operation_layer_name(operation),
            source_node_id=source_node,
            content_kind=LayerContentKind.RASTER,
            order=self._next_layer_order(source_node),
            graph_node_id=node.id,
            filter_operation=operation,
            filter_parameters=dict(parameters),
        )
        alpha = np.ones(result.shape[:2], dtype=np.float32)
        layer.bump_generation()
        self.project.edit_layers[layer.id] = layer
        set_layer_buffers(layer.id, result, alpha)
        self.project.active_edit_layers[source_node] = layer.id
        self._current_layer_id = layer.id
        self._current_pixels = result
        self._edit_composite_cache = result
        self._edit_composite_cache_key = self._edit_composite_key(source_node)
        self._finish_command(f"add {layer.name} layer", before)
        after_history = perf_counter()
        self._refresh_layers()
        after_layers = perf_counter()
        self._render_current_adjustment_preview()
        after_render = perf_counter()
        LOGGER.debug(
            "edit filter %s committed in %.3fs (history %.3fs, layers %.3fs, render %.3fs)",
            operation,
            after_render - commit_start,
            after_history - commit_start,
            after_layers - after_history,
            after_render - after_layers,
        )
        if self.editApplied is not None:
            self.editApplied()

    def _filter_operation_source_pixels_for_layer(self, layer: EditLayer) -> np.ndarray:
        """Return the rendered source below an editable filter layer."""
        if self._base_pixels is None:
            raise ValueError("No base image is loaded")
        source_node = layer.source_node_id
        if source_node is None:
            return self._base_pixels.copy()
        hidden_layers: list[tuple[EditLayer, bool]] = []
        for candidate in self.project.edit_layers.values():
            if candidate.source_node_id not in {None, source_node}:
                continue
            if candidate.id == layer.id or candidate.order >= layer.order:
                hidden_layers.append((candidate, candidate.visible))
                candidate.visible = False
        self._invalidate_edit_composite_cache()
        try:
            return render_edit_layers(self.project, source_node, self._base_pixels).copy()
        finally:
            for candidate, visible in hidden_layers:
                candidate.visible = visible
            self._invalidate_edit_composite_cache()

    def _filter_parameters_for_compute(
        self,
        operation: str,
        parameters: dict[str, object],
    ) -> dict[str, object]:
        """Resolve persisted filter settings into apply_edit_operation parameters."""
        if operation != "flat_field" or "flat_path" not in parameters:
            return dict(parameters)
        flat_path = parameters.get("flat_path")
        if not isinstance(flat_path, str) or not flat_path:
            return dict(parameters)
        resolved = dict(parameters)
        resolved["flat"] = read_image_asset(Path(flat_path), load_pixels=True).pixels
        return resolved

    def _update_filter_layer_parameters(
        self,
        layer_id: str,
        parameters: dict[str, object],
    ) -> None:
        """Recompute an editable raster filter layer and record it as an undoable command."""
        layer = self.project.edit_layers.get(layer_id)
        if layer is None or layer.filter_operation is None:
            return
        before = self._snapshot_edit_state()
        operation = layer.filter_operation
        source_pixels = self._filter_operation_source_pixels_for_layer(layer)
        compute_parameters = self._filter_parameters_for_compute(operation, parameters)
        result = apply_edit_operation(source_pixels, operation, compute_parameters)
        layer.filter_parameters = dict(parameters)
        layer.name = _operation_layer_name(operation)
        layer.bump_generation()
        set_layer_buffers(
            layer.id,
            result,
            np.ones(result.shape[:2], dtype=np.float32),
        )
        if layer.source_node_id is not None:
            self.project.active_edit_layers[layer.source_node_id] = layer.id
        self._current_layer_id = layer.id
        self._finish_command(f"update {layer.name} layer", before)
        self._invalidate_edit_composite_cache()
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

    def _add_adjustment_layer(
        self, operation: str, parameters: dict[str, object], node: ProcessingNode
    ) -> None:
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        image_node_id = source_node or node.id
        order = sum(
            1
            for layer in self.project.adjustment_layers.values()
            if layer.image_node_id == image_node_id
        )
        layer = AdjustmentLayer(
            name=_operation_layer_name(operation),
            image_node_id=image_node_id,
            operation=operation,
            parameters=dict(parameters),
            order=order,
        )
        self.project.add_adjustment_layer(layer)

    def _add_adjustment_layer_from_operation(
        self, operation: str, parameters: dict[str, object]
    ) -> None:
        self._upsert_adjustment_layer_from_operation(operation, parameters, replace_existing=False)

    def _upsert_adjustment_layer_from_operation(
        self,
        operation: str,
        parameters: dict[str, object],
        *,
        replace_existing: bool = True,
    ) -> None:
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        before = self._snapshot_edit_state()
        if replace_existing:
            existing = next(
                (
                    layer
                    for layer in self.project.adjustment_layers_for_image(source_node)
                    if layer.operation == operation
                ),
                None,
            )
            if existing is not None:
                self.project.update_adjustment_layer(existing.id, dict(parameters), enabled=True)
                self._finish_command(f"update {operation.replace('_', ' ')} adjustment", before)
                self._refresh_layers()
                if self.editApplied is not None:
                    self.editApplied()
                return
        node = ProcessingNode(
            operation=f"adjustment.{operation}",
            inputs=(source_node,),
            parameters=dict(parameters),
            provenance={"non_destructive": True, "renderer": "BioPic LM adjustment pipeline"},
        )
        self.project.graph.add_node(node)
        order = len(self.project.adjustment_layers_for_image(source_node))
        layer = AdjustmentLayer(
            name=_operation_layer_name(operation),
            image_node_id=source_node,
            operation=operation,
            parameters=dict(parameters),
            order=order,
            cache_key=None,
        )
        self.project.add_adjustment_layer(layer)
        self._finish_command(f"add {operation.replace('_', ' ')} adjustment", before)
        self._refresh_layers()
        if self.editApplied is not None:
            self.editApplied()

    def _start_white_balance_spot_pick(self, sample_size: int) -> None:
        self._pending_white_balance_spot_sample_size = max(3, int(sample_size))
        self.select_tool("color_picker")
        self._status("Click a neutral white/gray spot to set white balance.")

    def _apply_white_balance_spot_from_point(self, x: int, y: int) -> None:
        if self._current_pixels is None:
            return
        sample_size = max(3, int(self._pending_white_balance_spot_sample_size or 24))
        self._pending_white_balance_spot_sample_size = None
        image_height, image_width = self._current_pixels.shape[:2]
        half = sample_size // 2
        left = max(0, min(image_width - 1, int(x) - half))
        top = max(0, min(image_height - 1, int(y) - half))
        width = max(1, min(sample_size, image_width - left))
        height = max(1, min(sample_size, image_height - top))
        self.apply_named_operation(
            "white_balance",
            {
                "method": "spot",
                "sample_rect": (left, top, width, height),
                "sample_size": sample_size,
                "normalize": True,
            },
        )
        self.select_tool("pan")
        self._status(f"White balance sampled from {width} x {height}px spot.")
