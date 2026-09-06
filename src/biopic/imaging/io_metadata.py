"""Embedded BioPic/REMBI metadata helpers for image import/export."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from PIL import Image
from PIL.PngImagePlugin import PngInfo

BIOPIC_METADATA_KEY = "BioPic:Metadata"
BIOPIC_METADATA_PREFIX = "BioPic Metadata JSON: "
CONTAINER_METADATA_PREFIXES = ("jfif",)
CONTAINER_METADATA_KEYS = {
    "dpi",
    "transparency",
    "duration",
    "loop",
    "progression",
    "icc_profile",
}
REMBI_VERSION = "1.5"


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        clean[str(key)] = _clean_metadata_value(value)
    return clean


def _clean_metadata_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): _clean_metadata_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_clean_metadata_value(item) for item in value]
    return str(value)


def _embedded_metadata_from_text(text: str) -> dict[str, Any]:
    if not text:
        return {}
    if text.startswith(BIOPIC_METADATA_PREFIX):
        text = text[len(BIOPIC_METADATA_PREFIX) :]
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    if isinstance(decoded.get("metadata"), dict):
        decoded = decoded["metadata"]
    return _clean_metadata(decoded)


def image_metadata_text(metadata: dict[str, Any]) -> str:
    clean = export_metadata_payload(metadata)
    payload = json.dumps(
        {"schema": "biopic.metadata.v1", "metadata": clean},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{BIOPIC_METADATA_PREFIX}{payload}"


def image_metadata_xmp(metadata: dict[str, Any]) -> bytes:
    """Return a small XMP packet containing BioPic metadata fields."""
    clean = export_metadata_payload(metadata)
    rembi = rembi_metadata(metadata)
    lines = [
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>',
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
        '<rdf:Description rdf:about="" xmlns:biopic="https://biopic-lm.org/ns/1.0/">',
    ]
    for key, value in clean.items():
        tag = _xmp_tag_name(key)
        text = html.escape(_xmp_value_text(value), quote=False)
        lines.append(f"<biopic:{tag}>{text}</biopic:{tag}>")
    if rembi:
        text = html.escape(_xmp_value_text(rembi), quote=False)
        lines.append(f"<biopic:rembi>{text}</biopic:rembi>")
    lines.extend(
        [
            "</rdf:Description>",
            "</rdf:RDF>",
            "</x:xmpmeta>",
            "<?xpacket end=\"w\"?>",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def image_metadata_tiff_extratags(metadata: dict[str, Any]) -> list[tuple[int, str, int, bytes, bool]]:
    """Return TIFF extra tags for embedded BioPic metadata."""
    xmp = image_metadata_xmp(metadata)
    return [(700, "B", len(xmp), xmp, False)]


def export_metadata_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return file-embedded metadata without transient container fields."""
    clean = _clean_metadata(metadata)
    return {
        key: value
        for key, value in clean.items()
        if not _is_container_metadata_key(key)
    }


def rembi_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return BioPic metadata grouped under REMBI 1.5 section names where possible."""
    clean = export_metadata_payload(metadata)
    rembi: dict[str, Any] = {"rembi_version": REMBI_VERSION}
    biosample: dict[str, Any] = {}
    organism: dict[str, Any] = {}
    specimen: dict[str, Any] = {}
    image_acquisition: dict[str, Any] = {}
    image_data: dict[str, Any] = {}
    study: dict[str, Any] = {}

    _copy_value(clean, "scientific_name", organism, "scientific_name")
    _copy_value(clean, "taxonomy", organism, "ncbi_taxon")
    if organism:
        biosample["organism"] = organism
    _copy_value(clean, "sample_id", biosample, "identity")
    _copy_value(clean, "body_part", biosample, "biological_entity")
    _copy_value(clean, "habitat", biosample, "description")
    intrinsic = _joined_values(clean, ("sex", "life_stage"))
    if intrinsic:
        biosample["intrinsic_variables"] = intrinsic

    _copy_value(clean, "specimen_id", specimen, "identity")
    _copy_value(clean, "preparation", specimen, "sample_preparation")
    _copy_value(clean, "staining", specimen, "signal_or_contrast_mechanism")
    specimen_details = _joined_values(clean, ("orientation", "side", "body_part"))
    if specimen_details:
        specimen["location_within_biosample"] = specimen_details

    _copy_value(clean, "imaging_method", image_acquisition, "imaging_method")
    _copy_value(clean, "microscope", image_acquisition, "imaging_instrument")
    _copy_value(clean, "camera", image_acquisition, "detector")
    _copy_value(clean, "objective", image_acquisition, "objective")
    _copy_value(clean, "magnification", image_acquisition, "nominal_magnification")
    _copy_value(clean, "illumination", image_acquisition, "illumination")

    _copy_value(clean, "physical_pixel_size", image_data, "pixel_voxel_size")
    _copy_value(clean, "physical_pixel_unit", image_data, "pixel_voxel_size_unit")
    _copy_value(clean, "figure_sources", image_data, "related_images")

    _copy_value(clean, "collector", study, "contributors")
    _copy_value(clean, "collection_date", study, "collection_date")
    _copy_value(clean, "locality", study, "collection_locality")
    _copy_value(clean, "latitude", study, "latitude")
    _copy_value(clean, "longitude", study, "longitude")
    _copy_value(clean, "institution", study, "institution")
    _copy_value(clean, "rights", study, "licenses")
    _copy_value(clean, "notes", study, "description")

    if biosample:
        rembi["biosample"] = biosample
    if specimen:
        rembi["specimen"] = specimen
    if image_acquisition:
        rembi["image_acquisition"] = image_acquisition
    if image_data:
        rembi["image_data"] = image_data
    if study:
        rembi["study"] = study
    return rembi if len(rembi) > 1 else {}


def _copy_value(
    source: dict[str, Any],
    source_key: str,
    target: dict[str, Any],
    target_key: str,
) -> None:
    value = source.get(source_key)
    if _has_metadata_value(value):
        target[target_key] = value


def _joined_values(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts = [
        f"{key}: {source[key]}"
        for key in keys
        if _has_metadata_value(source.get(key))
    ]
    return "; ".join(parts)


def _has_metadata_value(value: Any) -> bool:
    return value is not None and value != ""


def _is_container_metadata_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in CONTAINER_METADATA_KEYS or any(
        normalized == prefix or normalized.startswith(f"{prefix}_")
        for prefix in CONTAINER_METADATA_PREFIXES
    )


def _xmp_tag_name(key: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in key)
    if not cleaned:
        return "field"
    if cleaned[0].isdigit():
        return f"field_{cleaned}"
    return cleaned


def _xmp_value_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _write_tiff_metadata(path: Path, metadata: dict[str, Any]) -> None:
    with tifffile.TiffFile(path) as tif:
        pixels = tif.asarray()
        page = tif.pages[0]
        resolution = _tiff_resolution_tuple(page)
        photometric = _tiff_photometric(pixels)
    temp_path = _temporary_sibling(path)
    try:
        kwargs: dict[str, Any] = {
            "description": image_metadata_text(metadata),
            "extratags": image_metadata_tiff_extratags(metadata),
        }
        if resolution is not None:
            kwargs["resolution"] = resolution
        if photometric is not None:
            kwargs["photometric"] = photometric
        tifffile.imwrite(temp_path, pixels, **kwargs)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_png_metadata(path: Path, metadata: dict[str, Any]) -> None:
    with Image.open(path) as image:
        image.load()
        pnginfo = PngInfo()
        for key, value in image.info.items():
            if isinstance(value, str) and key != BIOPIC_METADATA_KEY:
                pnginfo.add_text(key, value)
        pnginfo.add_text(BIOPIC_METADATA_KEY, image_metadata_text(metadata))
        save_kwargs: dict[str, Any] = {"pnginfo": pnginfo}
        if "dpi" in image.info:
            save_kwargs["dpi"] = image.info["dpi"]
        temp_path = _temporary_sibling(path)
        try:
            image.save(temp_path, **save_kwargs)
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _temporary_sibling(path: Path) -> Path:
    return path.with_name(f".{path.stem}.metadata.tmp{path.suffix}")


def _tiff_resolution_tuple(page: Any) -> tuple[tuple[int, int], tuple[int, int]] | None:
    tags = page.tags
    if "XResolution" not in tags or "YResolution" not in tags:
        return None
    return tags["XResolution"].value, tags["YResolution"].value


def _tiff_photometric(pixels: np.ndarray) -> str | None:
    if pixels.ndim >= 3 and pixels.shape[-1] in {3, 4}:
        return "rgb"
    if pixels.ndim >= 2:
        return "minisblack"
    return None


def _tiff_resolution(page: Any) -> dict[str, Any]:
    tags = page.tags
    result: dict[str, Any] = {}
    for name in ("XResolution", "YResolution", "ResolutionUnit"):
        if name in tags:
            result[name] = str(tags[name].value)
    return result

