"""Main application window."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
)

from biopic.app.branding import APP_NAME, APP_VERSION, WINDOW_TITLE_PREFIX
from biopic.export import export_image, export_project_figure_board
from biopic.imaging.io import SUPPORTED_EXTENSIONS, import_images, import_stack
from biopic.imaging.project_render import render_project_image
from biopic.models.image_asset import ImageAssetKind
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.app_icon import biopic_app_icon
from biopic.ui.main_window_chrome import MAIN_WINDOW_STYLESHEET, WorkspaceWatermark
from biopic.ui.main_window_presets import MainWindowPresetsMixin
from biopic.ui.settings import remembered_open_file, remembered_open_files, remembered_save_file
from biopic.ui.stack_import_resolution import resolve_stack_import_paths
from biopic.ui.theme import apply_theme, current_theme, set_current_theme
from biopic.ui.workspace_helpers.common import stack_display_name
from biopic.ui.workspaces import (
    AnnotationWorkspace,
    EditWorkspace,
    ExportWorkspace,
    FigureBoardWorkspace,
    ImportWorkspace,
    MeasureScaleWorkspace,
    MetadataWorkspace,
    OverviewWorkspace,
    StackFromVideoWorkspace,
    StackWorkspace,
    StitchImagesWorkspace,
)

LOGGER = logging.getLogger(__name__)


class WorkspaceStack(QStackedWidget):
    """Stacked workspaces without inactive pages forcing the main-window minimum."""

    def minimumSizeHint(self) -> QSize:
        return QSize(1, 1)

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is not None:
            return current.sizeHint()
        return super().sizeHint()


class MainWindow(MainWindowPresetsMixin, QMainWindow):
    """Persistent BioPic LM frame with menus and workspace navigation."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.project_path: Path | None = None
        self.store = ProjectStore()
        self._has_unsaved_changes = False
        self._project_refresh_timer = QTimer(self)
        self._project_refresh_timer.setSingleShot(True)
        self._project_refresh_timer.setInterval(80)
        self._project_refresh_timer.timeout.connect(self.refresh_project_views)
        self._workspace_actions: dict[int, QAction] = {}
        self._theme_actions: dict[str, QAction] = {}
        self.setStyleSheet(MAIN_WINDOW_STYLESHEET)
        icon = biopic_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setWindowTitle(f"{WINDOW_TITLE_PREFIX} - {project.name}")
        self._workspace = WorkspaceStack()
        self._workspace_names = [
            "Overview",
            "Stack from Video",
            "Stack",
            "Stitch Images",
            "Import",
            "Metadata",
            "Edit Image",
            "Measure and Scale",
            "Annotate",
            "Figureboard",
            "Export",
        ]
        self.overview_workspace = OverviewWorkspace(self.project)
        self.stack_from_video_workspace = StackFromVideoWorkspace(self.project)
        self.import_workspace = ImportWorkspace(self.project)
        self.stack_workspace = StackWorkspace(self.project)
        self.stitch_images_workspace = StitchImagesWorkspace(self.project)
        self.metadata_workspace = MetadataWorkspace(self.project)
        self.edit_workspace = EditWorkspace(self.project)
        self.measure_workspace = MeasureScaleWorkspace(self.project)
        self.annotation_workspace = AnnotationWorkspace(self.project)
        self.figure_board_workspace = FigureBoardWorkspace(self.project)
        self.export_workspace = ExportWorkspace(self.project)
        self.import_workspace.assetSelected = self._import_asset_selected
        self.stack_from_video_workspace.stackCreated.connect(self._video_stack_created)
        self.stack_from_video_workspace.videoLoaded.connect(self._update_empty_watermark)
        self.stack_workspace.stackCompleted = self._stack_changed
        self.stitch_images_workspace.stitchCreated.connect(self._stitch_created)
        self.metadata_workspace.metadataChanged = self._metadata_changed
        self.edit_workspace.editApplied = self._project_changed
        self.measure_workspace.measurementChanged = self._project_changed
        self.annotation_workspace.annotationChanged = self._project_changed
        self.figure_board_workspace.boardChanged = self._project_changed
        self._workspace.addWidget(self.overview_workspace)
        self._workspace.addWidget(self.stack_from_video_workspace)
        self._workspace.addWidget(self.stack_workspace)
        self._workspace.addWidget(self.stitch_images_workspace)
        self._workspace.addWidget(self.import_workspace)
        self._workspace.addWidget(self.metadata_workspace)
        self._workspace.addWidget(self.edit_workspace)
        self._workspace.addWidget(self.measure_workspace)
        self._workspace.addWidget(self.annotation_workspace)
        self._workspace.addWidget(self.figure_board_workspace)
        self._workspace.addWidget(self.export_workspace)
        self.setCentralWidget(self._workspace)
        self._empty_watermark = WorkspaceWatermark(self._workspace)
        self._empty_watermark.raise_()
        self._build_menu()
        self._build_toolbars()
        self._build_docks()
        self.setStatusBar(QStatusBar(self))
        self._select_workspace(0)
        self.statusBar().showMessage("Ready")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._add_action(file_menu, "New Project", "Ctrl+N", self.new_project)
        self._add_action(file_menu, "Open Project", "Ctrl+O", self.open_project)
        self._add_action(file_menu, "Save Project", "Ctrl+S", self.save_project)
        self._add_action(file_menu, "Save Project As", "Ctrl+Shift+S", self.save_project_as)
        file_menu.addSeparator()
        self._add_action(file_menu, "Import Image...", None, self.import_image)
        self._add_action(file_menu, "Import Image Stack...", None, self.import_image_stack)
        self._add_action(file_menu, "Import Video...", None, self.import_video)
        file_menu.addSeparator()
        self._add_action(file_menu, "Export Current Image", None, self.export_current_image)
        self._add_action(file_menu, "Export Figure Board", None, self.export_figure_board)
        file_menu.addSeparator()
        file_menu.addMenu("Recent Projects")

        edit_menu = self.menuBar().addMenu("&Edit")
        self._add_action(edit_menu, "Undo", "Ctrl+Z", self.undo)
        self._add_action(edit_menu, "Redo", "Ctrl+Y", self.redo)
        self._add_action(edit_menu, "Copy", "Ctrl+C", self.edit_workspace.copy_selection)
        self._add_action(edit_menu, "Paste", "Ctrl+V", self.edit_workspace.paste_as_layer)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Preferences", None, self._not_implemented)

        view_menu = self.menuBar().addMenu("&View")
        appearance_menu = view_menu.addMenu("Appearance")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for theme, label in (("dark", "Dark Mode"), ("light", "Light Mode")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(current_theme() == theme)
            action.triggered.connect(
                lambda _checked=False, selected=theme: self._set_theme(selected)
            )
            theme_group.addAction(action)
            appearance_menu.addAction(action)
            self._theme_actions[theme] = action

        self.presets_menu = self.menuBar().addMenu("&Presets")
        self.journal_presets_menu = self.presets_menu.addMenu("Journal Presets")
        for journal_name in self.figure_board_workspace.journal_preset_names():
            self._add_action(
                self.journal_presets_menu,
                journal_name,
                None,
                self._journal_preset_callback(journal_name),
            )
        self.equipment_presets_menu = self.presets_menu.addMenu("Equipment")
        self.location_presets_menu = self.presets_menu.addMenu("Location")
        self.collector_presets_menu = self.presets_menu.addMenu("Collector")
        self.preparation_presets_menu = self.presets_menu.addMenu("Preparation")
        self._rebuild_metadata_preset_menus()

        self.menuBar().addSeparator()
        self._add_workspace_action("Overview", 0)
        self.menuBar().addSeparator()
        self._add_workspace_action("Stack from Video", 1)
        self._add_workspace_action("Stack", 2)
        self._add_workspace_action("Stitch Images", 3)
        self.menuBar().addSeparator()
        self._add_workspace_action("Metadata", 5)
        self._add_workspace_action("Edit Image", 6)
        self._add_workspace_action("Measure and Scale", 7)
        self._add_workspace_action("Annotate", 8)
        self._add_workspace_action("Figureboard", 9)
        self.menuBar().addSeparator()

        help_menu = self.menuBar().addMenu("&Help")
        self._add_action(help_menu, "Help", None, self._not_implemented)
        self._add_action(help_menu, "About", None, self._show_about)

    def _build_docks(self) -> None:
        self.project_dock = QDockWidget("Project", self)
        self.project_dock.setObjectName("projectDock")
        self.project_list = QListWidget(self.project_dock)
        self.project_dock.setWidget(self.project_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.project_dock)
        self.refresh_project_views()

    def _build_toolbars(self) -> None:
        self.context_toolbar = QToolBar("Tool", self)
        self.context_toolbar.setObjectName("contextToolbar")
        self.context_toolbar.setMovable(False)
        self.context_toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.context_toolbar)

    def _toolbar_action(self, label: str, callback: Callable[[], object]) -> QAction:
        action = QAction(label, self)
        action.triggered.connect(callback)
        return action

    def _add_action(
        self, menu: QMenu, label: str, shortcut: str | None, callback: Callable[[], object]
    ) -> QAction:
        action = QAction(label, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _add_workspace_action(self, label: str, index: int) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.triggered.connect(
            lambda _checked=False, workspace_index=index: self._select_workspace(
                workspace_index
            )
        )
        self.menuBar().addAction(action)
        self._workspace_actions[index] = action
        return action

    def _select_workspace(self, index: int) -> None:
        self._workspace.setCurrentIndex(index)
        self._update_empty_watermark()
        active_widget = self._workspace.widget(index)
        self.project_dock.setVisible(active_widget is not self.edit_workspace)
        for workspace_index, action in self._workspace_actions.items():
            is_active = workspace_index == index
            action.setChecked(is_active)
            font = QFont()
            font.setBold(is_active)
            action.setFont(font)
        refresh = getattr(active_widget, "refresh", None)
        if callable(refresh):
            refresh()
        if active_widget is self.annotation_workspace:
            self.annotation_workspace.select_asset_id(self.measure_workspace.current_asset_id())
        self._refresh_context_toolbar(index)
        self.statusBar().showMessage(f"Workspace: {self._workspace_names[index]}")

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._update_empty_watermark()

    def undo(self) -> None:
        """Undo in the active editing workspace."""
        if self._workspace.currentWidget() is self.figure_board_workspace:
            self.figure_board_workspace.undo()
            return
        self.edit_workspace.undo()

    def redo(self) -> None:
        """Redo in the active editing workspace."""
        if self._workspace.currentWidget() is self.figure_board_workspace:
            self.figure_board_workspace.redo()
            return
        self.edit_workspace.redo()

    def _refresh_context_toolbar(self, index: int) -> None:
        self.context_toolbar.clear()
        if index == 1:
            self.context_toolbar.addAction(
                self._toolbar_action("Import Video", self.stack_from_video_workspace.open_video)
            )
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Create Stack from Video",
                    self.stack_from_video_workspace.create_stack_from_video,
                )
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Cancel", self.stack_from_video_workspace.cancel_extraction)
            )
        elif index == 2:
            self.context_toolbar.addAction(
                self._toolbar_action("Import Image Stack", self.import_image_stack)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Run Stack", self.stack_workspace.run_stacking)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Reverse Order", self.stack_workspace.reverse_current_stack)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Remove Image", self.stack_workspace.remove_selected_image)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Cancel", self.stack_workspace.cancel_stacking)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Save Result As", self.save_stacked_image)
            )
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Sharpness Comparison",
                    self.stack_workspace.open_sharpness_comparison,
                )
            )
        elif index == 3:
            self.context_toolbar.addAction(
                self._toolbar_action("Import Images", self.stitch_images_workspace.import_images)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Stitch Images", self.stitch_images_workspace.stitch_images)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Cancel", self.stitch_images_workspace.cancel_stitching)
            )
        elif index == 6:
            self.context_toolbar.addAction(
                self._toolbar_action("Apply", self.edit_workspace.apply_current_operation)
            )
            background_button = QToolButton(self.context_toolbar)
            background_button.setText("Background Correction")
            background_button.setMinimumWidth(178)
            background_button.setStyleSheet("QToolButton { padding-right: 16px; }")
            background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            background_menu = QMenu(background_button)
            background_menu.addAction(
                "Flat-Field Correction",
                lambda: self.edit_workspace.apply_named_operation(
                    "flat_field_correction_estimated"
                ),
            )
            background_menu.addAction(
                "Uniform Background Outside Selection",
                self.edit_workspace.create_uniform_background_outside_selection_layer,
            )
            background_button.setMenu(background_menu)
            self.context_toolbar.addWidget(background_button)
            self.context_toolbar.addSeparator()
            white_balance_button = QToolButton(self.context_toolbar)
            white_balance_button.setText("White Balance")
            white_balance_button.setMinimumWidth(124)
            white_balance_button.setStyleSheet("QToolButton { padding-right: 16px; }")
            white_balance_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            white_balance_menu = QMenu(white_balance_button)
            white_balance_menu.addAction(
                "White Balance",
                self.edit_workspace.open_white_balance_dialog,
            )
            white_balance_menu.addAction(
                "Auto White Balance",
                lambda: self.edit_workspace.apply_named_operation(
                    "white_balance", {"method": "auto", "sample_size": 24}
                ),
            )
            white_balance_button.setMenu(white_balance_menu)
            self.context_toolbar.addWidget(white_balance_button)
            self.context_toolbar.addSeparator()
            color_button = QToolButton(self.context_toolbar)
            color_button.setText("Color")
            color_button.setMinimumWidth(78)
            color_button.setStyleSheet("QToolButton { padding-right: 16px; }")
            color_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            color_menu = QMenu(color_button)
            color_menu.addAction(
                "Color / Saturation",
                self.edit_workspace.open_color_saturation_dialog,
            )
            color_button.setMenu(color_menu)
            self.context_toolbar.addWidget(color_button)
            self.context_toolbar.addSeparator()
            filters_button = QToolButton(self.context_toolbar)
            filters_button.setText("Filters")
            filters_button.setMinimumWidth(78)
            filters_button.setStyleSheet("QToolButton { padding-right: 16px; }")
            filters_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            filters_menu = QMenu(filters_button)
            filters_menu.addAction(
                "Noise Reduction",
                self.edit_workspace.open_noise_reduction_dialog,
            )
            filters_menu.addAction(
                "High-Pass Filter",
                self.edit_workspace.open_high_pass_dialog,
            )
            filters_button.setMenu(filters_menu)
            self.context_toolbar.addWidget(filters_button)
            self.context_toolbar.addSeparator()
            self.context_toolbar.addAction(
                self._toolbar_action("Add Layer", lambda: self.edit_workspace.add_empty_layer())
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Copy", self.edit_workspace.copy_selection)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Paste", self.edit_workspace.paste_as_layer)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Remove Layer", self.edit_workspace.remove_selected_layer)
            )
        elif index == 7:
            set_scale_button = QToolButton(self.context_toolbar)
            set_scale_button.setText("Set Scale")
            set_scale_button.setMinimumWidth(96)
            set_scale_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            set_scale_button.setMenu(self.measure_workspace.set_scale_menu)
            self.context_toolbar.addWidget(set_scale_button)
            self.context_toolbar.addAction(
                self._toolbar_action("Add Scale Bar", self.measure_workspace.add_scale_bar)
            )
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Add Measurement Scale Bar",
                    self.measure_workspace.add_measurement_scale_bar,
                )
            )
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Add Measurement", self.measure_workspace.add_line_measurement
                )
            )
        elif index == 8:
            self.context_toolbar.addAction(
                self._toolbar_action("Add Label", self.annotation_workspace.add_label)
            )
            abbreviation_button = QToolButton(self.context_toolbar)
            abbreviation_button.setText("Abbreviation Table")
            abbreviation_button.setMinimumWidth(150)
            abbreviation_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            abbreviation_button.setMenu(self.annotation_workspace.abbreviation_table_menu)
            self.context_toolbar.addWidget(abbreviation_button)
        elif index == 9:
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Settings",
                    self.figure_board_workspace.open_scale_bar_settings_dialog,
                )
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Undo", self.figure_board_workspace.undo)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Redo", self.figure_board_workspace.redo)
            )
            self.context_toolbar.addSeparator()
            self.context_toolbar.addAction(
                self._toolbar_action(
                    "Create Figure Board",
                    lambda: self.figure_board_workspace.create_board(show_dialog=True),
                )
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Layout", self.figure_board_workspace.open_layout_dialog)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Save Figure Board as", self.save_current_figure_board_as)
            )

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

    def import_video(self) -> None:
        """Open the video import workflow from the File menu."""
        self._select_workspace(1)
        self.stack_from_video_workspace.open_video()

    def open_project(self) -> None:
        """Open a saved BioPic LM project."""
        if not self._confirm_discard_unsaved_changes("open another project"):
            return
        filename = remembered_open_file(
            self,
            "Open Project",
            "project_open",
            "BioPic LM Project (*.biopic.json);;JSON (*.json)",
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
        self.refresh_project_views()
        self.statusBar().showMessage(f"Opened {filename}")

    def save_project(self) -> bool:
        """Save to the current project path or prompt for one."""
        if self.project_path is None:
            return self.save_project_as()
        try:
            self.edit_workspace._flush_pending_selection_persistence()
            self.store.save(self.project, self.project_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Project Failed", str(exc))
            return False
        self._has_unsaved_changes = False
        self.refresh_project_views()
        self.statusBar().showMessage(f"Saved {self.project_path}")
        return True

    def save_project_as(self) -> bool:
        """Prompt and save the current project."""
        filename = remembered_save_file(
            self,
            "Save Project As",
            "project_save",
            "BioPic LM Project (*.biopic.json)",
            f"{self.project.name}.biopic.json",
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix != ".json":
            path = path.with_suffix(".biopic.json")
        self.project_path = path
        return self.save_project()

    def import_image(self) -> None:
        """Import one or more independent images."""
        paths = self._select_image_paths("Import Image")
        if not paths:
            return
        try:
            assets = import_images(self.project, paths)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return
        self._has_unsaved_changes = True
        self.refresh_project_views()
        self._select_workspace(0)
        self.statusBar().showMessage(f"Imported {len(assets)} image(s)")

    def import_image_stack(self) -> None:
        """Import selected files as an ordered focal stack."""
        paths = self._select_image_paths("Import Image Stack")
        if not paths:
            return
        paths = resolve_stack_import_paths(self, paths)
        if not paths:
            return
        try:
            stack = import_stack(self.project, paths, StackKind.FOCAL)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Stack Failed", str(exc))
            return
        self._has_unsaved_changes = True
        self.refresh_project_views()
        self._select_workspace(2)
        self.statusBar().showMessage(f"Imported stack '{stack.name}' with {len(paths)} frame(s)")

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
        node_id = self._current_export_source_node_id()
        if node_id is None:
            QMessageBox.information(self, "Export Current Image", "No image is selected.")
            return
        filename = remembered_save_file(
            self,
            "Export Current Image",
            "current_image_export",
            "TIFF (*.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;Bitmap (*.bmp)",
            "current_image.tif",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".tif")
        try:
            pixels = render_project_image(self.project, node_id)
            if pixels is None:
                raise ValueError("The selected image could not be rendered.")
            export_image(pixels, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Export Current Image Failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported current image {path}")

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
        if self._workspace.currentWidget() in {self.measure_workspace, self.annotation_workspace}:
            asset_id = self.measure_workspace.current_asset_id()
            if asset_id is not None:
                return self.project.source_node_id_for_asset(asset_id)
        for asset in self.project.assets.values():
            node_id = self.project.source_node_id_for_asset(asset.id)
            if node_id is not None:
                return node_id
        return None

    def _bind_project_to_workspaces(self) -> None:
        self.overview_workspace.project = self.project
        self.import_workspace.project = self.project
        self.stack_from_video_workspace.project = self.project
        self.stack_workspace.project = self.project
        self.stitch_images_workspace.project = self.project
        self.metadata_workspace.project = self.project
        self.edit_workspace.project = self.project
        self.measure_workspace.project = self.project
        self.annotation_workspace.project = self.project
        self.figure_board_workspace.project = self.project
        self.export_workspace.project = self.project
        self.import_workspace.assetSelected = self._import_asset_selected
        with suppress(RuntimeError, TypeError):
            self.stack_from_video_workspace.stackCreated.disconnect(self._video_stack_created)
        self.stack_from_video_workspace.stackCreated.connect(self._video_stack_created)
        self.stack_workspace.stackCompleted = self._stack_changed
        with suppress(RuntimeError, TypeError):
            self.stitch_images_workspace.stitchCreated.disconnect(self._stitch_created)
        self.stitch_images_workspace.stitchCreated.connect(self._stitch_created)
        self.metadata_workspace.metadataChanged = self._metadata_changed
        self.edit_workspace.editApplied = self._project_changed
        self.measure_workspace.measurementChanged = self._project_changed
        self.annotation_workspace.annotationChanged = self._project_changed
        self.figure_board_workspace.boardChanged = self._project_changed
        self.measure_workspace._asset_list_signature = None
        self.measure_workspace._display_signature = None
        self.measure_workspace._rendered_image_cache.clear()
        self.measure_workspace._persistent_scale_presets_loaded = False
        self.annotation_workspace._asset_list_signature = None
        self.annotation_workspace._display_signature = None
        self.annotation_workspace._rendered_image_cache.clear()

    def _import_asset_selected(self, asset_id: str) -> None:
        self.stack_workspace.select_asset(asset_id)
        self.metadata_workspace.select_asset_id(asset_id)

    def _video_stack_created(self, stack_id: str) -> None:
        self._has_unsaved_changes = True
        self.stack_workspace.select_stack(stack_id)
        self._select_workspace(2)

    def _stitch_created(self, asset_ids: list[str]) -> None:
        self._has_unsaved_changes = True
        self.edit_workspace.set_asset_filter(asset_ids)
        self._select_workspace(6)

    def _project_changed(self) -> None:
        self._has_unsaved_changes = True
        if self._workspace.currentWidget() is self.edit_workspace:
            dirty_marker = "*" if self._has_unsaved_changes else ""
            self.setWindowTitle(f"{WINDOW_TITLE_PREFIX} - {self.project.name}{dirty_marker}")
            return
        if not self._project_refresh_timer.isActive():
            self._project_refresh_timer.start()

    def _stack_changed(self) -> None:
        self._has_unsaved_changes = True
        if self._workspace.currentWidget() is self.edit_workspace:
            self.edit_workspace.refresh()
        else:
            self.edit_workspace._editable_assets = []
        if not self._project_refresh_timer.isActive():
            self._project_refresh_timer.start()

    def _metadata_changed(self) -> None:
        self._has_unsaved_changes = True
        dirty_marker = "*" if self._has_unsaved_changes else ""
        self.setWindowTitle(f"{WINDOW_TITLE_PREFIX} - {self.project.name}{dirty_marker}")

    def _confirm_discard_unsaved_changes(self, action: str) -> bool:
        if not self._has_unsaved_changes:
            return True
        dialog = QMessageBox(self)
        dialog.setPalette(self.palette())
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Unsaved Project")
        dialog.setText(
            f"Save the current project before you {action}? Unsaved changes will be lost."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Save)
        dialog.setStyleSheet(MAIN_WINDOW_STYLESHEET)
        response = dialog.exec()
        if response == QMessageBox.StandardButton.Save:
            return self.save_project()
        return response == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent) -> None:
        """Warn before closing with unsaved project changes."""
        if self._confirm_discard_unsaved_changes("close BioPic LM"):
            event.accept()
            return
        event.ignore()

    def _select_image_paths(self, title: str) -> list[Path]:
        filters = "Images (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)) + ")"
        filenames = remembered_open_files(self, title, "image_import", filters)
        return [Path(filename) for filename in filenames]

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME} {APP_VERSION}\nNon-destructive microbiological figure workflow.",
        )

    def _not_implemented(self) -> None:
        self.statusBar().showMessage("This command is scheduled for a later milestone.")

    def _set_theme(self, theme: str) -> None:
        set_current_theme(theme)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self.setStyleSheet(MAIN_WINDOW_STYLESHEET)
        for action_theme, action in self._theme_actions.items():
            action.setChecked(action_theme == theme)

    def _update_empty_watermark(self) -> None:
        if not hasattr(self, "_empty_watermark"):
            return
        self._empty_watermark.setGeometry(self._workspace.rect())
        self._empty_watermark.setVisible(
            self._workspace.currentWidget() is self.overview_workspace and self._project_is_empty()
        )
        self._empty_watermark.raise_()

    def _project_is_empty(self) -> bool:
        return not (
            self.project.assets
            or self.project.stacks
            or self.project.graph.nodes
            or self.project.figure_boards
            or getattr(self.stack_from_video_workspace, "_video_paths", [])
        )
