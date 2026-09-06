"""Raster image and figure-board export."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import tifffile
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from biopic.imaging.io import (
    BIOPIC_METADATA_KEY,
    image_metadata_text,
    image_metadata_tiff_extratags,
)
from biopic.imaging.project_render import render_project_image
from biopic.export.raster_figure_board import (
    _display_compatible,
    _draw_measurement_overlay,
    _panel_image,
    _render_image_overlays,
    _source_image_metadata,
    export_project_figure_board,
    export_project_figure_board_latex,
    export_simple_figure_board,
)
from biopic.models.project import Project

ExportPrecisionPolicy = Literal["visual", "preserve"]


def export_image(
    image: np.ndarray,
    path: Path,
    *,
    dpi: int = 300,
    precision_policy: ExportPrecisionPolicy = "visual",
    metadata: dict[str, object] | None = None,
) -> None:
    """Export a current image to TIFF/PNG/JPEG/BMP."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        kwargs: dict[str, object] = {"resolution": (dpi, dpi)}
        if metadata:
            kwargs["description"] = image_metadata_text(metadata)
            kwargs["extratags"] = image_metadata_tiff_extratags(metadata)
        tifffile.imwrite(path, image, **kwargs)
        return
    if precision_policy == "preserve" and _requires_display_conversion(image):
        raise ValueError("Use TIFF export to preserve this image's dtype and channel data.")
    pil = Image.fromarray(_display_compatible(image))
    if suffix in {".jpg", ".jpeg"} and pil.mode in {"RGBA", "LA", "P"}:
        pil = pil.convert("RGB")
    save_kwargs: dict[str, object] = {"dpi": (dpi, dpi)}
    if metadata and suffix == ".png":
        pnginfo = PngInfo()
        pnginfo.add_text(BIOPIC_METADATA_KEY, image_metadata_text(metadata))
        save_kwargs["pnginfo"] = pnginfo
    elif metadata and suffix in {".jpg", ".jpeg"}:
        exif = pil.getexif()
        exif[270] = image_metadata_text(metadata)
        save_kwargs["exif"] = exif
    pil.save(path, **save_kwargs)


def export_project_image(
    project: Project,
    node_id: str,
    path: Path,
    *,
    dpi: int = 300,
    precision_policy: ExportPrecisionPolicy = "visual",
    include_overlays: bool = True,
) -> None:
    """Export a rendered project image with source metadata embedded."""
    pixels = render_project_image(project, node_id)
    if pixels is None:
        raise ValueError("The selected image could not be rendered.")
    if include_overlays:
        pixels = _render_image_overlays(project, node_id, pixels)
    metadata = _source_image_metadata(project, node_id)
    export_image(
        pixels,
        path,
        dpi=dpi,
        precision_policy=precision_policy,
        metadata=metadata,
    )


def _requires_display_conversion(image: np.ndarray) -> bool:
    array = np.asarray(image)
    while array.ndim > 3:
        array = array[0]
    if array.ndim == 3 and array.shape[-1] not in {3, 4}:
        return True
    return array.dtype != np.uint8

