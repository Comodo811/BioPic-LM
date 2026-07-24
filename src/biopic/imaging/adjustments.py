"""Non-destructive adjustment-layer rendering.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

from biopic.imaging.editing import apply_edit_operation
from biopic.models.editing import AdjustmentLayer


def render_adjustment_pipeline(
    base_image: np.ndarray, layers: list[AdjustmentLayer]
) -> np.ndarray:
    """Render enabled adjustment layers from the unmodified base image."""
    rendered = np.asarray(base_image).copy()
    for layer in sorted(layers, key=lambda item: item.order):
        if not layer.enabled:
            continue
        next_image = apply_edit_operation(rendered, layer.operation, layer.parameters)
        if layer.opacity >= 0.999:
            rendered = next_image
        else:
            rendered = _blend_normal(rendered, next_image, layer.opacity)
    return rendered


def adjustment_pipeline_cache_key(
    source_key: str, layers: list[AdjustmentLayer], *, renderer_version: int = 1
) -> str:
    """Build a stable cache key for a source image and adjustment stack."""
    payload = {
        "source": source_key,
        "renderer_version": renderer_version,
        "layers": [
            {
                "id": layer.id,
                "operation": layer.operation,
                "parameters": layer.parameters,
                "enabled": layer.enabled,
                "opacity": layer.opacity,
                "blend_mode": layer.blend_mode.value,
                "mask_node_id": layer.mask_node_id,
                "algorithm_version": layer.algorithm_version,
                "order": layer.order,
                "modified_at": layer.modified_at,
            }
            for layer in sorted(layers, key=lambda item: item.order)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _blend_normal(base: np.ndarray, adjusted: np.ndarray, opacity: float) -> np.ndarray:
    amount = float(np.clip(opacity, 0.0, 1.0))
    blended = np.asarray(base).astype(np.float32) * (1.0 - amount)
    blended += np.asarray(adjusted).astype(np.float32) * amount
    if np.issubdtype(np.asarray(base).dtype, np.integer):
        info = np.iinfo(np.asarray(base).dtype)
        return np.clip(blended, info.min, info.max).astype(np.asarray(base).dtype)
    return blended.astype(np.asarray(base).dtype, copy=False)
