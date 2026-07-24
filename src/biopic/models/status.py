"""Shared processing status values."""

from __future__ import annotations

from enum import StrEnum


class NodeStatus(StrEnum):
    """Lifecycle state for a processing node."""

    CURRENT = "current"
    MODIFIED = "modified"
    PROCESSING = "processing"
    STALE = "stale"
    FAILED = "failed"
    COMPLETE = "complete"
