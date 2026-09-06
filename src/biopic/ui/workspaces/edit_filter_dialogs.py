"""Filter and adjustment dialogs used by the edit workspace.

This module is intentionally a small compatibility facade. The dialog
implementations live in focused modules so the edit workspace remains easier to
navigate and cheaper to inspect.
"""

from __future__ import annotations

from biopic.ui.workspaces.edit_color_saturation_dialog import EditColorSaturationDialogMixin
from biopic.ui.workspaces.edit_filter_result_dialogs import EditFilterResultDialogsMixin
from biopic.ui.workspaces.edit_tonal_dialogs import (
    EditTonalDialogsMixin,
    _CurveEditorWidget,
    _LevelsHistogramWidget,
    _LevelsInputWidget,
    _evaluate_curve,
    _levels_auto_input_bounds,
    _levels_channel_values,
    _sanitize_curve_points,
)
from biopic.ui.workspaces.edit_white_balance_dialog import EditWhiteBalanceDialogMixin


class EditFilterDialogsMixin(
    EditFilterResultDialogsMixin,
    EditTonalDialogsMixin,
    EditWhiteBalanceDialogMixin,
    EditColorSaturationDialogMixin,
):
    """Combined dialog mixin for the edit workspace."""


__all__ = [
    "EditFilterDialogsMixin",
    "_CurveEditorWidget",
    "_LevelsHistogramWidget",
    "_LevelsInputWidget",
    "_evaluate_curve",
    "_levels_auto_input_bounds",
    "_levels_channel_values",
    "_sanitize_curve_points",
]
