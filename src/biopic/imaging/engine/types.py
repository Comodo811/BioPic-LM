"""Shared image-engine data structures.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from biopic.models.project import Project


Rect = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Feature switches for the active image-editing backend."""

    tiled_drawables: bool
    graph_projection: bool
    dirty_region_projection: bool
    native_compositing: bool
    gegl_available: bool
    gegl_buffer_io: bool
    alpha_carrying_projection: bool
    gegl_rendering: bool


@dataclass(frozen=True, slots=True)
class EngineStatus:
    """Human-readable backend status for diagnostics and future UI display."""

    active_backend: str
    gegl_library: str | None
    babl_library: str | None
    gi_available: bool
    gegl_reason: str


class ProjectionBackend(Protocol):
    """Backend contract for GIMP-like document projection."""

    name: str
    capabilities: EngineCapabilities

    def render_projection(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
    ) -> np.ndarray:
        """Render the full layer projection."""

    def render_region(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
    ) -> np.ndarray:
        """Render a dirty projection region."""

    def render_region_excluding(
        self,
        project: Project,
        source_node: str,
        base: np.ndarray,
        rect: Rect,
        exclude_layer_id: str,
    ) -> np.ndarray:
        """Render a dirty region while excluding one layer."""
