"""Scientific image import helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from PIL import Image

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


def read_image_asset(path: Path, *, load_pixels: bool = False) -> ImageReadResult:
    """Read metadata and optionally pixels from a supported image file."""
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {path.suffix}")
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix in TIFF_EXTENSIONS:
        asset, pixels = _read_tiff(path, load_pixels)
    elif suffix in RAW_EXTENSIONS:
        asset, pixels = _read_raw(path, load_pixels)
    else:
        asset, pixels = _read_pillow(path, load_pixels)
    asset.checksum = file_checksum(path)
    return ImageReadResult(asset=asset, pixels=pixels)


def import_images(
    project: Project,
    paths: list[Path],
    *,
    kind: ImageAssetKind = ImageAssetKind.DIRECT_IMPORT,
) -> list[ImageAsset]:
    """Import paths as independent source images."""
    assets: list[ImageAsset] = []
    for path in paths:
        result = read_image_asset(path, load_pixels=False)
        result.asset.kind = kind
        project.add_asset(result.asset)
        assets.append(result.asset)
    return assets


def import_stack(
    project: Project, paths: list[Path], kind: StackKind = StackKind.FOCAL
) -> ImageStack:
    """Import paths as an ordered microscopy stack."""
    assets = import_images(project, paths, kind=ImageAssetKind.STACK_SOURCE)
    stack = ImageStack(
        asset_ids=[asset.id for asset in assets],
        kind=kind,
        name=_stack_name(paths, kind),
    )
    project.add_stack(stack)
    return stack


def load_asset_pixels(asset: ImageAsset) -> np.ndarray:
    """Load an asset's pixels from its original path."""
    return read_image_asset(Path(asset.path), load_pixels=True).pixels


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


def _read_raw(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    try:
        import rawpy  # type: ignore[import-untyped]
    except ImportError as exc:
        message = (
            "RAW image support requires optional dependency rawpy; "
            "install BioPic LM with the raw extra."
        )
        raise ValueError(message) from exc

    with rawpy.imread(str(path)) as raw:
        sizes = raw.sizes
        metadata = _clean_metadata(
            {
                "raw_type": type(raw).__name__,
                "black_level_per_channel": tuple(getattr(raw, "black_level_per_channel", ())),
                "camera_whitebalance": tuple(getattr(raw, "camera_whitebalance", ())),
                "daylight_whitebalance": tuple(getattr(raw, "daylight_whitebalance", ())),
                "white_level": getattr(raw, "white_level", None),
            }
        )
        if load_pixels:
            pixels = raw.postprocess(
                output_bps=16,
                no_auto_bright=True,
                use_camera_wb=True,
            )
        else:
            pixels = np.empty((0,), dtype=np.uint16)
    return (
        ImageAsset(
            path=str(path),
            width=int(sizes.width),
            height=int(sizes.height),
            frames=1,
            dtype="uint16",
            color_model="rgb",
            metadata=metadata,
        ),
        pixels,
    )


def _read_pillow(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    with Image.open(path) as image:
        metadata = _clean_metadata(dict(image.info))
        frames = getattr(image, "n_frames", 1)
        dtype = _pillow_dtype(image)
        pixels = np.asarray(image) if load_pixels else np.empty((0,), dtype=np.uint8)
        asset = ImageAsset(
            path=str(path),
            width=image.width,
            height=image.height,
            frames=frames,
            dtype=dtype,
            color_model=_pillow_color_model(image.mode),
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


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)] = value
        elif isinstance(value, tuple):
            clean[str(key)] = [str(item) for item in value]
        else:
            clean[str(key)] = str(value)
    return clean


def _tiff_resolution(page: Any) -> dict[str, Any]:
    tags = page.tags
    result: dict[str, Any] = {}
    for name in ("XResolution", "YResolution", "ResolutionUnit"):
        if name in tags:
            result[name] = str(tags[name].value)
    return result


def _stack_name(paths: list[Path], kind: StackKind) -> str:
    if not paths:
        return f"{kind.value.title()} Stack"
    return f"{paths[0].stem} {kind.value.title()} Stack"
