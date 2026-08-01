"""Temporary result file handling for sharpness comparison."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np

from biopic.export.raster import export_image


class TemporaryResultStore:
    """Create and clean up temporary comparison result images."""

    def __init__(self, project_id: str) -> None:
        self.directory = (Path.cwd() / ".biopic_cache" / project_id / "sharpness_comparison").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.paths: list[Path] = []

    def save(self, method_id: str, image: np.ndarray) -> Path:
        path = self.directory / f"sharpness_comparison_{method_id}_{uuid4().hex}.tif"
        export_image(image, path)
        self.paths.append(path)
        return path

    def cleanup(self) -> None:
        for path in list(self.paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self.paths.clear()
