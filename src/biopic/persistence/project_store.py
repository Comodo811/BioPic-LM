"""Atomic project save/load support."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from biopic.imaging.layer_buffers import clear_layer_buffers, sync_layer_buffers_to_payload
from biopic.models.image_asset import ImageAsset
from biopic.models.project import PROJECT_SCHEMA_VERSION, Project
from biopic.persistence.project_archive import (
    ProjectSaveOptions,
    export_project_archive,
    project_archive_step_count,
    project_folder_for_manifest,
    relative_project_path,
)
from biopic.persistence.schema import migrate_project_data


ProjectSaveProgress = Callable[[int, int, Path, str], None]


class ProjectStore:
    """Read and write BioPic LM project manifests."""

    def save(
        self,
        project: Project,
        path: Path,
        *,
        save_options: ProjectSaveOptions | None = None,
        progress: ProjectSaveProgress | None = None,
    ) -> None:
        """Atomically save a project as JSON."""
        save_options = save_options or ProjectSaveOptions()
        path.parent.mkdir(parents=True, exist_ok=True)
        for layer in project.edit_layers.values():
            sync_layer_buffers_to_payload(layer)
        save_options_payload = save_options.to_dict()
        skip_archive = path.exists() and not project.archive_is_dirty(save_options_payload)
        total_steps = 1 if skip_archive else max(
            1,
            project_archive_step_count(project, path, save_options) + 1,
        )
        completed_steps = 0

        def advance_progress(current_path: Path, action: str) -> None:
            nonlocal completed_steps
            completed_steps = min(total_steps, completed_steps + 1)
            if progress is not None:
                progress(completed_steps, total_steps, current_path, action)

        archived_paths = (
            {asset.id: asset.path for asset in project.assets.values()}
            if skip_archive
            else export_project_archive(
                project,
                path,
                save_options,
                progress=advance_progress,
            )
        )
        if not skip_archive:
            project.touch()
        payload = project.to_dict()
        payload["undo_stack"] = []
        payload["redo_stack"] = []
        payload["storage"] = {
            "mode": "self_contained_folder",
            "asset_folder": relative_project_path(project_folder_for_manifest(path), path),
            "save_options": save_options.to_dict(),
        }
        for asset_payload in payload.get("assets", []):
            if not isinstance(asset_payload, dict):
                continue
            asset_id = asset_payload.get("id")
            if isinstance(asset_id, str) and asset_id in archived_paths:
                asset = project.assets.get(asset_id)
                if asset is not None and not asset_payload.get("display_name"):
                    asset_payload["display_name"] = Path(asset.path).name
                asset_payload["path"] = relative_project_path(Path(archived_paths[asset_id]), path)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_name = handle.name
        os.replace(temp_name, path)
        project.mark_archive_clean(save_options_payload)
        advance_progress(path, "Saving project manifest")

    def load(self, path: Path) -> Project:
        """Load a project manifest and apply migrations."""
        clear_layer_buffers()
        with path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = json.load(handle)
        migrated = migrate_project_data(data, PROJECT_SCHEMA_VERSION)
        project = Project.from_dict(migrated)
        _resolve_asset_paths(project, path)
        storage = migrated.get("storage", {})
        if isinstance(storage, dict):
            save_options = storage.get("save_options")
            if isinstance(save_options, dict):
                project.mark_archive_clean(save_options)
        return project


def _resolve_asset_paths(project: Project, manifest_path: Path) -> None:
    """Resolve project-relative asset paths after loading a self-contained project."""
    base_dir = manifest_path.parent
    for asset in project.assets.values():
        asset.path = _resolve_asset_path(asset, base_dir)


def _resolve_asset_path(asset: ImageAsset, base_dir: Path) -> str:
    path = Path(asset.path)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())
