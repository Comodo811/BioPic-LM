"""GIMP-inspired image document/projection facade.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np

from biopic.imaging.core import CoreImage, core_image_from_project
from biopic.imaging.engine.gegl_buffer_store import GeglDrawableBuffer
from biopic.imaging.engine.gegl_backend import detect_gegl_runtime, status_for_backend
from biopic.imaging.engine.gegl_ctypes import GeglCtypesBridge, GeglCtypesError
from biopic.imaging.engine.gegl_projection import (
    ProjectionState,
    render_normal_layers,
    render_normal_layers_region,
    render_projection_state,
)
from biopic.imaging.engine.numpy_backend import NumpyProjectionBackend
from biopic.imaging.engine.types import EngineCapabilities, EngineStatus, ProjectionBackend, Rect
from biopic.models.project import Project


class ImageEditingEngine:
    """Stable boundary between tools/UI and the editable document projection.

    The current backend is the native-assisted NumPy implementation. GEGL is
    detected here, but only selected after a real graph renderer is available.
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self._gegl_runtime = detect_gegl_runtime()
        self._backend: ProjectionBackend = NumpyProjectionBackend()
        self._gegl_bridge: GeglCtypesBridge | None = None
        self._gegl_bridge_error: str | None = None

    @property
    def backend_name(self) -> str:
        """Return the active projection backend name."""
        return self._backend.name

    @property
    def capabilities(self) -> EngineCapabilities:
        """Return active backend capabilities plus GEGL detection state."""
        active = self._backend.capabilities
        return EngineCapabilities(
            tiled_drawables=active.tiled_drawables,
            graph_projection=active.graph_projection,
            dirty_region_projection=active.dirty_region_projection,
            native_compositing=active.native_compositing,
            gegl_available=self._gegl_runtime.dll_available,
            gegl_buffer_io=self._gegl_runtime.dll_available,
            alpha_carrying_projection=self._gegl_runtime.dll_available,
            gegl_rendering=active.gegl_rendering,
        )

    @property
    def status(self) -> EngineStatus:
        """Return backend status suitable for diagnostics."""
        return status_for_backend(self.backend_name, self._gegl_runtime)

    def render_projection(self, source_node: str, base: np.ndarray) -> np.ndarray:
        """Render the complete image projection from editable layers."""
        return self._backend.render_projection(self.project, source_node, base)

    def render_region(
        self,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
    ) -> np.ndarray:
        """Render a dirty region of the image projection."""
        return self._backend.render_region(self.project, source_node, base, rect)

    def render_region_excluding(
        self,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
        exclude_layer_id: str,
    ) -> np.ndarray:
        """Render a dirty region while one layer is temporarily omitted."""
        return self._backend.render_region_excluding(
            self.project,
            source_node,
            base,
            rect,
            exclude_layer_id,
        )

    def create_gegl_drawable(self, pixels: np.ndarray) -> GeglDrawableBuffer:
        """Create an independently addressable GEGL drawable buffer."""
        bridge = self._gegl_ctypes_bridge()
        return GeglDrawableBuffer.from_array(pixels, bridge=bridge)

    def render_projection_gegl_experimental(
        self,
        source_node: str,
        base: np.ndarray,
    ) -> np.ndarray:
        """Render the normal-layer projection with GEGL.

        This is not the default renderer yet because group layers, non-normal
        blend modes and full mask semantics still need parity work.
        """
        return render_normal_layers(
            self.project,
            source_node,
            base,
            bridge=self._gegl_ctypes_bridge(),
        )

    def render_projection_state_gegl_experimental(
        self,
        source_node: str,
        base: np.ndarray,
    ) -> ProjectionState:
        """Render an alpha-carrying GEGL-style projection state."""
        return render_projection_state(
            self.project,
            source_node,
            base,
            bridge=self._gegl_ctypes_bridge(),
        )

    def core_image(self, source_node: str, base: np.ndarray) -> CoreImage:
        """Build a GIMP-like core image document for the current source."""
        return core_image_from_project(self.project, source_node, base)

    def render_region_gegl_experimental(
        self,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
    ) -> np.ndarray:
        """Render a normal-layer dirty region with GEGL."""
        return render_normal_layers_region(
            self.project,
            source_node,
            base,
            rect,
            bridge=self._gegl_ctypes_bridge(),
        )

    def _gegl_ctypes_bridge(self) -> GeglCtypesBridge:
        if self._gegl_bridge is not None:
            return self._gegl_bridge
        if self._gegl_bridge_error is not None:
            raise GeglCtypesError(self._gegl_bridge_error)
        try:
            self._gegl_bridge = GeglCtypesBridge()
        except GeglCtypesError as exc:
            self._gegl_bridge_error = str(exc)
            raise
        return self._gegl_bridge
