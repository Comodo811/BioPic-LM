"""Native-assisted NumPy projection backend.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np

from biopic.imaging.engine.types import EngineCapabilities, Rect
from biopic.imaging.project_render import (
    render_edit_layers,
    render_edit_layers_region,
    render_edit_layers_region_excluding,
)
from biopic.models.project import Project


class NumpyProjectionBackend:
    """Current projection backend using NumPy plus native compositing kernels."""

    name = "numpy-native"
    capabilities = EngineCapabilities(
        tiled_drawables=True,
        graph_projection=True,
        dirty_region_projection=True,
        native_compositing=True,
        gegl_available=False,
        gegl_buffer_io=False,
        alpha_carrying_projection=False,
        gegl_rendering=False,
    )

    def render_projection(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
    ) -> np.ndarray:
        """Render the full editable-layer projection."""
        return render_edit_layers(project, source_node, base)

    def render_region(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
    ) -> np.ndarray:
        """Render one dirty region of the editable-layer projection."""
        return render_edit_layers_region(project, source_node, base, rect)

    def render_region_excluding(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
        exclude_layer_id: str,
    ) -> np.ndarray:
        """Render a dirty region while omitting one layer."""
        return render_edit_layers_region_excluding(
            project,
            source_node,
            base,
            rect,
            exclude_layer_id,
        )
