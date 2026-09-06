"""Stack execution, preview, parameter, and comparison helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QComboBox, QDialog, QListWidgetItem, QTableWidgetItem

from biopic.imaging.io import read_image_asset
from biopic.imaging.stacking import (
    AlignmentMode,
    BackgroundMode,
    FocusMetric,
    FocusStackParameters,
    FocusStackResult,
    StackingMethod,
    gpu_backend_status,
)
from biopic.imaging.stacking.gpu_memory import plan_gpu_memory_from_shapes
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.pipeline.node import ProcessingNode
from biopic.sharpness_comparison.config_models import SharpnessComparisonSummary
from biopic.sharpness_comparison.dialog import SharpnessComparisonDialog
from biopic.sharpness_comparison.metrics import display_name as sharpness_metric_display_name
from biopic.sharpness_comparison.workers import (
    SharpnessComparisonJob,
    SharpnessComparisonWorker,
)
from biopic.ui.settings import set_settings_json, settings_json
from biopic.workers.focus_stack_worker import FocusStackJob, FocusStackWorker

STACK_DEFAULTS_KEY = "stack/default_parameters"


class StackExecutionMixin:
    """Run stack jobs, previews, comparison jobs, and parameter persistence."""

    def run_stacking(self) -> None:
        """Run focus stacking for the current stack."""
        self._start_stacking(preview=False)

    def open_sharpness_comparison(self) -> None:
        """Run a sharpness comparison for the current stack."""
        assets = self._current_stack_assets()
        stack = self._current_stack()
        if (
            stack is None
            or len(assets) < 2
            or self._worker is not None
            or self._comparison_worker is not None
        ):
            return
        dialog = SharpnessComparisonDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._running_stack_id = stack.id
        self.run_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.comparison_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        job = SharpnessComparisonJob(
            assets=assets,
            base_parameters=self._parameters(),
            config=dialog.config(),
            project_id=self.project.id,
            stack_name=stack.name,
        )
        self._comparison_worker = SharpnessComparisonWorker(job)
        self._comparison_worker.progressChanged.connect(self._show_progress)
        self._comparison_worker.comparisonFinished.connect(self._comparison_finished)
        self._comparison_worker.comparisonFailed.connect(self._stack_failed)
        self._comparison_worker.finished.connect(self._worker_finished)
        self._comparison_worker.start()

    def run_low_res_preview(self) -> None:
        """Run a temporary low-resolution focus-stack preview."""
        self._start_stacking(preview=True)

    def _start_stacking(self, preview: bool) -> None:
        """Run focus stacking for the current stack or a temporary preview."""
        assets = self._current_stack_assets()
        stack = self._current_stack()
        if stack is None:
            return
        if len(assets) < 1:
            return
        self._running_stack_id = stack.id
        self._running_preview = preview
        self._last_stack_progress_preview = None
        self._stack_display_overrides.pop(stack.id, None)
        self.run_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.comparison_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        parameters = self._parameters()
        if preview:
            parameters = replace(parameters, preview_scale=0.35)
        else:
            self._save_parameter_defaults(parameters)
        job = FocusStackJob(assets=assets, parameters=parameters)
        self._worker = FocusStackWorker(job)
        self._worker.progressChanged.connect(self._show_progress)
        self._worker.stackPreviewChanged.connect(self._show_stack_preview)
        self._worker.stackFinished.connect(self._stack_finished)
        self._worker.stackFailed.connect(self._stack_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def cancel_stacking(self) -> None:
        """Request cancellation of the current stack job."""
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
        if self._comparison_worker is not None:
            self._comparison_worker.cancel()
            self.cancel_button.setEnabled(False)

    def _parameters(self) -> FocusStackParameters:
        alignment = (
            AlignmentMode.TRANSLATION if self.align_check.isChecked() else AlignmentMode.NONE
        )
        patch_adjustment = self.patch_size_spin.value()
        return FocusStackParameters(
            stacking_method=StackingMethod(str(self.method_combo.currentData())),
            focus_metric=FocusMetric(str(self.metric_combo.currentData())),
            focus_radius=3,
            smoothing_sigma=self.smoothing_spin.value(),
            halo_suppression_sigma=self.noise_suppression_spin.value(),
            score_threshold=self.score_threshold_spin.value(),
            region_bias=patch_adjustment,
            scale_preset=self.scale_preset_spin.value(),
            adaptive_weighting=self.adaptive_weighting_check.isChecked(),
            detail_scale=self.detail_scale_spin.value(),
            background_mode=BackgroundMode(str(self.background_combo.currentData())),
            confidence_cleanup=self.confidence_cleanup_check.isChecked(),
            alignment_mode=alignment,
            reverse_order=False,
            preview_scale=1.0,
            skip_final_depth_buffer=(
                self._debug_options_enabled and self.skip_final_depth_buffer_check.isChecked()
            ),
            debug_save_stages=(
                self._debug_options_enabled and self.debug_save_stages_check.isChecked()
            ),
            use_cuda=self.cuda_check.isChecked(),
            gpu_memory_limit_mb=self.gpu_limit_spin.value() * 1024,
        )

    def _restore_parameter_defaults(self) -> None:
        defaults = settings_json(STACK_DEFAULTS_KEY, {})
        if not isinstance(defaults, dict):
            return
        self._set_combo_value(self.method_combo, defaults.get("stacking_method"))
        self._set_combo_value(self.metric_combo, defaults.get("focus_metric"))
        patch_adjustment = defaults.get("patch_adjustment", defaults.get("region_bias", 0))
        self.patch_size_spin.setValue(int(patch_adjustment))
        self.smoothing_spin.setValue(
            float(defaults.get("smoothing_sigma", self.smoothing_spin.value()))
        )
        self.noise_suppression_spin.setValue(
            float(defaults.get("halo_suppression_sigma", self.noise_suppression_spin.value()))
        )
        self.score_threshold_spin.setValue(
            int(defaults.get("score_threshold", self.score_threshold_spin.value()))
        )
        self.scale_preset_spin.setValue(
            int(defaults.get("scale_preset", self.scale_preset_spin.value()))
        )
        self._set_combo_value(self.background_combo, defaults.get("background_mode"))
        self.confidence_cleanup_check.setChecked(
            bool(defaults.get("confidence_cleanup", self.confidence_cleanup_check.isChecked()))
        )
        self.adaptive_weighting_check.setChecked(
            bool(defaults.get("adaptive_weighting", self.adaptive_weighting_check.isChecked()))
        )
        self.detail_scale_spin.setValue(
            int(defaults.get("detail_scale", self.detail_scale_spin.value()))
        )
        self.skip_final_depth_buffer_check.setChecked(
            bool(defaults.get("skip_final_depth_buffer", False))
        )
        self.debug_save_stages_check.setChecked(bool(defaults.get("debug_save_stages", False)))
        alignment_mode = str(defaults.get("alignment_mode", AlignmentMode.TRANSLATION.value))
        self.align_check.setChecked(alignment_mode == AlignmentMode.TRANSLATION.value)
        self.cuda_check.setChecked(bool(defaults.get("use_cuda", self.cuda_check.isChecked())))
        self.gpu_limit_spin.setValue(
            max(2, int(defaults.get("gpu_memory_limit_mb", self.gpu_limit_spin.value() * 1024)) // 1024)
        )
        self._refresh_cuda_tooltip()
        self._method_changed(self.method_combo.currentIndex())

    def _refresh_cuda_tooltip(self) -> None:
        status = gpu_backend_status()
        if status.get("available"):
            assets = self._current_stack_assets() if hasattr(self, "thumbnails") else []
            memory_text = ""
            if assets:
                try:
                    shapes = [
                        (asset.height, asset.width, 3)
                        if asset.color_model in {"rgb", "rgba"}
                        else (asset.height, asset.width)
                        for asset in assets
                    ]
                    plan = plan_gpu_memory_from_shapes(
                        shapes,
                        multiplier=5.5,
                        memory_limit_mb=self.gpu_limit_spin.value() * 1024,
                    )
                    mode = "full-frame GPU" if plan.full_frame_possible else "CPU fallback likely"
                    memory_text = (
                        f" Estimated stack memory: {plan.required_memory_mb} MB; "
                        f"free GPU memory: {plan.free_memory_mb} MB; {mode}."
                    )
                except (ValueError, MemoryError):
                    memory_text = ""
            method_text = ""
            if str(self.method_combo.currentData()) == StackingMethod.CUSTOM.value:
                method_text = (
                    " Custom currently uses only partial CUDA acceleration; "
                    "Depth Map and Pyramid Max Contrast are the GPU-first methods."
                )
            elif str(self.method_combo.currentData()) == StackingMethod.CUSTOM2.value:
                method_text = (
                    " Custom2 uses the GPU-enabled PMax detail stage when available, "
                    "but its Custom base stage remains mostly CPU."
                )
            self.cuda_check.setToolTip(
                f"CUDA GPU backend available: {status.get('device_name', 'CUDA device')}."
                f"{memory_text}{method_text}"
            )
            return
        self.cuda_check.setToolTip(
            "CUDA GPU backend is not available in this Python environment. "
            f"Reason: {status.get('reason', 'unknown')}. CPU fallback will be used."
        )

    def _save_parameter_defaults(self, parameters: FocusStackParameters) -> None:
        data = parameters.to_dict()
        data["patch_adjustment"] = self.patch_size_spin.value()
        set_settings_json(STACK_DEFAULTS_KEY, data)

    def _set_combo_value(self, combo: QComboBox, value: object) -> None:
        if value is None:
            return
        index = combo.findData(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _current_stack_assets(self) -> list[ImageAsset]:
        stack = (
            self.project.stacks.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        if stack is None:
            return []
        return [
            self.project.assets[asset_id]
            for asset_id in stack.asset_ids
            if asset_id in set(stack.enabled_asset_ids or []) and asset_id in self.project.assets
        ]

    def _refresh_stack_entries(self) -> None:
        """Show source images plus comparison table/generated results when available."""
        assets = self._current_stack_assets()
        summary = (
            self._comparison_summaries.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        generated = (
            self._comparison_assets.get(self._current_stack_id, [])
            if self._current_stack_id is not None
            else []
        )
        if summary is None:
            self.thumbnails.set_assets(assets)
            return
        self.thumbnails.clear()
        table_item = QListWidgetItem("Comparison Results")
        table_item.setData(256, "__comparison_table__")
        table_item.setData(257, "comparison_table")
        self.thumbnails.addItem(table_item)
        for asset in assets:
            item = QListWidgetItem(asset.filename)
            item.setData(256, asset.id)
            item.setData(257, "source")
            item.setToolTip(f"{asset.filename}\n{asset.width} x {asset.height}, {asset.dtype}")
            self.thumbnails.addItem(item)
        for asset in sorted(
            generated,
            key=lambda item: int(item.metadata.get("sharpness_rank", 9999)),
        ):
            rank = int(asset.metadata.get("sharpness_rank", 0))
            prefix = f"[#{rank}] " if rank else ""
            item = QListWidgetItem(f"{prefix}Result - {asset.display_name}")
            item.setData(256, asset.id)
            item.setData(257, "generated_result")
            item.setToolTip(str(asset.path))
            self.thumbnails.addItem(item)

    def _select_stack_entry_item(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        self._last_stack_selection_target = "source"
        entry_type = str(current.data(257) or "")
        entry_id = str(current.data(256))
        if entry_type == "comparison_table":
            self._selected_result_pixels = None
            self._show_comparison_table()
            return
        asset = self.project.assets.get(entry_id)
        if asset is None:
            return
        if entry_type == "generated_result":
            loaded = read_image_asset(Path(asset.path), load_pixels=True)
            self._selected_result_pixels = loaded.pixels
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self.result_canvas.set_pixels(loaded.pixels, asset.display_name)
            return
        self._selected_result_pixels = None
        self.result_view_stack.setCurrentWidget(self.result_canvas)

    def _show_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 100))
        self.progress.setFormat(f"{message} %p%")

    def _show_stack_preview(self, pixels: object, label: str) -> None:
        if not isinstance(pixels, np.ndarray):
            return
        if self._running_stack_id != self._current_stack_id:
            return
        if label.lower().startswith("stacking frame"):
            self._last_stack_progress_preview = (
                self._running_stack_id,
                np.asarray(pixels).copy(),
                label,
            )
        self.result_canvas.set_pixels(pixels, label, fit=self.result_canvas.visible_image_rect() is None)

    def _stack_finished(self, result: object) -> None:
        stack_result = result
        if not isinstance(stack_result, FocusStackResult):
            self._stack_failed("Unexpected stack result type.")
            return
        stack_id = self._running_stack_id
        if stack_id is None or stack_id not in self.project.stacks:
            self._stack_failed("Stack no longer exists.")
            return
        if self._running_preview:
            if self._current_stack_id == stack_id:
                self.result_canvas.set_pixels(stack_result.image, "Low-resolution stack preview")
            return
        self._last_stack_result = stack_result.image
        self._stack_results[stack_id] = stack_result.image
        if self._current_stack_id == stack_id:
            preview = self._last_stack_progress_preview
            if (
                stack_result.parameters.skip_final_depth_buffer
                and preview is not None
                and preview[0] == stack_id
            ):
                self._stack_display_overrides[stack_id] = (preview[1], preview[2])
                self.result_canvas.set_pixels(preview[1], preview[2])
            else:
                self._stack_display_overrides.pop(stack_id, None)
                self.result_canvas.set_pixels(stack_result.image, "Focus-stacked result")
        source_node_ids = [
            node_id
            for asset in self._stack_assets(stack_id)
            if (node_id := self.project.source_node_id_for_asset(asset.id)) is not None
        ]
        node = ProcessingNode(
            operation="focus_stack",
            inputs=tuple(source_node_ids),
            parameters=stack_result.parameters.to_dict(),
            provenance={
                "transforms": [transform.to_dict() for transform in stack_result.transforms],
                "reference": (
                    "Independent BioPic LM implementation; behavior verified by BioPic regression tests."
                ),
            },
        )
        self.project.graph.add_node(node)
        self._register_stack_result_asset(stack_result, node, stack_id)
        self.project.touch()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _comparison_finished(self, result: object) -> None:
        if not isinstance(result, SharpnessComparisonSummary):
            self._stack_failed("Unexpected sharpness comparison result type.")
            return
        stack_id = self._running_stack_id or self._current_stack_id
        if stack_id is None or stack_id not in self.project.stacks:
            self._stack_failed("Stack no longer exists.")
            return
        self._comparison_summaries[stack_id] = result
        generated: list[ImageAsset] = []
        for comparison_result in result.results:
            read_result = read_image_asset(comparison_result.temporary_path, load_pixels=False)
            asset = read_result.asset
            asset.kind = ImageAssetKind.STACK_RESULT
            asset.display_name = comparison_result.method_name
            asset.metadata.update(
                {
                    "source_stack_id": stack_id,
                    "sharpness_comparison": True,
                    "sharpness_result_id": comparison_result.result_id,
                    "sharpness_rank": comparison_result.rank,
                    "combined_score": comparison_result.combined_score,
                    "raw_scores": comparison_result.raw_scores,
                    "normalized_scores": comparison_result.normalized_scores,
                    "temporary": True,
                }
            )
            self.project.add_asset(asset)
            generated.append(asset)
        self._comparison_assets[stack_id] = generated
        self._refresh_stack_entries()
        self._populate_comparison_table(result)
        if generated:
            best = min(generated, key=lambda asset: int(asset.metadata.get("sharpness_rank", 9999)))
            self._select_asset_in_strip(best.id)
        self.project.touch()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _populate_comparison_table(self, summary: SharpnessComparisonSummary) -> None:
        metric_ids = sorted({metric for result in summary.results for metric in result.raw_scores})
        headers = ["Rank", "Method", "Preset"]
        headers.extend(sharpness_metric_display_name(metric) for metric in metric_ids)
        headers.extend(["Combined score", "Runtime", "Temporary filename"])
        self.result_table.setSortingEnabled(False)
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(summary.results))
        ordered_results = sorted(summary.results, key=lambda item: item.rank)
        best_combined_id = ordered_results[0].result_id if ordered_results else ""
        best_by_metric = {
            metric: max(
                ordered_results,
                key=lambda item, metric_id=metric: item.raw_scores.get(metric_id, float("-inf")),
            ).result_id
            for metric in metric_ids
            if ordered_results
        }
        for row, comparison_result in enumerate(ordered_results):
            values: list[object] = [
                comparison_result.rank,
                comparison_result.method_name,
                summary.preset_name,
            ]
            values.extend(comparison_result.raw_scores.get(metric, 0.0) for metric in metric_ids)
            values.extend(
                [
                    comparison_result.combined_score,
                    comparison_result.runtime_seconds,
                    comparison_result.temporary_path.name,
                ]
            )
            for column, value in enumerate(values):
                text = f"{value:.6g}" if isinstance(value, float) else str(value)
                item = QTableWidgetItem(text)
                item.setData(256, comparison_result.result_id)
                if isinstance(value, (int, float)):
                    item.setData(Qt.ItemDataRole.EditRole, value)
                if comparison_result.result_id == best_combined_id:
                    item.setBackground(QBrush(QColor("#e7f4ff")))
                if 3 <= column < 3 + len(metric_ids):
                    metric_id = metric_ids[column - 3]
                    if best_by_metric.get(metric_id) == comparison_result.result_id:
                        item.setBackground(QBrush(QColor("#edf8e9")))
                self.result_table.setItem(row, column, item)
        self.result_table.setSortingEnabled(True)
        if "Combined score" in headers:
            self.result_table.sortItems(
                headers.index("Combined score"),
                Qt.SortOrder.DescendingOrder,
            )
        self.result_summary_label.setText(self._comparison_summary_text(summary))

    def _show_comparison_table(self) -> None:
        summary = (
            self._comparison_summaries.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        if summary is not None:
            self._populate_comparison_table(summary)
        self.result_view_stack.setCurrentWidget(self.result_table_panel)

    def _select_comparison_result_row(self, row: int, _column: int) -> None:
        item = self.result_table.item(row, 0)
        if item is None or self._current_stack_id is None:
            return
        result_id = str(item.data(256))
        for asset in self._comparison_assets.get(self._current_stack_id, []):
            if asset.metadata.get("sharpness_result_id") == result_id:
                self._select_asset_in_strip(asset.id)
                self.result_table.selectRow(row)
                return

    def _comparison_summary_text(self, summary: SharpnessComparisonSummary) -> str:
        best = min(summary.results, key=lambda item: item.rank) if summary.results else None
        best_text = best.method_name if best is not None else "None"
        shape = " x ".join(str(part) for part in summary.image_shape)
        return (
            f"Source stack: {summary.stack_name} | "
            f"Frames: {summary.source_count} | "
            f"Shape: {shape} | "
            f"Bit depth: {summary.dtype} | "
            f"Analysis region: {summary.analysis_region} | "
            f"Preset: {summary.preset_name} | "
            f"Generated methods: {len(summary.results)} | "
            f"Best combined result: {best_text} | "
            f"Temporary result directory: {summary.temporary_dir}"
        )

    def _select_asset_in_strip(self, asset_id: str) -> None:
        for row in range(self.thumbnails.count()):
            item = self.thumbnails.item(row)
            if str(item.data(256)) == asset_id:
                self.thumbnails.setCurrentRow(row)
                return

    def _stack_failed(self, message: str) -> None:
        self.progress.setFormat(message)

    def _worker_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None
        self._comparison_worker = None
        self._running_stack_id = None
        self._running_preview = False
        self._update_comparison_button_enabled()

