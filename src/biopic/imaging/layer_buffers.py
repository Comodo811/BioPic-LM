"""Transient layer pixel buffers used by the interactive editor.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np

from biopic.models.editing import EditLayer

_CONTENT_BUFFERS: dict[str, np.ndarray] = {}
_ALPHA_BUFFERS: dict[str, np.ndarray] = {}
_CONTENT_REFS: dict[int, set[str]] = {}
_ALPHA_REFS: dict[int, set[str]] = {}


def set_layer_buffers(layer_id: str, content: np.ndarray, alpha: np.ndarray) -> None:
    """Attach live content/alpha buffers to a layer id."""
    _drop_buffer_refs(layer_id)
    _CONTENT_BUFFERS[layer_id] = content
    _ALPHA_BUFFERS[layer_id] = alpha.astype(np.float32, copy=False)
    _CONTENT_REFS.setdefault(id(_CONTENT_BUFFERS[layer_id]), set()).add(layer_id)
    _ALPHA_REFS.setdefault(id(_ALPHA_BUFFERS[layer_id]), set()).add(layer_id)


def share_layer_buffers(source_layer_id: str, target_layer_id: str) -> bool:
    """Share live buffers between two layers until either layer is edited."""
    content = _CONTENT_BUFFERS.get(source_layer_id)
    alpha = _ALPHA_BUFFERS.get(source_layer_id)
    if content is None or alpha is None:
        return False
    _drop_buffer_refs(target_layer_id)
    _CONTENT_BUFFERS[target_layer_id] = content
    _ALPHA_BUFFERS[target_layer_id] = alpha
    _CONTENT_REFS.setdefault(id(content), set()).update({source_layer_id, target_layer_id})
    _ALPHA_REFS.setdefault(id(alpha), set()).update({source_layer_id, target_layer_id})
    return True


def ensure_unique_layer_buffers(layer_id: str) -> None:
    """Detach copy-on-write live buffers before mutating a layer."""
    content = _CONTENT_BUFFERS.get(layer_id)
    alpha = _ALPHA_BUFFERS.get(layer_id)
    if content is None or alpha is None:
        return
    content_shared = len(_CONTENT_REFS.get(id(content), set())) > 1
    alpha_shared = len(_ALPHA_REFS.get(id(alpha), set())) > 1
    if not content_shared and not alpha_shared:
        return
    set_layer_buffers(
        layer_id,
        content.copy() if content_shared else content,
        alpha.copy() if alpha_shared else alpha,
    )


def layer_content_buffer(layer_id: str) -> np.ndarray | None:
    """Return a live content buffer, if one exists."""
    return _CONTENT_BUFFERS.get(layer_id)


def layer_alpha_buffer(layer_id: str) -> np.ndarray | None:
    """Return a live alpha buffer, if one exists."""
    return _ALPHA_BUFFERS.get(layer_id)


def clear_layer_buffers(layer_id: str | None = None) -> None:
    """Clear one layer's live buffers, or all live layer buffers."""
    if layer_id is None:
        _CONTENT_BUFFERS.clear()
        _ALPHA_BUFFERS.clear()
        _CONTENT_REFS.clear()
        _ALPHA_REFS.clear()
        return
    _drop_buffer_refs(layer_id)
    _CONTENT_BUFFERS.pop(layer_id, None)
    _ALPHA_BUFFERS.pop(layer_id, None)


def sync_layer_buffers_to_payload(layer: EditLayer) -> None:
    """Persist a layer's live buffers into its serializable payload."""
    content = layer_content_buffer(layer.id)
    alpha = layer_alpha_buffer(layer.id)
    if content is not None and not _payload_matches(layer.content_pixels(), content):
        layer.set_content_pixels(content)
    if alpha is not None and not _payload_matches(layer.alpha_pixels(), alpha):
        layer.set_alpha_pixels(alpha)


def _payload_matches(payload: np.ndarray | None, buffer: np.ndarray) -> bool:
    if payload is None:
        return False
    return payload.shape == buffer.shape and payload.dtype == buffer.dtype and np.array_equal(
        payload,
        buffer,
    )


def _drop_buffer_refs(layer_id: str) -> None:
    content = _CONTENT_BUFFERS.get(layer_id)
    alpha = _ALPHA_BUFFERS.get(layer_id)
    if content is not None:
        refs = _CONTENT_REFS.get(id(content))
        if refs is not None:
            refs.discard(layer_id)
            if not refs:
                _CONTENT_REFS.pop(id(content), None)
    if alpha is not None:
        refs = _ALPHA_REFS.get(id(alpha))
        if refs is not None:
            refs.discard(layer_id)
            if not refs:
                _ALPHA_REFS.pop(id(alpha), None)
