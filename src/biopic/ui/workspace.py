"""Workspace page compatibility exports."""

from __future__ import annotations

from biopic.ui.workspaces.annotation import AnnotationWorkspace  # noqa: F401
from biopic.ui.workspaces.edit import EditWorkspace  # noqa: F401
from biopic.ui.workspaces.edit_constants import GIMP_TOOLBOX_TOOLS as _GIMP_TOOLBOX_TOOLS  # noqa: F401
from biopic.ui.workspaces.export import ExportWorkspace  # noqa: F401
from biopic.ui.workspaces.figure_board import FigureBoardWorkspace  # noqa: F401
from biopic.ui.workspaces.import_workspace import ImportWorkspace  # noqa: F401
from biopic.ui.workspaces.measure_scale import MeasureScaleWorkspace  # noqa: F401
from biopic.ui.workspaces.metadata import MetadataWorkspace  # noqa: F401
from biopic.ui.workspaces.overview import OverviewWorkspace  # noqa: F401
from biopic.ui.workspaces.stack import StackWorkspace  # noqa: F401


def _catmull_rom_points(
    p0: tuple[int, int],
    p1: tuple[int, int],
    p2: tuple[int, int],
    p3: tuple[int, int],
    segments: int,
) -> list[tuple[int, int]]:
    """Return integer Catmull-Rom samples from p1 toward p2."""
    if segments <= 0:
        return [p2]
    points: list[tuple[int, int]] = []
    for index in range(1, segments + 1):
        t = index / segments
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (
            (2 * p1[0])
            + (-p0[0] + p2[0]) * t
            + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
            + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
        )
        y = 0.5 * (
            (2 * p1[1])
            + (-p0[1] + p2[1]) * t
            + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
            + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
        )
        point = (int(round(x)), int(round(y)))
        if not points or points[-1] != point:
            points.append(point)
    return points
