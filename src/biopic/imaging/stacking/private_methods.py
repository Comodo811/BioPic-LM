"""Private stacking-method feature gate."""

from __future__ import annotations

import os


def private_stacking_enabled() -> bool:
    """Return whether private stack methods should be exposed."""
    value = os.environ.get("BIOPIC_ENABLE_PRIVATE_STACKING", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}
