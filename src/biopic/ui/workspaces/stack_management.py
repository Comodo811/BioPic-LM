"""Stack workspace management, persistence, and selection helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem, QProgressDialog

from biopic.export.raster import export_image
from biopic.imaging.io import SUPPORTED_EXTENSIONS, file_checksum, import_images, read_image_asset
from biopic.imaging.stacking import FocusStackResult
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack
from biopic.pipeline.node import ProcessingNode
from biopic.ui.previews import asset_preview_pixels
from biopic.ui.settings import remembered_open_files
from biopic.ui.stack_import_resolution import resolve_stack_import_paths
from biopic.ui.workspace_helpers.common import stack_result_metadata


class StackManagementMixin:
    """Save, mutate, select, and register stack records."""

    def save_last_result(self, path: str) -> bool:
        """Save the most recent focus-stacked result."""
        result = (
            self._stack_results.get(self._current_stack_id)
            if self._current_stack_id is not None
            else self._last_stack_result
        )
        if result is None:
            if self._selected_result_pixels is None:
                return False
            export_image(self._selected_result_pixels, Path(path))
            return True
        if self.result_view_stack.currentWidget() is self.result_table_panel:
            return False
        if self._selected_result_pixels is not None:
            export_image(self._selected_result_pixels, Path(path))
            return True
        export_image(result, Path(path))
        return True

    def reverse_current_stack(self) -> None:
        """Reverse the selected stack order."""
        stack = self._current_stack()
        if stack is None:
            return
        self._push_undo_state()
        stack.asset_ids.reverse()
        if stack.enabled_asset_ids is not None:
            stack.enabled_asset_ids.reverse()
        self._invalidate_stack_result(stack.id)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def add_images_to_current_stack(self) -> None:
        """Import additional images and append them to the selected stack."""
        stack = self._current_stack()
        if stack is None:
            return
        filters = "Images (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)) + ")"
        filenames = remembered_open_files(self, "Add Images to Stack", "stack_append", filters)
        if not filenames:
            return
        paths = resolve_stack_import_paths(self, [Path(filename) for filename in filenames])
        if not paths:
            return
        existing_asset_ids = set(self.project.assets)
        existing_node_ids = set(self.project.graph.nodes)
        progress = QProgressDialog("Loading images...", "Cancel", 0, len(paths), self)
        progress.setWindowTitle("Add Images to Stack")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()

        def update_progress(done: int, total: int, path: Path) -> None:
            progress.setMaximum(total)
            progress.setLabelText(f"Loading {path.name} ({done}/{total})")
            progress.setValue(done)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise InterruptedError("Add images canceled")

        try:
            assets = import_images(
                self.project,
                paths,
                kind=ImageAssetKind.STACK_SOURCE,
                progress=update_progress,
            )
        except InterruptedError:
            progress.close()
            self._discard_partial_import(existing_asset_ids, existing_node_ids)
            self.progress.setFormat("Add images canceled")
            return
        except (OSError, ValueError) as exc:
            progress.close()
            self._discard_partial_import(existing_asset_ids, existing_node_ids)
            self.progress.setFormat(str(exc))
            return
        progress.close()
        new_asset_ids = [asset.id for asset in assets]
        stack.asset_ids.extend(new_asset_ids)
        if stack.enabled_asset_ids is None:
            stack.enabled_asset_ids = list(stack.asset_ids)
        else:
            stack.enabled_asset_ids.extend(new_asset_ids)
        self._invalidate_stack_result(stack.id)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _discard_partial_import(
        self,
        existing_asset_ids: set[str],
        existing_node_ids: set[str],
    ) -> None:
        for asset_id in set(self.project.assets) - existing_asset_ids:
            self.project.assets.pop(asset_id, None)
        for node_id in set(self.project.graph.nodes) - existing_node_ids:
            self.project.graph.nodes.pop(node_id, None)

    def remove_selected_image(self) -> None:
        """Remove the selected source image(s) from the current stack."""
        stack = self._current_stack()
        if stack is None:
            return
        selected = [
            item
            for item in self.thumbnails.selectedItems()
            if str(item.data(257) or "source") == "source"
        ]
        if not selected and self.thumbnails.currentItem() is not None:
            current = self.thumbnails.currentItem()
            if str(current.data(257) or "source") == "source":
                selected = [current]
        asset_ids = {str(item.data(256)) for item in selected}
        if not asset_ids:
            return
        self._push_undo_state()
        stack.asset_ids = [item for item in stack.asset_ids if item not in asset_ids]
        stack.enabled_asset_ids = [
            item for item in (stack.enabled_asset_ids or []) if item not in asset_ids
        ]
        self._invalidate_stack_result(stack.id)
        if not stack.asset_ids:
            self._delete_stack(stack.id)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def delete_selected_stack(self) -> None:
        """Delete the currently selected stack."""
        stack = self._current_stack()
        if stack is None:
            return
        self._push_undo_state()
        self._delete_stack(stack.id, remove_sources=True)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def undo(self) -> None:
        """Undo the latest stack workspace operation."""
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot_state())
        self._restore_state(self._undo_stack.pop())

    def redo(self) -> None:
        """Redo the latest undone stack workspace operation."""
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot_state())
        self._restore_state(self._redo_stack.pop())

    def _push_undo_state(self) -> None:
        self._undo_stack.append(self._snapshot_state())
        self._redo_stack.clear()

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "assets": deepcopy(self.project.assets),
            "stacks": deepcopy(self.project.stacks),
            "graph": deepcopy(self.project.graph),
            "calibrations": deepcopy(self.project.calibrations),
            "measurements": deepcopy(self.project.measurements),
            "scale_bars": deepcopy(self.project.scale_bars),
            "annotations": deepcopy(self.project.annotations),
            "stack_results": deepcopy(self._stack_results),
            "stack_display_overrides": deepcopy(self._stack_display_overrides),
            "comparison_summaries": deepcopy(self._comparison_summaries),
            "comparison_assets": deepcopy(self._comparison_assets),
            "current_stack_id": self._current_stack_id,
        }

    def _restore_state(self, state: dict[str, Any]) -> None:
        self.project.assets = deepcopy(state["assets"])
        self.project.stacks = deepcopy(state["stacks"])
        self.project.graph = deepcopy(state["graph"])
        self.project.calibrations = deepcopy(state["calibrations"])
        self.project.measurements = deepcopy(state["measurements"])
        self.project.scale_bars = deepcopy(state["scale_bars"])
        self.project.annotations = deepcopy(state["annotations"])
        self._stack_results = deepcopy(state["stack_results"])
        self._stack_display_overrides = deepcopy(state["stack_display_overrides"])
        self._comparison_summaries = deepcopy(state["comparison_summaries"])
        self._comparison_assets = deepcopy(state["comparison_assets"])
        self._current_stack_id = state["current_stack_id"]
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _select_stack_item(self, current: QListWidgetItem | None) -> None:
        self._last_stack_selection_target = "stack"
        self._current_stack_id = None if current is None else str(current.data(256))
        assets = self._current_stack_assets()
        self._refresh_stack_entries()
        self._update_comparison_button_enabled()
        if assets:
            self._set_source_preview_asset(assets[0])
        else:
            self.source_canvas.set_asset(None)
        self._refresh_result_canvas()

    def _current_stack(self) -> ImageStack | None:
        if self._current_stack_id is None:
            return None
        return self.project.stacks.get(self._current_stack_id)

    def _set_source_preview_asset(self, asset: ImageAsset) -> None:
        stack_module = sys.modules.get("biopic.ui.workspaces.stack")
        preview_loader = (
            getattr(stack_module, "asset_preview_pixels", asset_preview_pixels)
            if stack_module is not None
            else asset_preview_pixels
        )
        try:
            preview = preview_loader(asset)
        except (OSError, ValueError):
            self.source_canvas.set_asset(asset)
            return
        self.source_canvas.set_pixels(preview, f"{asset.filename} (preview)")

    def _stack_assets(self, stack_id: str) -> list[ImageAsset]:
        stack = self.project.stacks.get(stack_id)
        if stack is None:
            return []
        enabled = set(stack.enabled_asset_ids or [])
        return [
            self.project.assets[asset_id]
            for asset_id in stack.asset_ids
            if asset_id in enabled and asset_id in self.project.assets
        ]

    def _refresh_result_canvas(self) -> None:
        if self._current_stack_id is None:
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = None
            self.result_canvas.set_asset(None)
            return
        result = self._stack_results.get(self._current_stack_id)
        if result is not None:
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = result
            override = self._stack_display_overrides.get(self._current_stack_id)
            if override is not None:
                self.result_canvas.set_pixels(override[0], override[1])
            else:
                self.result_canvas.set_pixels(result, "Focus-stacked result")
            return
        asset = self._stack_result_asset(self._current_stack_id)
        if asset is not None:
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = None
            self.result_canvas.set_asset(asset)
            return
        self.result_view_stack.setCurrentWidget(self.result_canvas)
        self._selected_result_pixels = None
        self.result_canvas.set_asset(None)

    def _stack_result_asset(self, stack_id: str) -> ImageAsset | None:
        return next(
            (
                asset
                for asset in self.project.assets.values()
                if asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
                and not asset.metadata.get("stale")
            ),
            None,
        )

    def _invalidate_stack_result(self, stack_id: str) -> None:
        self._stack_results.pop(stack_id, None)
        self._stack_display_overrides.pop(stack_id, None)
        self._remove_comparison_outputs(stack_id)
        for asset in self.project.assets.values():
            if (
                asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
            ):
                asset.metadata["stale"] = True
        if self._current_stack_id == stack_id:
            self.result_canvas.set_asset(None)

    def _remove_empty_stacks(self) -> None:
        """Drop stale empty stack records before drawing the stack list."""
        empty_stack_ids = [
            stack_id
            for stack_id, stack in self.project.stacks.items()
            if not stack.asset_ids
        ]
        for stack_id in empty_stack_ids:
            self._delete_stack(stack_id)

    def _delete_stack(self, stack_id: str, *, remove_sources: bool = False) -> None:
        """Delete a stack record and any derived cached result records."""
        stack = self.project.stacks.get(stack_id)
        stack_asset_ids = list(stack.asset_ids) if stack is not None else []
        self._stack_results.pop(stack_id, None)
        self._stack_display_overrides.pop(stack_id, None)
        self._remove_comparison_outputs(stack_id)
        self.project.stacks.pop(stack_id, None)
        if remove_sources:
            self._remove_unshared_stack_source_assets(stack_asset_ids)
        stale_result_ids = [
            asset.id
            for asset in self.project.assets.values()
            if (
                asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
            )
        ]
        for asset_id in stale_result_ids:
            self.project.assets.pop(asset_id, None)
        if self._current_stack_id == stack_id:
            self._current_stack_id = None
            self.source_canvas.set_asset(None)
            self.result_canvas.set_asset(None)

    def _remove_unshared_stack_source_assets(self, asset_ids: list[str]) -> None:
        remaining_stack_asset_ids = {
            asset_id
            for stack in self.project.stacks.values()
            for asset_id in stack.asset_ids
        }
        for asset_id in asset_ids:
            if asset_id in remaining_stack_asset_ids:
                continue
            asset = self.project.assets.get(asset_id)
            if asset is None or asset.kind is not ImageAssetKind.STACK_SOURCE:
                continue
            node_id = self.project.source_node_id_for_asset(asset_id)
            if node_id is not None:
                self.project.graph.nodes.pop(node_id, None)
                self.project.calibrations.pop(node_id, None)
                self.project.measurements = {
                    measurement_id: measurement
                    for measurement_id, measurement in self.project.measurements.items()
                    if measurement.image_node_id != node_id
                }
                self.project.scale_bars = {
                    scale_bar_id: scale_bar
                    for scale_bar_id, scale_bar in self.project.scale_bars.items()
                    if scale_bar.image_node_id != node_id
                }
                self.project.annotations = {
                    annotation_id: annotation
                    for annotation_id, annotation in self.project.annotations.items()
                    if annotation.image_node_id != node_id
                }
            self.project.assets.pop(asset_id, None)

    def _remove_comparison_outputs(self, stack_id: str) -> None:
        self._comparison_summaries.pop(stack_id, None)
        for asset in self._comparison_assets.pop(stack_id, []):
            try:
                Path(asset.path).unlink(missing_ok=True)
            except OSError:
                pass
            self.project.assets.pop(asset.id, None)

    def _update_comparison_button_enabled(self) -> None:
        idle = self._worker is None and self._comparison_worker is None
        self.comparison_button.setEnabled(idle and len(self._current_stack_assets()) >= 2)

    def _register_stack_result_asset(
        self, result: FocusStackResult, node: ProcessingNode, stack_id: str | None = None
    ) -> None:
        stack = (
            self.project.stacks.get(stack_id)
            if stack_id is not None
            else self._current_stack()
        )
        if stack is None:
            return
        cache_dir = (Path.cwd() / ".biopic_cache" / self.project.id / "stack_results").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{stack.id}_stacked.tif"
        export_image(result.image, path)
        read_result = read_image_asset(path, load_pixels=False)
        existing = next(
            (
                asset
                for asset in self.project.assets.values()
                if asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack.id
            ),
            None,
        )
        if existing is None:
            asset = read_result.asset
            asset.kind = ImageAssetKind.STACK_RESULT
            asset.display_name = f"{stack.name} - stacked result"
            asset.origin_node_id = node.id
            asset.metadata.update(stack_result_metadata(stack, node, result))
            asset.metadata.pop("stale", None)
            self.project.add_asset(asset)
            return
        existing.path = str(path)
        existing.checksum = file_checksum(path)
        existing.width = read_result.asset.width
        existing.height = read_result.asset.height
        existing.frames = read_result.asset.frames
        existing.dtype = read_result.asset.dtype
        existing.color_model = read_result.asset.color_model
        existing.display_name = f"{stack.name} - stacked result"
        existing.origin_node_id = node.id
        existing.metadata.update(stack_result_metadata(stack, node, result))
        existing.metadata.pop("stale", None)

