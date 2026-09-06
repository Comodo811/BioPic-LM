"""Scientific image import helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
import tifffile
from PIL import Image, ImageOps

from biopic.imaging.io_metadata import (
    BIOPIC_METADATA_KEY,
    _clean_metadata,
    _embedded_metadata_from_text,
    _tiff_resolution,
    _write_png_metadata,
    _write_tiff_metadata,
    export_metadata_payload,
    image_metadata_text,
    image_metadata_tiff_extratags,
    image_metadata_xmp,
    rembi_metadata,
)
from biopic.imaging.io_raw import (
    RAW_DECODE_RAWPY,
    RAW_DECODE_WIC_DISPLAY,
    RAW_STACK_BRIGHTNESS,
    _decode_wic_32bpp_bgra,
    _read_raw,
)
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack, StackKind
from biopic.models.project import Project

TIFF_EXTENSIONS = {".tif", ".tiff"}
RAW_EXTENSIONS = {
    ".3fr",
    ".ari",
    ".arw",
    ".bay",
    ".cr2",
    ".cr3",
    ".crw",
    ".dcr",
    ".dng",
    ".erf",
    ".fff",
    ".iiq",
    ".k25",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rw2",
    ".rwl",
    ".sr2",
    ".srf",
    ".srw",
    ".x3f",
}
SUPPORTED_EXTENSIONS = TIFF_EXTENSIONS | RAW_EXTENSIONS | {".png", ".jpg", ".jpeg", ".bmp"}
@dataclass(frozen=True, slots=True)
class ImageReadResult:
    """Loaded image pixels plus the project asset record."""

    asset: ImageAsset
    pixels: np.ndarray


def read_image_asset(
    path: Path,
    *,
    load_pixels: bool = False,
    raw_decode_mode: str = RAW_DECODE_RAWPY,
) -> ImageReadResult:
    """Read metadata and optionally pixels from a supported image file."""
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {path.suffix}")
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix in TIFF_EXTENSIONS:
        asset, pixels = _read_tiff(path, load_pixels)
    elif suffix in RAW_EXTENSIONS:
        asset, pixels = _read_raw(path, load_pixels, decode_mode=raw_decode_mode)
    else:
        asset, pixels = _read_pillow(path, load_pixels)
    asset.checksum = file_checksum(path)
    return ImageReadResult(asset=asset, pixels=pixels)


def import_images(
    project: Project,
    paths: list[Path],
    *,
    kind: ImageAssetKind = ImageAssetKind.DIRECT_IMPORT,
    progress: Callable[[int, int, Path], None] | None = None,
) -> list[ImageAsset]:
    """Import paths as independent source images."""
    assets: list[ImageAsset] = []
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        result = read_image_asset(path, load_pixels=False)
        result.asset.kind = kind
        project.add_asset(result.asset)
        assets.append(result.asset)
        if progress is not None:
            progress(index, total, path)
    return assets


def import_stack(
    project: Project,
    paths: list[Path],
    kind: StackKind = StackKind.FOCAL,
    *,
    progress: Callable[[int, int, Path], None] | None = None,
) -> ImageStack:
    """Import paths as an ordered microscopy stack."""
    assets = import_images(
        project,
        paths,
        kind=ImageAssetKind.STACK_SOURCE,
        progress=progress,
    )
    stack = ImageStack(
        asset_ids=[asset.id for asset in assets],
        kind=kind,
        name=_stack_name(paths, kind),
    )
    project.add_stack(stack)
    return stack


def load_asset_pixels(
    asset: ImageAsset,
    *,
    raw_decode_mode: str = RAW_DECODE_RAWPY,
) -> np.ndarray:
    """Load an asset's pixels from its original path."""
    return read_image_asset(
        Path(asset.path),
        load_pixels=True,
        raw_decode_mode=raw_decode_mode,
    ).pixels


def write_image_metadata(path: Path, metadata: dict[str, Any]) -> bool:
    """Embed BioPic metadata into a supported image file without changing pixel values.

    TIFF and PNG can be rewritten losslessly with text metadata. Existing JPEG files are
    intentionally not rewritten here because Pillow would re-encode the image data.
    """
    suffix = path.suffix.lower()
    if not path.exists() or suffix in RAW_EXTENSIONS:
        return False
    clean = export_metadata_payload(metadata)
    if not clean:
        return False
    if suffix in TIFF_EXTENSIONS:
        _write_tiff_metadata(path, clean)
        return True
    if suffix == ".png":
        _write_png_metadata(path, clean)
        return True
    return False


def file_checksum(path: Path, algorithm: str = "sha256") -> str:
    """Return a checksum without loading the whole file into memory."""
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"{algorithm}:{hasher.hexdigest()}"


def _read_tiff(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        shape = series.shape
        dtype = str(series.dtype)
        axes = series.axes
        height, width = _shape_to_hw(shape, axes)
        frames = _frame_count(shape, axes)
        metadata = _clean_metadata(tif.imagej_metadata or {})
        first_page = tif.pages[0]
        description = getattr(first_page, "description", None)
        if description:
            metadata["image_description"] = str(description)
            metadata.update(_embedded_metadata_from_text(str(description)))
        resolution = _tiff_resolution(first_page)
        if resolution:
            metadata.update(resolution)
        pixels = (
            _read_tiff_pixels(path)
            if load_pixels
            else np.empty((0,), dtype=series.dtype)
        )
    return (
        ImageAsset(
            path=str(path),
            width=width,
            height=height,
            frames=frames,
            dtype=dtype,
            color_model=_color_model(shape, axes),
            metadata=metadata,
        ),
        pixels,
    )


def _read_tiff_pixels(path: Path) -> np.ndarray:
    try:
        return tifffile.memmap(path)
    except (ValueError, OSError, TypeError, tifffile.TiffFileError):
        with tifffile.TiffFile(path) as tif:
            return tif.asarray()

def _read_pillow(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    with Image.open(path) as image:
        metadata = _clean_metadata(dict(image.info))
        metadata.update(_embedded_metadata_from_text(str(metadata.get(BIOPIC_METADATA_KEY, ""))))
        frames = getattr(image, "n_frames", 1)
        oriented = ImageOps.exif_transpose(image)
        dtype = _pillow_dtype(oriented)
        pixels = np.asarray(oriented) if load_pixels else np.empty((0,), dtype=np.uint8)
        asset = ImageAsset(
            path=str(path),
            width=oriented.width,
            height=oriented.height,
            frames=frames,
            dtype=dtype,
            color_model=_pillow_color_model(oriented.mode),
            metadata=metadata,
        )
    return asset, pixels


def _shape_to_hw(shape: tuple[int, ...], axes: str) -> tuple[int, int]:
    if "Y" in axes and "X" in axes:
        return int(shape[axes.index("Y")]), int(shape[axes.index("X")])
    if len(shape) < 2:
        raise ValueError(f"Image data does not have two spatial dimensions: {shape}")
    return int(shape[-2]), int(shape[-1])


def _frame_count(shape: tuple[int, ...], axes: str) -> int:
    count = 1
    for axis, size in zip(axes, shape, strict=False):
        if axis not in {"Y", "X", "S"}:
            count *= int(size)
    return count


def _color_model(shape: tuple[int, ...], axes: str) -> str:
    if "S" in axes and shape[axes.index("S")] in {3, 4}:
        return "rgba" if shape[axes.index("S")] == 4 else "rgb"
    return "grayscale"


def _pillow_dtype(image: Image.Image) -> str:
    if image.mode in {"I;16", "I;16L", "I;16B"}:
        return "uint16"
    if image.mode in {"I"}:
        return "int32"
    if image.mode == "F":
        return "float32"
    return "uint8"


def _pillow_color_model(mode: str) -> str:
    if mode in {"RGB", "RGBA"}:
        return mode.lower()
    return "grayscale"

def _stack_name(paths: list[Path], kind: StackKind) -> str:
    if not paths:
        return f"{kind.value.title()} Stack"
    return f"{paths[0].stem} {kind.value.title()} Stack"
