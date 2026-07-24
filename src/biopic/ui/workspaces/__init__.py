"""Workspace widget implementations."""

from biopic.ui.workspaces.annotation import AnnotationWorkspace
from biopic.ui.workspaces.edit import EditWorkspace
from biopic.ui.workspaces.export import ExportWorkspace
from biopic.ui.workspaces.figure_board import FigureBoardWorkspace
from biopic.ui.workspaces.import_workspace import ImportWorkspace
from biopic.ui.workspaces.measure_scale import MeasureScaleWorkspace
from biopic.ui.workspaces.metadata import MetadataWorkspace
from biopic.ui.workspaces.overview import OverviewWorkspace
from biopic.ui.workspaces.stack import StackWorkspace
from biopic.ui.workspaces.stack_from_video import StackFromVideoWorkspace
from biopic.ui.workspaces.stitch_images import StitchImagesWorkspace

__all__ = [
    "AnnotationWorkspace",
    "EditWorkspace",
    "ExportWorkspace",
    "FigureBoardWorkspace",
    "ImportWorkspace",
    "MeasureScaleWorkspace",
    "MetadataWorkspace",
    "OverviewWorkspace",
    "StackWorkspace",
    "StackFromVideoWorkspace",
    "StitchImagesWorkspace",
]
