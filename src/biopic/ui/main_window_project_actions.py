"""Project, import, export, and refresh actions for MainWindow."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QProgressDialog

from biopic.app.branding import WINDOW_TITLE_PREFIX
from biopic.export import export_project_figure_board, export_project_image
from biopic.imaging.io import SUPPORTED_EXTENSIONS, import_images, import_stack
from biopic.imaging.layer_buffers import (
    layer_alpha_buffer,
    layer_content_buffer,
    set_layer_buffers,
    sync_layer_buffers_to_payload,
)
from biopic.imaging.project_render import asset_for_source_node
from biopic.models.editing import AdjustmentLayer, EditLayer, RetouchStroke, SelectionMask
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.ui.settings import remembered_open_file, remembered_open_files, remembered_save_file
from biopic.ui.main_window_save_options import ProjectSaveOptionsDialog, save_project_save_options
from biopic.ui.stack_import_resolution import resolve_stack_import_paths
from biopic.ui.workspace_helpers.common import stack_display_name

LOGGER = logging.getLogger(__name__)

WORKSPACE_OVERVIEW = 0
WORKSPACE_STACK_FROM_VIDEO = 1
WORKSPACE_STACK = 2
WORKSPACE_STITCH_IMAGES = 3
WORKSPACE_METADATA = 4
WORKSPACE_EDIT_IMAGE = 5
WORKSPACE_MEASURE_SCALE = 6
WORKSPACE_ANNOTATE = 7
WORKSPACE_FIGURE_BOARD = 8
WORKSPACE_IMPORT = 9
WORKSPACE_EXPORT = 10


class MainWindowProjectActionsMixin:
    """Project lifecycle, image import, export, and workspace refresh actions."""

    def new_project(self) -> None:
        """Create a new empty project."""
        if not self._confirm_discard_unsaved_changes("create a new project"):
            return
        name, accepted = QInputDialog.getText(self, "New Project", "Project name:")
        if not accepted:
            return
        self.project = Project.new(name or "Untitled Project")
        self.project_path = None
        self._has_unsaved_changes = True
        self._bind_project_to_workspaces()
        self.refresh_project_views()

    def rename_project(self) -> None:
        """Rename the active project and mark the manifest dirty."""
        current_name = self.project.name.strip() or "Untitled Project"
        name, accepted = QInputDialog.getText(
            self,
            "Rename Project",
            "Project name:",
            text=current_name,
        )
        if not accepted:
            return
        name = name.strip() or "Untitled Project"
        if name == self.project.name:
            return
        self.project.name = name
        self.project.touch()
        self._has_unsaved_changes = True
        self._update_project_title()
        self.refresh_project_views()
        self.statusBar().showMessage(f"Renamed project to '{name}'")

    def import_video(self) -> None:
        """Open the video import workflow from the File menu."""
        self._select_workspace(WORKSPACE_STACK_FROM_VIDEO)
        self.stack_from_video_workspace.open_video()

    def open_project(self) -> None:
        """Open a saved BioPic LM project."""
        if not self._confirm_discard_unsaved_changes("open another project"):
            return
        filename = remembered_open_file(
            self,
            "Open Project",
            "project_open",
            "BioPic Self-Contained Project (*.biopic.json);;JSON (*.json)",
        )
        if not filename:
            return
        try:
            self.project = self.store.load(Path(filename))
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Open Project Failed", str(exc))
            return
        self.project_path = Path(filename)
        self._has_unsaved_changes = False
        self._bind_project_to_workspaces()
        self._update_project_title()
        self.refresh_project_views()
        self.statusBar().showMessage(f"Opened {filename}")

    def save_project(self) -> bool:
        """Save to the current project path or prompt for one."""
        if self.project_path is None:
            return self.save_project_as()
        if not self._has_unsaved_changes and self.project_path.exists():
            self.statusBar().showMessage(f"No changes to save: {self.project_path}")
            return True
        self._save_progress_token += 1
        save_progress_token = self._save_progress_token
        self._set_save_progress(0, 1, self.project_path, "Preparing save")
        QApplication.processEvents()

        def update_progress(done: int, total: int, path: Path, action: str) -> None:
            self._set_save_progress(done, total, path, action)
            QApplication.processEvents()

        try:
            self.edit_workspace._flush_pending_selection_persistence()
            self.store.save(
                self.project,
                self.project_path,
                save_options=self.project_save_options,
                progress=update_progress,
            )
        except OSError as exc:
            self._hide_save_progress()
            QMessageBox.critical(self, "Save Project Failed", str(exc))
            return False
        self._has_unsaved_changes = False
        self.refresh_project_views()
        self.statusBar().showMessage(f"Saved {self.project_path}")
        QTimer.singleShot(
            2000,
            lambda token=save_progress_token: self._hide_save_progress_if_current(token),
        )
        return True

    def save_project_as(self) -> bool:
        """Prompt and save the current project."""
        filename = remembered_save_file(
            self,
            "Save Project As",
            "project_save",
            "BioPic Self-Contained Project (*.biopic.json)",
            f"{self.project.name}.biopic.json",
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix != ".json":
            path = path.with_suffix(".biopic.json")
        self.project_path = path
        return self.save_project()

    def open_save_options_dialog(self) -> None:
        """Open project save behavior options."""
        dialog = ProjectSaveOptionsDialog(self.project_save_options, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.project_save_options = dialog.options()
        save_project_save_options(self.project_save_options)
        self.statusBar().showMessage("Project save options updated")

    def import_image(self) -> None:
        """Import one or more independent images."""
        paths = self._select_image_paths("Import Image")
        if not paths:
            return
        switch_to_overview = self._project_is_empty()
        try:
            assets = import_images(self.project, paths)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return
        self._has_unsaved_changes = True
        self.refresh_project_views()
        if switch_to_overview:
            self._select_workspace(WORKSPACE_OVERVIEW)
        self.statusBar().showMessage(f"Imported {len(assets)} image(s)")

    def import_image_stack(self) -> None:
        """Import selected files as an ordered focal stack."""
        paths = self._select_image_paths("Import Image Stack")
        if not paths:
            return
        paths = resolve_stack_import_paths(self, paths)
        if not paths:
            return
        switch_to_stack = self._project_is_empty()
        progress = QProgressDialog("Loading image stack...", "Cancel", 0, len(paths), self)
        progress.setWindowTitle("Import Image Stack")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()
        existing_asset_ids = set(self.project.assets)
        existing_node_ids = set(self.project.graph.nodes)

        def update_progress(done: int, total: int, path: Path) -> None:
            progress.setMaximum(total)
            progress.setLabelText(f"Loading {path.name} ({done}/{total})")
            progress.setValue(done)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise InterruptedError("Image stack import canceled")

        try:
            stack = import_stack(
                self.project,
                paths,
                StackKind.FOCAL,
                progress=update_progress,
            )
        except InterruptedError:
            progress.close()
            self._discard_partial_import(existing_asset_ids, existing_node_ids)
            self.statusBar().showMessage("Image stack import canceled")
            return
        except (OSError, ValueError) as exc:
            progress.close()
            self._discard_partial_import(existing_asset_ids, existing_node_ids)
            QMessageBox.critical(self, "Import Stack Failed", str(exc))
            return
        progress.close()
        self._has_unsaved_changes = True
        self.refresh_project_views()
        if switch_to_stack:
            self._select_workspace(WORKSPACE_STACK)
        self.statusBar().showMessage(f"Imported stack '{stack.name}' with {len(paths)} frame(s)")

    def copy_current_context(self) -> None:
        """Copy pixels in Edit Image, or copy the selected project image elsewhere."""
        if self._workspace.currentWidget() is self.edit_workspace:
            self.edit_workspace.copy_selection()
            return
        self.copy_current_project_image()

    def paste_current_context(self) -> None:
        """Paste pixels in Edit Image, or paste the copied project image elsewhere."""
        if (
            self._workspace.currentWidget() is self.edit_workspace
            and self.edit_workspace._clipboard_pixels is not None
        ):
            self.edit_workspace.paste_as_layer()
            return
        self.paste_copied_project_image()

    def copy_current_project_image(self) -> None:
        """Copy the currently selected rendered project image for duplication."""
        node_id = self._current_project_image_source_node_id()
        if node_id is None:
            self.statusBar().showMessage("No image is selected to copy.")
            return
        asset = asset_for_source_node(self.project, node_id)
        if asset is None:
            self.statusBar().showMessage("No image is selected to copy.")
            return
        self._copied_project_image_node_id = node_id
        self._copied_project_image_asset_id = asset.id
        self.statusBar().showMessage(f"Copied image '{asset.filename}'")

    def paste_copied_project_image(self) -> None:
        """Paste the copied image as a new source with independent editable state."""
        node_id = getattr(self, "_copied_project_image_node_id", None)
        asset_id = getattr(self, "_copied_project_image_asset_id", None)
        if node_id is None or asset_id is None:
            self.statusBar().showMessage("No copied image is available to paste.")
            return
        source = self.project.assets.get(asset_id)
        if source is None:
            self.statusBar().showMessage("The copied image is no longer available.")
            return
        asset = ImageAsset(
            path=source.path,
            kind=ImageAssetKind.EDIT_DERIVATIVE,
            checksum=source.checksum,
            width=source.width,
            height=source.height,
            frames=source.frames,
            dtype=source.dtype,
            color_model=source.color_model,
            origin_node_id=node_id,
            metadata=deepcopy(source.metadata),
        )
        asset.display_name = self._copied_image_display_name(source.filename)
        asset.metadata["copied_from_asset_id"] = source.id
        asset.metadata["copied_from_node_id"] = node_id
        self.project.add_asset(asset)
        new_node_id = self.project.source_node_id_for_asset(asset.id)
        if new_node_id is not None:
            self._copy_project_image_edit_state(node_id, new_node_id)
        self._has_unsaved_changes = True
        self.refresh_project_views()
        self._select_project_asset_in_active_workspace(asset.id)
        self.statusBar().showMessage(f"Pasted image '{asset.display_name}'")

    def _copy_project_image_edit_state(self, source_node_id: str, target_node_id: str) -> None:
        """Clone editable project records so the copied image can diverge independently."""
        if source_node_id in self.project.calibrations:
            self.project.calibrations[target_node_id] = deepcopy(
                self.project.calibrations[source_node_id]
            )
        layer_id_map = self._copy_edit_layers(source_node_id, target_node_id)
        self._copy_adjustment_layers(source_node_id, target_node_id)
        self._copy_retouch_strokes(source_node_id, target_node_id, layer_id_map)
        self._copy_selection_masks(source_node_id, target_node_id)

    def _copy_edit_layers(self, source_node_id: str, target_node_id: str) -> dict[str, str]:
        layer_id_map: dict[str, str] = {}
        source_layers = [
            layer
            for layer in self.project.edit_layers.values()
            if layer.source_node_id == source_node_id
        ]
        for layer in source_layers:
            sync_layer_buffers_to_payload(layer)
            clone = EditLayer.from_dict(deepcopy(layer.to_dict()))
            old_id = clone.id
            clone.id = str(uuid4())
            clone.source_node_id = target_node_id
            clone.image_item_id = str(uuid4())
            clone.drawable_id = str(uuid4())
            clone.tile_store_id = str(uuid4())
            clone.graph_node_id = str(uuid4())
            clone.content = deepcopy(layer.content)
            clone.alpha = deepcopy(layer.alpha)
            clone.mask_content = deepcopy(layer.mask_content)
            self.project.edit_layers[clone.id] = clone
            layer_id_map[old_id] = clone.id
            content = layer_content_buffer(layer.id)
            alpha = layer_alpha_buffer(layer.id)
            if content is not None and alpha is not None:
                set_layer_buffers(clone.id, content.copy(), alpha.copy())
        for old_id, new_id in layer_id_map.items():
            clone = self.project.edit_layers[new_id]
            if clone.parent_id in layer_id_map:
                clone.parent_id = layer_id_map[str(clone.parent_id)]
            if self.project.active_edit_layers.get(source_node_id) == old_id:
                self.project.active_edit_layers[target_node_id] = new_id
        return layer_id_map

    def _copy_adjustment_layers(self, source_node_id: str, target_node_id: str) -> None:
        for layer in self.project.adjustment_layers_for_image(source_node_id):
            clone = AdjustmentLayer.from_dict(deepcopy(layer.to_dict()))
            clone.id = str(uuid4())
            clone.image_node_id = target_node_id
            clone.parameters = deepcopy(layer.parameters)
            clone.cache_key = None
            self.project.adjustment_layers[clone.id] = clone

    def _copy_retouch_strokes(
        self,
        source_node_id: str,
        target_node_id: str,
        layer_id_map: dict[str, str],
    ) -> None:
        for stroke in list(self.project.retouch_strokes.values()):
            if stroke.image_node_id != source_node_id:
                continue
            clone = RetouchStroke.from_dict(deepcopy(stroke.to_dict()))
            clone.id = str(uuid4())
            clone.image_node_id = target_node_id
            if clone.layer_id in layer_id_map:
                clone.layer_id = layer_id_map[str(clone.layer_id)]
            self.project.retouch_strokes[clone.id] = clone

    def _copy_selection_masks(self, source_node_id: str, target_node_id: str) -> None:
        for selection in list(self.project.selections.values()):
            if selection.source_node_id != source_node_id:
                continue
            clone = SelectionMask.from_dict(deepcopy(selection.to_dict()))
            clone.id = str(uuid4())
            clone.source_node_id = target_node_id
            clone.mask_node_id = str(uuid4())
            self.project.selections[clone.id] = clone

    def _current_project_image_source_node_id(self) -> str | None:
        """Return the source node represented by the active workspace selection."""
        active_widget = self._workspace.currentWidget()
        if active_widget is self.edit_workspace:
            return self.edit_workspace._current_source_node_id
        if active_widget is self.metadata_workspace:
            asset_id = getattr(self.metadata_workspace, "_current_asset_id", None)
            return self.project.source_node_id_for_asset(asset_id) if asset_id else None
        if active_widget is self.measure_workspace:
            asset_id = self.measure_workspace.current_asset_id()
            return self.project.source_node_id_for_asset(asset_id) if asset_id else None
        if active_widget is self.annotation_workspace:
            asset_id = self.annotation_workspace.current_asset_id()
            return self.project.source_node_id_for_asset(asset_id) if asset_id else None
        if active_widget is self.figure_board_workspace:
            node_id = self._figure_board_selected_source_node_id()
            if node_id is not None:
                return node_id
        return self._current_export_source_node_id()

    def _figure_board_selected_source_node_id(self) -> str | None:
        board = self.figure_board_workspace._current_board()
        panel_id = getattr(self.figure_board_workspace, "_selected_panel_id", None)
        if board is not None and panel_id is not None:
            panel = next((item for item in board.panels if item.id == panel_id), None)
            if panel is not None and panel.source_node_id is not None:
                return panel.source_node_id
        current = self.figure_board_workspace.image_strip.currentItem()
        if current is not None:
            asset_id = current.data(256)
            if asset_id is not None:
                return self.project.source_node_id_for_asset(str(asset_id))
        return None

    def _select_project_asset_in_active_workspace(self, asset_id: str) -> None:
        active_widget = self._workspace.currentWidget()
        if active_widget is self.edit_workspace:
            row = next(
                (
                    index
                    for index, asset in enumerate(self.edit_workspace._editable_assets)
                    if asset.id == asset_id
                ),
                -1,
            )
            if row >= 0:
                self.edit_workspace.asset_list.setCurrentRow(row)
            return
        select_asset_id = getattr(active_widget, "select_asset_id", None)
        if callable(select_asset_id):
            select_asset_id(asset_id)
            return
        if active_widget is self.figure_board_workspace:
            for row in range(self.figure_board_workspace.image_strip.count()):
                item = self.figure_board_workspace.image_strip.item(row)
                if item is not None and item.data(256) == asset_id:
                    self.figure_board_workspace.image_strip.setCurrentRow(row)
                    return

    def _copied_image_display_name(self, source_name: str) -> str:
        stem = Path(source_name).stem or "Image"
        extension = Path(source_name).suffix or ".tif"
        existing = {asset.filename for asset in self.project.assets.values()}
        index = 1
        while True:
            copy_suffix = "" if index == 1 else f" {index}"
            name = f"{stem} copy{copy_suffix}{extension}"
            if name not in existing:
                return name
            index += 1

    def _discard_partial_import(
        self,
        existing_asset_ids: set[str],
        existing_node_ids: set[str],
    ) -> None:
        for asset_id in set(self.project.assets) - existing_asset_ids:
            self.project.assets.pop(asset_id, None)
        for node_id in set(self.project.graph.nodes) - existing_node_ids:
            self.project.graph.nodes.pop(node_id, None)

    def refresh_project_views(self) -> None:
        """Refresh all views that mirror project state."""
        start = perf_counter()
        self._remove_empty_stacks()
        dirty_marker = "*" if self._has_unsaved_changes else ""
        self.setWindowTitle(f"{WINDOW_TITLE_PREFIX} - {self.project.name}{dirty_marker}")
        self.project_list.clear()
        stacked_asset_ids = {
            asset_id for stack in self.project.stacks.values() for asset_id in stack.asset_ids
        }
        source_assets = [
            asset
            for asset in self.project.assets.values()
            if asset.kind is not ImageAssetKind.STACK_SOURCE
            and asset.id not in stacked_asset_ids
        ]
        self.project_list.addItem(f"Sources ({len(source_assets)})")
        for asset in source_assets:
            self.project_list.addItem(f"  {asset.filename}")
        self.project_list.addItem(f"Stacks ({len(self.project.stacks)})")
        for stack in self.project.stacks.values():
            self.project_list.addItem(f"  {stack_display_name(stack, self.project.assets)}")
        self.project_list.addItem(f"Pipeline nodes ({len(self.project.graph.nodes)})")
        self.project_list.addItem(f"Measurements ({len(self.project.measurements)})")
        self.project_list.addItem(f"Scale bars ({len(self.project.scale_bars)})")
        self.project_list.addItem(f"Annotations ({len(self.project.annotations)})")
        self.project_list.addItem(f"Figure boards ({len(self.project.figure_boards)})")
        active_widget = self._workspace.currentWidget()
        if active_widget is self.overview_workspace:
            self.overview_workspace.refresh()
        elif active_widget is self.stack_from_video_workspace:
            self.stack_from_video_workspace.refresh()
        elif active_widget is self.import_workspace:
            self.import_workspace.refresh()
        elif active_widget is self.stack_workspace:
            self.stack_workspace.refresh()
        elif active_widget is self.stitch_images_workspace:
            self.stitch_images_workspace.refresh()
        elif active_widget is self.metadata_workspace:
            self.metadata_workspace.refresh()
        elif active_widget is self.edit_workspace:
            if getattr(self.edit_workspace, "_asset_filter_ids", None) is not None:
                self.edit_workspace.set_asset_filter(None)
                return
            self.edit_workspace.refresh()
        elif active_widget is self.measure_workspace:
            self.measure_workspace.refresh()
        elif active_widget is self.annotation_workspace:
            self.annotation_workspace.refresh()
        elif active_widget is self.figure_board_workspace:
            self.figure_board_workspace.refresh()
        elif active_widget is self.export_workspace:
            self.export_workspace.refresh()
        LOGGER.debug(
            "project views refreshed in %.3fs active=%s",
            perf_counter() - start,
            type(active_widget).__name__ if active_widget is not None else None,
        )
        self._update_empty_watermark()

    def _update_project_title(self) -> None:
        """Apply the current project name and dirty marker to the window title."""
        dirty_marker = "*" if self._has_unsaved_changes else ""
        self.setWindowTitle(f"{WINDOW_TITLE_PREFIX} - {self.project.name}{dirty_marker}")

    def _remove_empty_stacks(self) -> None:
        """Remove empty stack records and their derived stack-result assets."""
        empty_stack_ids = {
            stack_id
            for stack_id, stack in self.project.stacks.items()
            if not stack.asset_ids
        }
        if not empty_stack_ids:
            return
        for stack_id in empty_stack_ids:
            self.project.stacks.pop(stack_id, None)
        stale_result_ids = [
            asset.id
            for asset in self.project.assets.values()
            if (
                asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") in empty_stack_ids
            )
        ]
        for asset_id in stale_result_ids:
            self.project.assets.pop(asset_id, None)
        self.project.touch()
        self._has_unsaved_changes = True

    def save_stacked_image(self) -> None:
        """Save the current focus-stack result."""
        filename = remembered_save_file(
            self,
            "Save Stacked Image",
            "stacked_image_save",
            "TIFF (*.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;Bitmap (*.bmp)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".tif")
        try:
            saved = self.stack_workspace.save_last_result(str(path))
        except OSError as exc:
            QMessageBox.critical(self, "Save Stacked Image Failed", str(exc))
            return
        if not saved:
            self.statusBar().showMessage("No stacked result is available to save.")
            return
        self.statusBar().showMessage(f"Saved stacked image {path}")

    def export_current_image(self) -> None:
        """Export the currently selected rendered image."""
        self._save_rendered_current_image(
            title="Export Current Image",
            settings_key="current_image_export",
            default_name="current_image.tif",
            no_selection_message="No image is selected.",
            failure_title="Export Current Image Failed",
            success_prefix="Exported current image",
        )

    def save_edited_image_as(self) -> None:
        """Save the active Edit Image render to a raster file."""
        self._save_rendered_current_image(
            title="Save Image As",
            settings_key="edited_image_save",
            default_name="edited_image.tif",
            no_selection_message="No edited image is selected.",
            failure_title="Save Image Failed",
            success_prefix="Saved edited image",
        )

    def _save_rendered_current_image(
        self,
        *,
        title: str,
        settings_key: str,
        default_name: str,
        no_selection_message: str,
        failure_title: str,
        success_prefix: str,
    ) -> None:
        """Prompt for a raster path and save the currently selected rendered image."""
        node_id = self._current_export_source_node_id()
        if node_id is None:
            QMessageBox.information(self, title, no_selection_message)
            return
        filename = remembered_save_file(
            self,
            title,
            settings_key,
            "TIFF (*.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;Bitmap (*.bmp)",
            default_name,
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".tif")
        try:
            export_project_image(self.project, node_id, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, failure_title, str(exc))
            return
        self.statusBar().showMessage(f"{success_prefix} {path}")

    def export_figure_board(self) -> None:
        """Export a publication figure board with its saved layout transforms."""
        board = self._select_figure_board_for_export()
        if board is None:
            return
        self._save_figure_board_as(board)

    def save_current_figure_board_as(self) -> None:
        """Export the currently active figure board from the toolbar."""
        board = self.figure_board_workspace._current_board()
        if board is None:
            QMessageBox.information(self, "Save Figure Board as", "No figure board exists.")
            return
        self._save_figure_board_as(board)

    def _save_figure_board_as(self, board) -> None:
        """Prompt for a target path and export a figure board."""
        filename = remembered_save_file(
            self,
            "Save Figure Board as",
            "figure_board_export",
            "TIFF (*.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;"
            "Bitmap (*.bmp);;LaTeX Figure (*.tex)",
            f"{board.name}.tif",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".tif")
        try:
            export_project_figure_board(self.project, board, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save Figure Board Failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported figure board {path}")

    def _select_figure_board_for_export(self):
        boards = list(self.project.figure_boards.values())
        if not boards:
            QMessageBox.information(self, "Export Figure Board", "No figure board exists.")
            return None
        if len(boards) == 1:
            return boards[0]
        labels = [board.name for board in boards]
        selected, accepted = QInputDialog.getItem(
            self,
            "Export Figure Board",
            "Figure board:",
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return next((board for board in boards if board.name == selected), boards[0])

    def _current_export_source_node_id(self) -> str | None:
        if self._workspace.currentWidget() is self.edit_workspace:
            node_id = self.edit_workspace._current_source_node_id
            if node_id is not None:
                return node_id
        if self._workspace.currentWidget() is self.measure_workspace:
            asset_id = self.measure_workspace.current_asset_id()
            if asset_id is not None:
                return self.project.source_node_id_for_asset(asset_id)
        if self._workspace.currentWidget() is self.annotation_workspace:
            asset_id = self.annotation_workspace.current_asset_id()
            if asset_id is not None:
                return self.project.source_node_id_for_asset(asset_id)
        for asset in self.project.assets.values():
            node_id = self.project.source_node_id_for_asset(asset.id)
            if node_id is not None:
                return node_id
        return None

