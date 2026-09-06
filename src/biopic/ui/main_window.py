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
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from biopic.app.branding import APP_NAME, APP_VERSION, WINDOW_TITLE_PREFIX
from biopic.export import export_project_figure_board, export_project_image
from biopic.imaging.io import SUPPORTED_EXTENSIONS, import_images, import_stack
from biopic.models.image_asset import ImageAssetKind
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.app_icon import biopic_app_icon
from biopic.ui.main_window_chrome import MAIN_WINDOW_STYLESHEET, WorkspaceWatermark
from biopic.ui.main_window_presets import MainWindowPresetsMixin
from biopic.ui.main_window_project_actions import MainWindowProjectActionsMixin
from biopic.ui.main_window_save_options import load_project_save_options
from biopic.ui.settings import (
    DEBUG_OPTIONS_SETTING_KEY,
    remembered_open_file,
    remembered_open_files,
    remembered_save_file,
    set_settings_json,
    settings_json,
)
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


class WorkspaceStack(QStackedWidget):
    """Stacked workspaces without inactive pages forcing the main-window minimum."""

    def minimumSizeHint(self) -> QSize:
        return QSize(1, 1)

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is not None:
            return current.sizeHint()
        return super().sizeHint()


class MainWindow(MainWindowProjectActionsMixin, MainWindowPresetsMixin, QMainWindow):
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
        self.debug_options_action: QAction | None = None
        self.cuda_action: QAction | None = None
        self.gpu_limit_options_spin: QSpinBox | None = None
        self._copied_project_image_node_id: str | None = None
        self._copied_project_image_asset_id: str | None = None
        self._save_progress_token = 0
        self.project_save_options = load_project_save_options()
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
            "Metadata",
            "Edit Image",
            "Measure and Scale",
            "Annotate",
            "Figure Board",
            "Import",
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
        self.figure_board_workspace.annotationOverlayChanged = self._metadata_changed
        self._workspace.addWidget(self.overview_workspace)
        self._workspace.addWidget(self.stack_from_video_workspace)
        self._workspace.addWidget(self.stack_workspace)
        self._workspace.addWidget(self.stitch_images_workspace)
        self._workspace.addWidget(self.metadata_workspace)
        self._workspace.addWidget(self.edit_workspace)
        self._workspace.addWidget(self.measure_workspace)
        self._workspace.addWidget(self.annotation_workspace)
        self._workspace.addWidget(self.figure_board_workspace)
        self._workspace.addWidget(self.import_workspace)
        self._workspace.addWidget(self.export_workspace)
        self.setCentralWidget(self._workspace)
        self._empty_watermark = WorkspaceWatermark(self._workspace)
        self._empty_watermark.raise_()
        self._build_menu()
        self._build_toolbars()
        self._build_docks()
        self.setStatusBar(QStatusBar(self))
        self._build_save_progress_status()
        self._select_workspace(WORKSPACE_OVERVIEW)
        self.statusBar().showMessage("Ready")

    def _build_save_progress_status(self) -> None:
        """Create hidden save progress controls in the bottom status bar."""
        self.save_progress_label = QLabel("", self)
        self.save_progress_label.setMinimumWidth(260)
        self.save_progress_label.setVisible(False)
        self.save_progress_bar = QProgressBar(self)
        self.save_progress_bar.setRange(0, 100)
        self.save_progress_bar.setFixedWidth(180)
        self.save_progress_bar.setTextVisible(True)
        self.save_progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.save_progress_label)
        self.statusBar().addPermanentWidget(self.save_progress_bar)

    def _set_save_progress(
        self,
        completed: int,
        total: int,
        path: Path,
        action: str,
    ) -> None:
        """Show project save progress in the status bar."""
        total = max(1, int(total))
        completed = max(0, min(total, int(completed)))
        percent = int(round((completed / total) * 100.0))
        self.save_progress_label.setText(f"{action}: {Path(path).name}")
        self.save_progress_label.setToolTip(str(path))
        self.save_progress_bar.setValue(percent)
        self.save_progress_label.setVisible(True)
        self.save_progress_bar.setVisible(True)

    def _hide_save_progress(self) -> None:
        """Hide save progress controls after a save finishes or fails."""
        self.save_progress_label.clear()
        self.save_progress_label.setToolTip("")
        self.save_progress_label.setVisible(False)
        self.save_progress_bar.setVisible(False)

    def _hide_save_progress_if_current(self, token: int) -> None:
        """Hide save progress only if no newer save has started."""
        if token == self._save_progress_token:
            self._hide_save_progress()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._add_action(file_menu, "New Project", "Ctrl+N", self.new_project)
        self._add_action(file_menu, "Open Project", "Ctrl+O", self.open_project)
        self._add_action(file_menu, "Save Project", "Ctrl+S", self.save_project)
        self._add_action(file_menu, "Save Project As", "Ctrl+Shift+S", self.save_project_as)
        self._add_action(file_menu, "Rename Project...", None, self.rename_project)
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
        self._add_action(edit_menu, "Copy", "Ctrl+C", self.copy_current_context)
        self._add_action(edit_menu, "Paste", "Ctrl+V", self.paste_current_context)
        self._add_action(edit_menu, "Copy Image", "Ctrl+Shift+C", self.copy_current_project_image)
        self._add_action(edit_menu, "Paste Image", "Ctrl+Shift+V", self.paste_copied_project_image)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Preferences", None, self._not_implemented)

        options_menu = self.menuBar().addMenu("&Options")
        appearance_menu = options_menu.addMenu("Appearance")
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
        options_menu.addSeparator()
        debug_options_action = QAction("Enable Debug Options", self)
        debug_options_action.setCheckable(True)
        debug_options_action.setChecked(bool(settings_json(DEBUG_OPTIONS_SETTING_KEY, False)))
        debug_options_action.toggled.connect(self._set_debug_options_enabled)
        options_menu.addAction(debug_options_action)
        self.debug_options_action = debug_options_action
        self._set_debug_options_enabled(debug_options_action.isChecked(), persist=False)
        saving_options_menu = options_menu.addMenu("Saving")
        self._add_action(
            saving_options_menu,
            "Save Options...",
            None,
            self.open_save_options_dialog,
        )
        stacking_options_menu = options_menu.addMenu("Stacking")
        cuda_action = QAction("Use CUDA", self)
        cuda_action.setCheckable(True)
        cuda_action.setChecked(self.stack_workspace.cuda_check.isChecked())
        cuda_action.toggled.connect(self.stack_workspace.set_cuda_enabled)
        stacking_options_menu.addAction(cuda_action)
        self.cuda_action = cuda_action

        gpu_limit_action = QWidgetAction(self)
        gpu_limit_widget = QWidget(self)
        gpu_limit_layout = QHBoxLayout(gpu_limit_widget)
        gpu_limit_layout.setContentsMargins(8, 2, 8, 2)
        gpu_limit_layout.addWidget(QLabel("GPU limit", gpu_limit_widget))
        gpu_limit_spin = QSpinBox(gpu_limit_widget)
        gpu_limit_spin.setRange(
            self.stack_workspace.gpu_limit_spin.minimum(),
            self.stack_workspace.gpu_limit_spin.maximum(),
        )
        gpu_limit_spin.setValue(self.stack_workspace.gpu_limit_spin.value())
        gpu_limit_spin.setSuffix(" GB")
        gpu_limit_spin.valueChanged.connect(self.stack_workspace.set_gpu_memory_limit_gb)
        gpu_limit_layout.addWidget(gpu_limit_spin)
        gpu_limit_action.setDefaultWidget(gpu_limit_widget)
        stacking_options_menu.addAction(gpu_limit_action)
        self.gpu_limit_options_spin = gpu_limit_spin

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
        self._add_workspace_action("Overview", WORKSPACE_OVERVIEW)
        self._add_workspace_action("Stack from Video", WORKSPACE_STACK_FROM_VIDEO)
        self._add_workspace_action("Stack", WORKSPACE_STACK)
        self._add_workspace_action("Stitch Images", WORKSPACE_STITCH_IMAGES)
        self._add_workspace_action("Metadata", WORKSPACE_METADATA)
        self._add_workspace_action("Edit Image", WORKSPACE_EDIT_IMAGE)
        self._add_workspace_action("Measure and Scale", WORKSPACE_MEASURE_SCALE)
        self._add_workspace_action("Annotate", WORKSPACE_ANNOTATE)
        self._add_workspace_action("Figure Board", WORKSPACE_FIGURE_BOARD)
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

    def _set_debug_options_enabled(self, enabled: bool, *, persist: bool = True) -> None:
        if persist:
            set_settings_json(DEBUG_OPTIONS_SETTING_KEY, bool(enabled))
        self.stack_workspace.set_debug_options_enabled(bool(enabled))

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
        if self._workspace.currentWidget() is self.stack_workspace:
            self.stack_workspace.undo()
            return
        if self._workspace.currentWidget() is self.measure_workspace:
            self.measure_workspace.undo()
            return
        if self._workspace.currentWidget() is self.annotation_workspace:
            self.annotation_workspace.undo()
            return
        if self._workspace.currentWidget() is self.figure_board_workspace:
            self.figure_board_workspace.undo()
            return
        self.edit_workspace.undo()

    def redo(self) -> None:
        """Redo in the active editing workspace."""
        if self._workspace.currentWidget() is self.stack_workspace:
            self.stack_workspace.redo()
            return
        if self._workspace.currentWidget() is self.measure_workspace:
            self.measure_workspace.redo()
            return
        if self._workspace.currentWidget() is self.annotation_workspace:
            self.annotation_workspace.redo()
            return
        if self._workspace.currentWidget() is self.figure_board_workspace:
            self.figure_board_workspace.redo()
            return
        self.edit_workspace.redo()

    def _refresh_context_toolbar(self, index: int) -> None:
        self.context_toolbar.clear()
        if index == WORKSPACE_STACK_FROM_VIDEO:
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
        elif index == WORKSPACE_STACK:
            self.context_toolbar.addAction(
                self._toolbar_action("Import Image Stack", self.import_image_stack)
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
        elif index == WORKSPACE_STITCH_IMAGES:
            self.context_toolbar.addAction(
                self._toolbar_action("Import Images", self.stitch_images_workspace.import_images)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Stitch Images", self.stitch_images_workspace.stitch_images)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Cancel", self.stitch_images_workspace.cancel_stitching)
            )
        elif index == WORKSPACE_EDIT_IMAGE:
            self.context_toolbar.addAction(
                self._toolbar_action("Apply", self.edit_workspace.apply_current_operation)
            )
            self.context_toolbar.addAction(
                self._toolbar_action("Save Image As", self.save_edited_image_as)
            )
            self.context_toolbar.addSeparator()
            background_button = QToolButton(self.context_toolbar)
            background_button.setText("Background Correction")
            background_button.setMinimumWidth(178)
            background_button.setStyleSheet("QToolButton { padding-right: 16px; }")
            background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            background_menu = QMenu(background_button)
            background_menu.addAction(
                "Flat-Field Correction",
                self.edit_workspace.open_flat_field_dialog,
            )
            background_menu.addAction(
                "Uniform Background Outside Selection (Stamp)",
                self.edit_workspace.create_uniform_background_outside_selection_layer,
            )
            background_menu.addAction(
                "Uniform Background Outside Selection (Heal)",
                self.edit_workspace.create_healed_uniform_background_outside_selection_layer,
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
                "Levels / Tonwertkorrektur",
                self.edit_workspace.open_levels_dialog,
            )
            color_menu.addAction(
                "Gamma Correction",
                self.edit_workspace.open_gamma_dialog,
            )
            color_menu.addAction(
                "Curves / Gradationskurve",
                self.edit_workspace.open_curves_dialog,
            )
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
        elif index == WORKSPACE_MEASURE_SCALE:
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
                    "Add Measurement", self.measure_workspace.add_line_measurement
                )
            )
        elif index == WORKSPACE_ANNOTATE:
            self.context_toolbar.addAction(
                self._toolbar_action("Add Label", self.annotation_workspace.add_label)
            )
            abbreviation_button = QToolButton(self.context_toolbar)
            abbreviation_button.setText("Abbreviation Table")
            abbreviation_button.setMinimumWidth(150)
            abbreviation_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            abbreviation_button.setMenu(self.annotation_workspace.abbreviation_table_menu)
            self.context_toolbar.addWidget(abbreviation_button)
        elif index == WORKSPACE_FIGURE_BOARD:
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
            self.context_toolbar.addSeparator()
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
        self.figure_board_workspace.annotationOverlayChanged = self._metadata_changed
        self.edit_workspace._asset_list_signature = None
        self.edit_workspace._loaded_asset_signature = None
        self.edit_workspace._invalidate_edit_composite_cache()
        self.measure_workspace._asset_list_signature = None
        self.measure_workspace._display_signature = None
        self.measure_workspace._rendered_image_cache.clear()
        self.measure_workspace._persistent_scale_presets_loaded = False
        self.annotation_workspace._asset_list_signature = None
        self.annotation_workspace._display_signature = None
        self.annotation_workspace._rendered_image_cache.clear()
        self.figure_board_workspace.preview.project = self.project
        self.figure_board_workspace.preview.invalidate_render_cache()
        self.figure_board_workspace.image_strip._items_signature = None
        self.figure_board_workspace.image_strip._thumbnail_cache.clear()

    def _import_asset_selected(self, asset_id: str) -> None:
        self.stack_workspace.select_asset(asset_id)
        self.metadata_workspace.select_asset_id(asset_id)

    def _video_stack_created(self, stack_id: str) -> None:
        self._has_unsaved_changes = True
        self.stack_workspace.select_stack(stack_id)
        self._select_workspace(WORKSPACE_STACK)

    def _stitch_created(self, asset_ids: list[str]) -> None:
        self._has_unsaved_changes = True
        self.edit_workspace.set_asset_filter(asset_ids)
        self._select_workspace(WORKSPACE_EDIT_IMAGE)

    def _project_changed(self) -> None:
        self._has_unsaved_changes = True
        if self._workspace.currentWidget() is self.edit_workspace:
            self._update_project_title()
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
        self._update_project_title()

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
