"""Project schema migrations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def migrate_project_data(data: dict[str, Any], target_version: int) -> dict[str, Any]:
    """Migrate project data to the requested schema version."""
    migrated = deepcopy(data)
    current = int(migrated.get("schema_version", 1))
    if current > target_version:
        raise ValueError(
            f"Project schema {current} is newer than supported schema {target_version}"
        )
    while current < target_version:
        current += 1
        migrated["schema_version"] = current
    return migrated
