"""Atomic project save/load support."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from biopic.imaging.layer_buffers import clear_layer_buffers, sync_layer_buffers_to_payload
from biopic.models.project import PROJECT_SCHEMA_VERSION, Project
from biopic.persistence.project_archive import export_project_archive
from biopic.persistence.schema import migrate_project_data


class ProjectStore:
    """Read and write BioPic LM project manifests."""

    def save(self, project: Project, path: Path) -> None:
        """Atomically save a project as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        for layer in project.edit_layers.values():
            sync_layer_buffers_to_payload(layer)
        archived_paths = export_project_archive(project, path)
        project.touch()
        payload = project.to_dict()
        for asset_payload in payload.get("assets", []):
            if not isinstance(asset_payload, dict):
                continue
            asset_id = asset_payload.get("id")
            if isinstance(asset_id, str) and asset_id in archived_paths:
                asset_payload["path"] = archived_paths[asset_id]
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_name = handle.name
        os.replace(temp_name, path)

    def load(self, path: Path) -> Project:
        """Load a project manifest and apply migrations."""
        clear_layer_buffers()
        with path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = json.load(handle)
        migrated = migrate_project_data(data, PROJECT_SCHEMA_VERSION)
        return Project.from_dict(migrated)
