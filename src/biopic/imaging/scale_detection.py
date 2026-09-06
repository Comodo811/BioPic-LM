"""Scale calibration helpers for ruler and stage-micrometer images."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from biopic.imaging.scale_detection_preprocess import (
    _crop_constant_dark_border,
    _estimate_rotation_by_projection,
    _period_from_projection,
    _prepared_gray,
    _projection_alignment_score,
    _stripe_positions_from_projection,
)

@dataclass(frozen=True, slots=True)
class StripeDetection:
    spacing_pixels: float
    axis: str
    confidence: float
    stripe_positions: tuple[float, ...]
    orientation_confidence: float = 0.0
    candidate_tick_count: int = 0
    refined_tick_count: int = 0
    inlier_tick_count: int = 0
    spacing_rms_error: float = 0.0
    pixels_per_micrometer: float = 0.0
    micrometers_per_pixel: float = 0.0
    tick_angle_degrees: float = 0.0
    tick_angle_std_degrees: float = 0.0
    tick_marks: tuple[dict[str, float | str], ...] = ()


@dataclass(frozen=True, slots=True)
class ScaleOrientation:
    axis: str
    profile_axis: int
    confidence: float
    period_hint: float
    tick_angle_degrees: float = 0.0
    tick_angle_std_degrees: float = 0.0


@dataclass(frozen=True, slots=True)
class ScaleCoordinateSystem:
    tick_angle_degrees: float
    normal_x: float
    normal_y: float
    tangent_x: float
    tangent_y: float
    u_min: float
    u_max: float
    v_min: float
    v_max: float


@dataclass(frozen=True, slots=True)
class TickCandidate:
    index: int
    prominence: float
    width: float


@dataclass(frozen=True, slots=True)
class RefinedTick:
    center: float
    confidence: float
    left_edge: float | None = None
    right_edge: float | None = None
    residual: float = 0.0
    inlier: bool = True
    length: float = 0.0
    tick_class: str = "small"


@dataclass(frozen=True, slots=True)
class TickLatticeFit:
    spacing: float
    origin: float
    rms_error: float
    inlier_mask: tuple[bool, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class StripeAlignment:
    angle_degrees: float
    center: tuple[float, float] | None
    confidence: float


def infer_scale_metadata_from_filename(path: str | Path) -> dict[str, str]:
    """Infer likely equipment, magnification and immersion-fluid tokens from a file name."""
    filename = Path(path).stem
    text = _normalize_filename_text(filename)
    result: dict[str, str] = {}
    if magnification := _detect_magnification(text):
        result["magnification"] = magnification
    result["fluid"] = _detect_immersion_fluid(text) or "Air"
    if microscope := _detect_microscope(text):
        result["microscope"] = microscope
    if camera := _detect_camera(text):
        result["camera"] = camera
    return result


def _normalize_filename_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip()


def _detect_magnification(text: str) -> str | None:
    match = re.search(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:x|×)(?=$|[^a-z0-9]|(?:oil|water|air|glycerol|silicone))",
        text,
        re.I,
    )
    if match is None:
        match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:obj|objective)", text, re.I)
    if match is None:
        return None
    return f"{match.group(1).replace(',', '.')}x"


def _detect_immersion_fluid(text: str) -> str | None:
    compact = re.sub(r"[^a-z0-9]+", "", text.casefold())
    spaced = f" {_normalize_filename_text(text).casefold()} "
    if (
        re.search(r"(?:^|[^a-z])oil(?:$|[^a-z])", spaced)
        or "immersionoil" in compact
        or re.search(r"\d+(?:[.,]\d+)?x(?:immersion)?oil", compact)
    ):
        return "Oil"
    if (
        re.search(r"(?:^|[^a-z])water(?:$|[^a-z])", spaced)
        or "waterimmersion" in compact
        or re.search(r"\d+(?:[.,]\d+)?xwater", compact)
    ):
        return "Water"
    if "glycerol" in compact or "glycerine" in compact:
        return "Glycerol"
    if "siliconeoil" in compact or "silicone" in compact:
        return "Silicone oil"
    if re.search(r"(?:^|[^a-z])air(?:$|[^a-z])", spaced):
        return "Air"
    return None


def _detect_microscope(text: str) -> str | None:
    haystack = _normalized_match_text(text)
    best: tuple[int, str] | None = None
    for manufacturer, model in _microscope_model_entries():
        model_key = _normalized_match_text(model)
        if not model_key or model_key not in haystack:
            continue
        candidate = f"{manufacturer} {model}" if manufacturer.casefold() not in model.casefold() else model
        score = len(model_key)
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is not None:
        return best[1]
    tokens = set(_tokenize_equipment_text(text))
    for manufacturer, aliases in _microscope_manufacturer_aliases().items():
        if any(alias in tokens for alias in aliases):
            return manufacturer
    return None


def _detect_camera(text: str) -> str | None:
    normalized = _normalize_filename_text(text)
    compact = _normalized_match_text(normalized)
    if catalogue_match := _detect_catalogue_camera(text):
        return catalogue_match
    patterns = [
        ("Canon", r"\bcanon\b\s*(?:eos\s*)?([a-z0-9 ]{2,20})?"),
        ("Nikon", r"\bnikon\b\s*([a-z0-9 ]{2,20})?"),
        ("Sony", r"\bsony\b\s*([a-z0-9 ]{2,20})?"),
        ("Olympus", r"\bolympus\b\s*([a-z0-9 ]{2,20})?"),
        ("Leica", r"\bleica\b\s*(?:dmc|dfc|m|mc)\s*([a-z0-9 ]{1,12})?"),
        ("ZEISS", r"\b(?:zeiss|axiocam)\b\s*([a-z0-9 ]{1,16})?"),
        ("Motic", r"\bmoticam\b\s*([a-z0-9 ]{1,12})?"),
        ("AmScope", r"\bamscope\b\s*(?:mu|md)\s*([a-z0-9 ]{1,12})?"),
    ]
    for brand, pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match is None:
            continue
        model = _clean_camera_model(match.group(1) or "")
        if brand == "Canon" and ("canoneos" in compact or re.search(r"\beos\b", normalized, re.I)):
            return f"Canon EOS {model}".strip()
        return f"{brand} {model}".strip()
    eos = re.search(r"\beos\s*([a-z0-9 ]{2,16})", normalized, re.I)
    if eos is not None:
        return f"Canon EOS {_clean_camera_model(eos.group(1) or '')}".strip()
    return None


def _detect_catalogue_camera(text: str) -> str | None:
    haystack = _normalized_match_text(text)
    best: tuple[int, str] | None = None
    for manufacturer, model in _camera_model_entries():
        model_key = _normalized_match_text(model)
        if not model_key or model_key not in haystack:
            continue
        candidate = _camera_candidate_name(manufacturer, model)
        score = len(model_key)
        if best is None or score > best[0]:
            best = (score, candidate)
    return None if best is None else best[1]


def _camera_candidate_name(manufacturer: str, model: str) -> str:
    brand = _camera_display_manufacturer(manufacturer, model)
    if brand.casefold() in model.casefold():
        return model
    return f"{brand} {model}".strip()


def _camera_display_manufacturer(manufacturer: str, model: str) -> str:
    text = manufacturer.strip()
    first = text.split("/")[0].strip()
    aliases = {
        "ZEISS": "ZEISS",
        "Carl Zeiss Microscopy": "ZEISS",
        "Olympus": "Olympus",
        "Evident Scientific": "Evident",
        "Leica Microsystems": "Leica",
        "Hamamatsu Photonics": "Hamamatsu",
        "Andor Technology": "Andor",
        "Photometrics": "Photometrics",
        "PCO": "PCO",
        "Canon": "Canon",
        "Nikon consumer": "Nikon",
        "Sony": "Sony",
    }
    for prefix, display in aliases.items():
        if first.casefold().startswith(prefix.casefold()):
            return display
    if model.casefold().startswith(("eos ", "eos")):
        return "Canon"
    return first


def _clean_camera_model(value: str) -> str:
    value = re.sub(r"(?<!\d)\d+(?:[.,]\d+)?\s*(?:x|×).*$", "", value, flags=re.I)
    value = re.sub(
        r"\b(?:oil|water|air|glycerol|silicone|objective|obj|scale|calibration)\b.*$",
        "",
        value,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", value).strip()


def _normalized_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _tokenize_equipment_text(value: str) -> list[str]:
    return [token.casefold() for token in re.split(r"[^A-Za-z0-9]+", value) if token]


@lru_cache(maxsize=1)
def _microscope_model_entries() -> tuple[tuple[str, str], ...]:
    try:
        data = resources.files("biopic.data").joinpath("microscope_models.json").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return ()
    import json

    payload = json.loads(data)
    entries: list[tuple[str, str]] = []
    for manufacturer in payload.get("manufacturers", []):
        name = str(manufacturer.get("manufacturer", "")).strip()
        short_name = name.split("/")[0].strip()
        for model in manufacturer.get("models", []):
            model_text = str(model).strip()
            if model_text:
                entries.append((short_name, model_text))
    entries.sort(key=lambda item: len(_normalized_match_text(item[1])), reverse=True)
    return tuple(entries)


@lru_cache(maxsize=1)
def _camera_model_entries() -> tuple[tuple[str, str], ...]:
    try:
        data = resources.files("biopic.data").joinpath("camera_models.json").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return ()
    import json

    payload = json.loads(data)
    entries: list[tuple[str, str]] = []
    for manufacturer in payload.get("manufacturers", []):
        name = str(manufacturer.get("manufacturer", "")).strip()
        for model in manufacturer.get("models", []):
            model_text = str(model).strip()
            if model_text:
                entries.append((name, model_text))
    entries.sort(key=lambda item: len(_normalized_match_text(item[1])), reverse=True)
    return tuple(entries)


@lru_cache(maxsize=1)
def _microscope_manufacturer_aliases() -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for manufacturer, _model in _microscope_model_entries():
        names = {
            token.casefold()
            for token in re.split(r"[^A-Za-z0-9]+", manufacturer)
            if len(token) >= 3
        }
        if manufacturer.casefold().startswith("zeiss"):
            names.update({"zeiss"})
        if manufacturer.casefold().startswith("leica"):
            names.update({"leica", "leitz"})
        if names:
            aliases.setdefault(manufacturer, set()).update(names)
    return aliases


def detect_scale_stripe_spacing(
    pixels: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
) -> tuple[float, str, float]:
    """Return estimated stripe spacing in source pixels, axis, and confidence."""
    detection = detect_scale_stripe_pattern(pixels, roi)
    return detection.spacing_pixels, detection.axis, detection.confidence


def detect_scale_stripe_pattern(
    pixels: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
) -> StripeDetection:
    """Return periodic stripe spacing and subpixel tick center positions."""
    gray, scale = _prepared_gray(pixels, roi)
    if gray.size == 0:
        raise ValueError("image is empty")
    detections = [
        result
        for result in (
            _detect_stripes_for_orientation(
                gray,
                ScaleOrientation("vertical stripes", 0, 1.0, 0.0),
            ),
            _detect_stripes_for_orientation(
                gray,
                ScaleOrientation("horizontal stripes", 1, 1.0, 0.0),
            ),
        )
        if result is not None
    ]
    if not detections:
        raise ValueError("could not detect periodic scale stripes")
    detections.sort(key=lambda item: item[0], reverse=True)
    (
        _score,
        orientation,
        _profile,
        geometry,
        candidates,
        refined,
        lattice,
        inlier_ticks,
    ) = detections[0]
    lengths = estimate_tick_lengths(gray, orientation, inlier_ticks, geometry)
    classified = classify_tick_sizes(inlier_ticks, lengths)
    positions = tuple(tick.center / scale for tick in classified)
    spacing = lattice.spacing / scale
    diagnostics = compute_scale_calibration(spacing)
    tick_marks = tuple(_tick_mark_dict(tick, geometry, scale) for tick in classified)
    positions = tuple(
        float(mark["x" if orientation.axis == "vertical stripes" else "y"])
        for mark in tick_marks
    )
    confidence = max(
        0.0,
        orientation.confidence
        * lattice.confidence
        * min(3.0, len(inlier_ticks) / 8.0)
        / max(1.0, lattice.rms_error + 0.25),
    )
    return StripeDetection(
        spacing_pixels=spacing,
        axis=orientation.axis,
        confidence=confidence,
        stripe_positions=positions,
        orientation_confidence=orientation.confidence,
        candidate_tick_count=len(candidates),
        refined_tick_count=len(refined),
        inlier_tick_count=len(inlier_ticks),
        spacing_rms_error=lattice.rms_error / scale,
        pixels_per_micrometer=diagnostics["pixels_per_micrometer"],
        micrometers_per_pixel=diagnostics["micrometers_per_pixel"],
        tick_angle_degrees=orientation.tick_angle_degrees,
        tick_angle_std_degrees=orientation.tick_angle_std_degrees,
        tick_marks=tick_marks,
    )


def confidence_label(confidence: float) -> str:
    """Return an easy confidence description for a numeric stripe-detection score."""
    if confidence >= 80:
        return "excellent"
    if confidence >= 30:
        return "strong"
    if confidence >= 12:
        return "usable"
    if confidence >= 5:
        return "weak"
    return "poor"


def reference_overlay_lengths(pixels_per_unit: float) -> list[tuple[float, float]]:
    """Return 100, 50, and 10 unit reference lengths in pixels."""
    if pixels_per_unit <= 0:
        return []
    return [(length, length * pixels_per_unit) for length in (100.0, 50.0, 10.0)]


def snapped_measurement_endpoint(
    start: tuple[float, float],
    cursor: tuple[float, float],
    *,
    free_angle: bool = False,
) -> tuple[tuple[float, float], str]:
    """Return the endpoint snapped to horizontal/vertical unless free-angle is enabled."""
    if free_angle:
        return cursor, "free"
    dx = cursor[0] - start[0]
    dy = cursor[1] - start[1]
    if abs(dx) >= abs(dy):
        return (cursor[0], start[1]), "horizontal"
    return (start[0], cursor[1]), "vertical"


def measurement_metrics(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    unit_per_pixel: float | None = None,
) -> dict[str, float]:
    """Return pixel distance, normalized angle, and optional physical distance."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = float(np.hypot(dx, dy))
    angle = float(np.degrees(np.arctan2(dy, dx)))
    while angle > 90.0:
        angle -= 180.0
    while angle < -90.0:
        angle += 180.0
    result = {"distance_pixels": distance, "angle_degrees": angle}
    if unit_per_pixel is not None and unit_per_pixel > 0:
        result["distance_physical"] = distance * unit_per_pixel
    return result


def robust_rotation_from_segments(
    segments: list[tuple[float, float, float, float]],
) -> tuple[float, float]:
    """Estimate one correction angle from reliable line segments.

    Returns angle in degrees and total accepted segment length.
    """
    candidates: list[tuple[float, float, str]] = []
    for x1, y1, x2, y2 in segments:
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length <= 0:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        while angle > 90.0:
            angle -= 180.0
        while angle < -90.0:
            angle += 180.0
        if abs(angle) <= 45.0:
            deviation = angle
            group = "horizontal"
        else:
            target = 90.0 if angle > 0 else -90.0
            deviation = angle - target
            group = "vertical"
        candidates.append((deviation, length, group))
    if not candidates:
        raise ValueError("could not detect reliable stripe orientation")
    lengths = np.array([item[1] for item in candidates], dtype=np.float32)
    min_length = max(float(np.percentile(lengths, 65.0)) * 0.55, float(lengths.max()) * 0.20)
    filtered = [item for item in candidates if item[1] >= min_length]
    if not filtered:
        raise ValueError("could not detect reliable stripe orientation")
    deviations = np.array([item[0] for item in filtered], dtype=np.float32)
    median = float(np.median(deviations))
    mad = float(np.median(np.abs(deviations - median)))
    tolerance = max(1.5, 3.5 * mad)
    filtered = [item for item in filtered if abs(item[0] - median) <= tolerance]
    if not filtered:
        raise ValueError("stripe orientation estimates disagree")
    groups: dict[str, list[tuple[float, float, str]]] = {
        "horizontal": [item for item in filtered if item[2] == "horizontal"],
        "vertical": [item for item in filtered if item[2] == "vertical"],
    }
    group_estimates: list[tuple[float, float]] = []
    for group_items in groups.values():
        if not group_items:
            continue
        weight_sum = sum(item[1] for item in group_items)
        estimate = sum(item[0] * item[1] for item in group_items) / weight_sum
        group_estimates.append((estimate, weight_sum))
    if len(group_estimates) == 2 and abs(group_estimates[0][0] - group_estimates[1][0]) > 2.5:
        group_estimates.sort(key=lambda item: item[1], reverse=True)
        return -group_estimates[0][0], group_estimates[0][1]
    weight_sum = sum(item[1] for item in filtered)
    correction = -sum(item[0] * item[1] for item in filtered) / weight_sum
    return float(correction), float(weight_sum)


def detect_major_stripe_rotation(pixels: np.ndarray) -> tuple[float, float]:
    """Detect long stripe-like line segments and estimate one global correction angle."""
    gray, scale = _prepared_gray(pixels, None)
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        raise ValueError("image is too small for stripe alignment")
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError("stripe alignment requires OpenCV") from exc
    image_u8 = np.clip(gray * 255.0, 0, 255).astype(np.uint8)
    edges = cv2.Canny(image_u8, 40, 120, apertureSize=3)
    min_line = max(24, int(min(gray.shape[:2]) * 0.18))
    gap = max(4, int(min_line * 0.08))
    raw = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=max(30, int(min_line * 0.45)),
        minLineLength=min_line,
        maxLineGap=gap,
    )
    if raw is None:
        raise ValueError("no reliable long stripes were detected")
    raw_segments = np.asarray(raw).reshape(-1, 4)
    segments = [
        (float(x1) / scale, float(y1) / scale, float(x2) / scale, float(y2) / scale)
        for x1, y1, x2, y2 in raw_segments
    ]
    return robust_rotation_from_segments(segments)


def detect_crosshair_alignment(pixels: np.ndarray) -> StripeAlignment:
    """Estimate alignment from the major crosshair axes and their intersection."""
    segments = _detect_long_line_segments(pixels)
    if not segments:
        raise ValueError("no reliable long crosshair lines were detected")
    horizontal: list[tuple[float, tuple[float, float, float, float], float]] = []
    vertical: list[tuple[float, tuple[float, float, float, float], float]] = []
    for segment in segments:
        x1, y1, x2, y2 = segment
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length <= 0:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        while angle > 90.0:
            angle -= 180.0
        while angle < -90.0:
            angle += 180.0
        if abs(angle) <= 45.0:
            horizontal.append((angle, segment, length))
        else:
            vertical.append((angle - (90.0 if angle > 0 else -90.0), segment, length))
    if not horizontal and not vertical:
        raise ValueError("no reliable crosshair axis orientation was detected")
    h_dev = _weighted_trimmed_angle(horizontal)
    v_dev = _weighted_trimmed_angle(vertical)
    if h_dev is not None and v_dev is not None and abs(h_dev - v_dev) > 3.0:
        h_weight = sum(item[2] for item in horizontal)
        v_weight = sum(item[2] for item in vertical)
        deviation = h_dev if h_weight >= v_weight else v_dev
        confidence = max(h_weight, v_weight)
    else:
        groups = []
        if h_dev is not None:
            groups.extend(horizontal)
        if v_dev is not None:
            groups.extend(vertical)
        deviation = _weighted_trimmed_angle(groups)
        confidence = sum(item[2] for item in groups)
    if deviation is None:
        raise ValueError("crosshair axis estimates are not reliable")
    center = _crosshair_intersection(horizontal, vertical)
    return StripeAlignment(
        angle_degrees=float(deviation),
        center=center,
        confidence=float(confidence),
    )


def estimate_rotation_to_axis(pixels: np.ndarray) -> float:
    """Estimate a rotation angle that makes stripe/ruler marks horizontal or vertical."""
    try:
        crosshair = detect_crosshair_alignment(pixels)
        if crosshair.confidence > 0:
            return crosshair.angle_degrees
    except ValueError:
        pass
    projection_angle = _estimate_rotation_by_projection(pixels)
    try:
        hough_angle, _weight = detect_major_stripe_rotation(pixels)
    except ValueError:
        return projection_angle
    if abs(projection_angle - hough_angle) <= 2.5:
        return float((projection_angle + hough_angle) / 2.0)
    return projection_angle


def align_image_to_axes(pixels: np.ndarray) -> tuple[np.ndarray, float]:
    """Rotate a stripe/crosshair image to image axes without scaling."""
    center: tuple[float, float] | None = None
    try:
        alignment = detect_crosshair_alignment(pixels)
        angle = alignment.angle_degrees
        center = alignment.center
    except ValueError:
        angle = estimate_rotation_to_axis(pixels)
    return rotate_image_no_scale(pixels, angle, center=center), angle


def rotate_image_no_scale(
    pixels: np.ndarray,
    angle_degrees: float,
    *,
    center: tuple[float, float] | None = None,
) -> np.ndarray:
    """Rotate pixels around the center without stretching or changing aspect ratio."""
    if abs(angle_degrees) < 1e-6:
        return pixels
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        return pixels
    height, width = pixels.shape[:2]
    rotation_center = center if center is not None else (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(rotation_center, angle_degrees, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int(round(height * sin + width * cos))
    new_height = int(round(height * cos + width * sin))
    if center is None:
        matrix[0, 2] += new_width / 2.0 - rotation_center[0]
        matrix[1, 2] += new_height / 2.0 - rotation_center[1]
    else:
        matrix[0, 2] += new_width / 2.0 - (
            matrix[0, 0] * center[0] + matrix[0, 1] * center[1] + matrix[0, 2]
        )
        matrix[1, 2] += new_height / 2.0 - (
            matrix[1, 0] * center[0] + matrix[1, 1] * center[1] + matrix[1, 2]
        )
    interpolation = cv2.INTER_LINEAR
    border_mode = cv2.BORDER_CONSTANT
    return cv2.warpAffine(
        np.asarray(pixels),
        matrix,
        (new_width, new_height),
        flags=interpolation,
        borderMode=border_mode,
        borderValue=0,
    )


def _detect_long_line_segments(pixels: np.ndarray) -> list[tuple[float, float, float, float]]:
    gray, scale = _prepared_gray(pixels, None)
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return []
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        return []
    image_u8 = np.clip(gray * 255.0, 0, 255).astype(np.uint8)
    edges = cv2.Canny(image_u8, 30, 110, apertureSize=3)
    min_line = max(24, int(min(gray.shape[:2]) * 0.14))
    raw = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=max(24, int(min_line * 0.35)),
        minLineLength=min_line,
        maxLineGap=max(5, int(min_line * 0.14)),
    )
    if raw is None:
        return []
    segments = np.asarray(raw).reshape(-1, 4)
    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    if lengths.size == 0:
        return []
    min_keep = max(float(np.percentile(lengths, 55.0)), float(lengths.max()) * 0.18)
    return [
        (float(x1) / scale, float(y1) / scale, float(x2) / scale, float(y2) / scale)
        for (x1, y1, x2, y2), length in zip(segments, lengths, strict=False)
        if float(length) >= min_keep
    ]


def _weighted_trimmed_angle(
    items: list[tuple[float, tuple[float, float, float, float], float]],
) -> float | None:
    if not items:
        return None
    values = np.array([item[0] for item in items], dtype=np.float32)
    weights = np.array([item[2] for item in items], dtype=np.float32)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    tolerance = max(1.0, 3.0 * mad)
    keep = np.abs(values - median) <= tolerance
    if not np.any(keep):
        return None
    values = values[keep]
    weights = weights[keep]
    total = float(np.sum(weights))
    if total <= 0:
        return None
    return float(np.sum(values * weights) / total)


def _crosshair_intersection(
    horizontal: list[tuple[float, tuple[float, float, float, float], float]],
    vertical: list[tuple[float, tuple[float, float, float, float], float]],
) -> tuple[float, float] | None:
    if not horizontal or not vertical:
        return None
    h_lines = sorted(horizontal, key=lambda item: item[2], reverse=True)[:6]
    v_lines = sorted(vertical, key=lambda item: item[2], reverse=True)[:6]
    points: list[tuple[float, float, float]] = []
    for _h_angle, h_segment, h_length in h_lines:
        for _v_angle, v_segment, v_length in v_lines:
            point = _line_intersection(h_segment, v_segment)
            if point is not None:
                points.append((point[0], point[1], h_length + v_length))
    if not points:
        return None
    weights = np.array([point[2] for point in points], dtype=np.float32)
    xs = np.array([point[0] for point in points], dtype=np.float32)
    ys = np.array([point[1] for point in points], dtype=np.float32)
    return (
        float(np.sum(xs * weights) / np.sum(weights)),
        float(np.sum(ys * weights) / np.sum(weights)),
    )


def _line_intersection(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    x1, y1, x2, y2 = first
    x3, y3, x4, y4 = second
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-6:
        return None
    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / denominator
    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / denominator
    return float(px), float(py)


def _detect_stripes_for_orientation(
    gray: np.ndarray,
    orientation: ScaleOrientation,
) -> tuple[
    float,
    ScaleOrientation,
    np.ndarray,
    ScaleCoordinateSystem,
    tuple[TickCandidate, ...],
    tuple[RefinedTick, ...],
    TickLatticeFit,
    tuple[RefinedTick, ...],
] | None:
    angle_degrees, angle_std, angle_confidence = estimate_tick_angle(gray, orientation)
    geometry = make_scale_coordinate_system(gray.shape, angle_degrees)
    profile = project_scale_profile(gray, geometry)
    period, period_confidence = _period_from_projection(profile)
    if period <= 0:
        return None
    orientation = ScaleOrientation(
        axis=orientation.axis,
        profile_axis=orientation.profile_axis,
        confidence=period_confidence * angle_confidence,
        period_hint=period,
        tick_angle_degrees=angle_degrees,
        tick_angle_std_degrees=angle_std,
    )
    candidates = detect_tick_candidates(profile, period)
    refined = refine_tick_centers_subpixel(profile, candidates, period)
    line_refined = detect_tick_centers_from_line_segments(gray, orientation, geometry)
    if len(refined) < 4 and len(line_refined) > len(refined):
        refined = line_refined
    if len(refined) < 3:
        fallback = _stripe_positions_from_projection(profile, period)
        refined = tuple(
            RefinedTick(center=float(position), confidence=1.0)
            for position in fallback
        )
    if len(refined) < 3:
        return None
    lattice = fit_tick_lattice(refined, period)
    inlier_ticks = tuple(
        tick
        for tick, inlier in zip(refined, lattice.inlier_mask, strict=False)
        if inlier
    )
    if len(inlier_ticks) < 3 or lattice.spacing <= 0 or lattice.confidence <= 0:
        return None
    span = max(1.0, inlier_ticks[-1].center - inlier_ticks[0].center)
    coverage = min(1.0, span / max(1.0, profile.size * 0.45))
    candidate_quality = min(1.0, len(candidates) / max(1.0, len(refined)))
    score = (
        len(inlier_ticks)
        * lattice.confidence
        * min(20.0, period_confidence)
        * coverage
        * max(0.15, candidate_quality)
        / max(1.0, lattice.rms_error + 0.2)
    )
    return score, orientation, profile, geometry, candidates, refined, lattice, inlier_ticks


def estimate_tick_angle(
    gray: np.ndarray,
    orientation: ScaleOrientation,
) -> tuple[float, float, float]:
    """Estimate the dominant continuous tick angle in image coordinates."""
    nominal = 90.0 if orientation.profile_axis == 0 else 0.0
    segments = _detect_long_line_segments((gray * 255.0).astype(np.uint8))
    candidates: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in segments:
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length <= 0:
            continue
        angle = _line_angle_0_180(np.degrees(np.arctan2(dy, dx)))
        deviation = _angle_delta_180(angle, nominal)
        if abs(deviation) <= 35.0:
            candidates.append((nominal + deviation, length))
    if not candidates:
        return nominal, 25.0, 0.35
    angles = np.array([item[0] for item in candidates], dtype=np.float64)
    weights = np.array([item[1] for item in candidates], dtype=np.float64)
    median = _weighted_median(angles, weights)
    deviations = np.array([_angle_delta_180(angle, median) for angle in angles], dtype=np.float64)
    mad = float(np.median(np.abs(deviations)))
    keep = np.abs(deviations) <= max(3.0, 3.5 * mad)
    if np.any(keep):
        angles = angles[keep]
        weights = weights[keep]
        deviations = np.array([_angle_delta_180(angle, median) for angle in angles], dtype=np.float64)
    angle = _weighted_median(angles, weights)
    angle_std = float(np.sqrt(np.average(np.square(deviations), weights=weights))) if weights.size else 25.0
    confidence = max(0.15, min(1.0, float(np.sum(weights)) / max(24.0, min(gray.shape) * 1.5)))
    confidence *= max(0.15, 1.0 - min(1.0, angle_std / 20.0))
    return float(_line_angle_0_180(angle)), angle_std, confidence


def make_scale_coordinate_system(
    shape: tuple[int, int],
    tick_angle_degrees: float,
) -> ScaleCoordinateSystem:
    """Create an orthonormal scale coordinate system for image-to-profile projection."""
    height, width = shape
    angle = np.deg2rad(tick_angle_degrees)
    tangent_x = float(np.cos(angle))
    tangent_y = float(np.sin(angle))
    normal_x = float(-np.sin(angle))
    normal_y = float(np.cos(angle))
    corners = np.array(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [0.0, float(height - 1)],
            [float(width - 1), float(height - 1)],
        ],
        dtype=np.float64,
    )
    u_values = corners[:, 0] * normal_x + corners[:, 1] * normal_y
    v_values = corners[:, 0] * tangent_x + corners[:, 1] * tangent_y
    return ScaleCoordinateSystem(
        tick_angle_degrees=float(tick_angle_degrees),
        normal_x=normal_x,
        normal_y=normal_y,
        tangent_x=tangent_x,
        tangent_y=tangent_y,
        u_min=float(np.floor(np.min(u_values))),
        u_max=float(np.ceil(np.max(u_values))),
        v_min=float(np.floor(np.min(v_values))),
        v_max=float(np.ceil(np.max(v_values))),
    )


def project_scale_profile(gray: np.ndarray, geometry: ScaleCoordinateSystem) -> np.ndarray:
    """Average image intensity along tick direction using projected coordinates."""
    if gray.ndim != 2 or gray.size == 0:
        return np.array([], dtype=np.float32)
    yy, xx = np.indices(gray.shape, dtype=np.float32)
    u = xx * geometry.normal_x + yy * geometry.normal_y
    bins = np.rint(u - geometry.u_min).astype(np.int32)
    size = max(1, int(round(geometry.u_max - geometry.u_min)) + 1)
    border_dark = _border_connected_dark_mask(gray)
    valid = (bins >= 0) & (bins < size) & ~border_dark
    sums = np.bincount(bins[valid].ravel(), weights=gray[valid].ravel(), minlength=size)
    counts = np.bincount(bins[valid].ravel(), minlength=size)
    profile = np.divide(
        sums,
        np.maximum(counts, 1),
        out=np.zeros(size, dtype=np.float64),
        where=counts > 0,
    )
    if np.any(counts == 0) and np.any(counts > 0):
        filled = np.interp(
            np.arange(size, dtype=np.float64),
            np.nonzero(counts > 0)[0].astype(np.float64),
            profile[counts > 0],
        )
        profile = filled
    return _normalize_profile(np.asarray(profile, dtype=np.float32))


def _border_connected_dark_mask(gray: np.ndarray) -> np.ndarray:
    """Return dark regions connected to image edges, typically rotation padding."""
    if gray.ndim != 2 or gray.size == 0:
        return np.zeros_like(gray, dtype=bool)
    dark = gray <= max(0.015, float(np.percentile(gray, 0.5)) + 0.005)
    if float(np.mean(dark)) < 0.02:
        return np.zeros_like(dark, dtype=bool)
    visited = np.zeros_like(dark, dtype=bool)
    height, width = dark.shape
    stack: list[tuple[int, int]] = [
        (0, 0),
        (0, width - 1),
        (height - 1, 0),
        (height - 1, width - 1),
    ]
    while stack:
        y, x = stack.pop()
        if y < 0 or y >= height or x < 0 or x >= width or visited[y, x] or not dark[y, x]:
            continue
        visited[y, x] = True
        stack.extend(((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
    if float(np.mean(visited)) < 0.02:
        return np.zeros_like(visited, dtype=bool)
    return visited


def scale_to_image_coordinates(
    geometry: ScaleCoordinateSystem,
    u_profile: float,
    v: float,
) -> tuple[float, float]:
    """Transform scale coordinates back to original image coordinates."""
    u = geometry.u_min + u_profile
    x = geometry.normal_x * u + geometry.tangent_x * v
    y = geometry.normal_y * u + geometry.tangent_y * v
    return float(x), float(y)


def detect_scale_orientation(gray: np.ndarray) -> ScaleOrientation:
    """Detect whether scale ticks are vertical or horizontal from profile periodicity."""
    vertical_profile = build_scale_profile(gray, ScaleOrientation("vertical stripes", 0, 1.0, 0.0))
    horizontal_profile = build_scale_profile(gray, ScaleOrientation("horizontal stripes", 1, 1.0, 0.0))
    vertical_period, vertical_confidence = _period_from_projection(vertical_profile)
    horizontal_period, horizontal_confidence = _period_from_projection(horizontal_profile)
    if vertical_period <= 0 and horizontal_period <= 0:
        raise ValueError("could not detect reliable stripe orientation")
    if vertical_confidence >= horizontal_confidence:
        return ScaleOrientation(
            axis="vertical stripes",
            profile_axis=0,
            confidence=vertical_confidence / max(1.0, horizontal_confidence),
            period_hint=vertical_period,
        )
    return ScaleOrientation(
        axis="horizontal stripes",
        profile_axis=1,
        confidence=horizontal_confidence / max(1.0, vertical_confidence),
        period_hint=horizontal_period,
    )


def build_scale_profile(gray: np.ndarray, orientation: ScaleOrientation) -> np.ndarray:
    """Build a normalized 1D profile perpendicular to tick direction."""
    if gray.ndim != 2 or gray.size == 0:
        return np.array([], dtype=np.float32)
    if orientation.profile_axis == 0:
        trim = max(0, int(gray.shape[0] * 0.03))
        work = gray[trim : gray.shape[0] - trim or gray.shape[0], :]
        profile = np.mean(work, axis=0)
    else:
        trim = max(0, int(gray.shape[1] * 0.03))
        work = gray[:, trim : gray.shape[1] - trim or gray.shape[1]]
        profile = np.mean(work, axis=1)
    return _normalize_profile(np.asarray(profile, dtype=np.float32))


def _normalize_profile(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size < 3:
        return values
    window = max(9, min(301, (values.size // 8) | 1))
    if window < values.size:
        kernel = np.ones(window, dtype=np.float32) / window
        background = np.convolve(values, kernel, mode="same")
        values = values - background + float(np.median(background))
    low, high = np.percentile(values, [2.0, 98.0])
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def detect_tick_candidates(profile: np.ndarray, period_hint: float) -> tuple[TickCandidate, ...]:
    """Detect dark valley candidates in a normalized profile."""
    values = np.asarray(profile, dtype=np.float32)
    if values.size < 5:
        return ()
    dark = float(np.median(values)) - values
    dark = dark - float(np.percentile(dark, 10.0))
    if float(np.max(dark)) <= 0:
        return ()
    threshold = max(
        float(np.percentile(dark, 72.0)),
        float(np.max(dark)) * 0.20,
    )
    min_separation = max(2.0, min(float(period_hint) * 0.45, 10.0))
    raw: list[tuple[float, int, float]] = []
    for index in range(1, values.size - 1):
        if dark[index] < threshold:
            continue
        if dark[index] >= dark[index - 1] and dark[index] >= dark[index + 1]:
            left = index
            while left > 0 and dark[left] > threshold * 0.45:
                left -= 1
            right = index
            while right < dark.size - 1 and dark[right] > threshold * 0.45:
                right += 1
            width = float(max(1, right - left))
            if width > max(16.0, period_hint * 0.65):
                continue
            local_floor = float(max(dark[left], dark[right], np.percentile(dark[max(0, left - 4):min(dark.size, right + 5)], 25.0)))
            prominence = float(dark[index] - local_floor)
            raw.append((prominence, index, width))
    raw.sort(key=lambda item: item[1])
    selected: list[TickCandidate] = []
    for prominence, index, width in raw:
        if not selected or index - selected[-1].index >= min_separation:
            selected.append(TickCandidate(index=index, prominence=prominence, width=width))
        elif prominence > selected[-1].prominence:
            selected[-1] = TickCandidate(index=index, prominence=prominence, width=width)
    return tuple(selected)


def refine_tick_centers_subpixel(
    profile: np.ndarray,
    candidates: tuple[TickCandidate, ...],
    period_hint: float,
) -> tuple[RefinedTick, ...]:
    """Refine tick centers using subpixel edge positions with valley fallback."""
    values = np.asarray(profile, dtype=np.float32)
    if values.size < 5:
        return ()
    gradient = np.gradient(values)
    noise = float(np.median(np.abs(values - np.median(values)))) + 1e-6
    radius = max(3, int(round(max(4.0, period_hint * 0.42))))
    refined: list[RefinedTick] = []
    for candidate in candidates:
        center = int(candidate.index)
        left_start = max(1, center - radius)
        right_end = min(values.size - 2, center + radius)
        left_edge: float | None = None
        right_edge: float | None = None
        if center - left_start >= 2:
            local = -gradient[left_start : center + 1]
            left_edge = left_start + _quadratic_peak_position(local)
        if right_end - center >= 2:
            local = gradient[center : right_end + 1]
            right_edge = center + _quadratic_peak_position(local)
        edge_span_ok = (
            left_edge is not None
            and right_edge is not None
            and 0.8 <= right_edge - left_edge <= max(18.0, period_hint * 0.70)
        )
        if edge_span_ok:
            subpixel_center = (left_edge + right_edge) / 2.0
            edge_balance = 1.0 - min(
                0.9,
                abs((center - left_edge) - (right_edge - center))
                / max(1.0, right_edge - left_edge),
            )
        else:
            valley_start = max(0, center - 2)
            valley_end = min(values.size, center + 3)
            subpixel_center = valley_start + _quadratic_peak_position(-values[valley_start:valley_end])
            edge_balance = 0.55
            left_edge = None
            right_edge = None
        confidence = max(0.0, candidate.prominence / noise) * edge_balance
        if 0 <= subpixel_center < values.size:
            refined.append(
                RefinedTick(
                    center=float(subpixel_center),
                    confidence=float(confidence),
                    left_edge=left_edge,
                    right_edge=right_edge,
                )
            )
    refined.sort(key=lambda tick: tick.center)
    return tuple(refined)


def detect_tick_centers_from_line_segments(
    gray: np.ndarray,
    orientation: ScaleOrientation,
    geometry: ScaleCoordinateSystem,
) -> tuple[RefinedTick, ...]:
    """Detect rotated tick centerlines directly from Hough line segments."""
    segments = _detect_long_line_segments((gray * 255.0).astype(np.uint8))
    if not segments:
        return ()
    values: list[tuple[float, float, float]] = []
    for x1, y1, x2, y2 in segments:
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length < max(10.0, min(gray.shape) * 0.08):
            continue
        angle = _line_angle_0_180(np.degrees(np.arctan2(dy, dx)))
        if abs(_angle_delta_180(angle, orientation.tick_angle_degrees)) > 8.0:
            continue
        midpoint_x = (x1 + x2) / 2.0
        midpoint_y = (y1 + y2) / 2.0
        u_profile = (
            midpoint_x * geometry.normal_x
            + midpoint_y * geometry.normal_y
            - geometry.u_min
        )
        values.append((float(u_profile), length, angle))
    if len(values) < 3:
        return ()
    values.sort(key=lambda item: item[0])
    clustered: list[list[tuple[float, float, float]]] = []
    for item in values:
        if not clustered or abs(item[0] - np.average([v[0] for v in clustered[-1]], weights=[v[1] for v in clustered[-1]])) > 5.0:
            clustered.append([item])
        else:
            clustered[-1].append(item)
    ticks: list[RefinedTick] = []
    for group in clustered:
        weights = np.array([item[1] for item in group], dtype=np.float64)
        centers = np.array([item[0] for item in group], dtype=np.float64)
        ticks.append(
            RefinedTick(
                center=float(np.average(centers, weights=weights)),
                confidence=float(np.sum(weights) / max(1.0, min(gray.shape))),
                length=float(np.max(weights)),
            )
        )
    return tuple(ticks)


def fit_tick_lattice(
    ticks: tuple[RefinedTick, ...],
    period_hint: float = 0.0,
) -> TickLatticeFit:
    """Fit subpixel tick centers to a regular 1D lattice with outlier rejection."""
    if len(ticks) < 3:
        return TickLatticeFit(0.0, 0.0, float("inf"), tuple(False for _ in ticks), 0.0)
    centers = np.array([tick.center for tick in ticks], dtype=np.float64)
    weights = np.array([max(0.1, tick.confidence) for tick in ticks], dtype=np.float64)
    spacing = _initial_lattice_spacing(centers, period_hint)
    if spacing <= 0:
        return TickLatticeFit(0.0, 0.0, float("inf"), tuple(False for _ in ticks), 0.0)
    origin = float(centers[0])
    mask = np.ones(centers.shape, dtype=bool)
    for _ in range(5):
        indices = np.rint((centers - origin) / spacing).astype(np.int64)
        indices -= int(indices.min())
        fit = _weighted_line_fit(indices[mask], centers[mask], weights[mask])
        if fit is None:
            break
        origin, spacing = fit
        residuals = centers - (origin + indices * spacing)
        rms = _weighted_rms(residuals[mask], weights[mask])
        tolerance = max(1.25, min(spacing * 0.22, rms * 3.0 + 0.35))
        new_mask = np.abs(residuals) <= tolerance
        if int(np.sum(new_mask)) < 3:
            break
        if np.array_equal(new_mask, mask):
            mask = new_mask
            break
        mask = new_mask
    indices = np.rint((centers - origin) / spacing).astype(np.int64)
    residuals = centers - (origin + indices * spacing)
    rms = _weighted_rms(residuals[mask], weights[mask]) if np.any(mask) else float("inf")
    confidence = max(0.0, float(np.sum(mask)) / len(ticks)) * max(0.0, 1.0 - rms / max(1.0, spacing * 0.18))
    return TickLatticeFit(
        spacing=float(spacing),
        origin=float(origin),
        rms_error=float(rms),
        inlier_mask=tuple(bool(value) for value in mask),
        confidence=float(confidence),
    )


def estimate_tick_lengths(
    gray: np.ndarray,
    orientation: ScaleOrientation,
    ticks: tuple[RefinedTick, ...],
    geometry: ScaleCoordinateSystem | None = None,
) -> tuple[float, ...]:
    """Estimate visible tick length along the tick direction for classification."""
    if not ticks:
        return ()
    if geometry is not None:
        return _estimate_projected_tick_lengths(gray, ticks, geometry)
    lengths: list[float] = []
    dark_threshold = float(np.percentile(gray, 18.0))
    for tick in ticks:
        center = int(round(tick.center))
        if orientation.profile_axis == 0:
            x0 = max(0, center - 1)
            x1 = min(gray.shape[1], center + 2)
            line_strength = np.mean(gray[:, x0:x1], axis=1)
        else:
            y0 = max(0, center - 1)
            y1 = min(gray.shape[0], center + 2)
            line_strength = np.mean(gray[y0:y1, :], axis=0)
        active = line_strength <= dark_threshold
        runs = _active_runs(active)
        length = float(max((end - start for start, end in runs), default=1))
        lengths.append(length)
    return tuple(lengths)


def _estimate_projected_tick_lengths(
    gray: np.ndarray,
    ticks: tuple[RefinedTick, ...],
    geometry: ScaleCoordinateSystem,
) -> tuple[float, ...]:
    yy, xx = np.indices(gray.shape, dtype=np.float32)
    u_profile = xx * geometry.normal_x + yy * geometry.normal_y - geometry.u_min
    v = xx * geometry.tangent_x + yy * geometry.tangent_y
    dark_threshold = float(np.percentile(gray, 18.0))
    dark = gray <= dark_threshold
    lengths: list[float] = []
    for tick in ticks:
        width = 2.25
        mask = dark & (np.abs(u_profile - tick.center) <= width)
        values = v[mask]
        if values.size < 3:
            lengths.append(1.0)
            continue
        lengths.append(float(np.percentile(values, 97.0) - np.percentile(values, 3.0)))
    return tuple(lengths)


def classify_tick_sizes(
    ticks: tuple[RefinedTick, ...],
    lengths: tuple[float, ...],
) -> tuple[RefinedTick, ...]:
    """Classify ticks by relative geometric length."""
    if not ticks:
        return ()
    if not lengths or len(lengths) != len(ticks):
        lengths = tuple(1.0 for _ in ticks)
    max_length = max(max(lengths), 1.0)
    classified: list[RefinedTick] = []
    for tick, length in zip(ticks, lengths, strict=False):
        ratio = float(length) / max_length
        if ratio >= 0.78:
            tick_class = "large"
        elif ratio >= 0.60:
            tick_class = "medium"
        else:
            tick_class = "small"
        classified.append(
            RefinedTick(
                center=tick.center,
                confidence=tick.confidence,
                left_edge=tick.left_edge,
                right_edge=tick.right_edge,
                residual=tick.residual,
                inlier=tick.inlier,
                length=float(length),
                tick_class=tick_class,
            )
        )
    return tuple(classified)


def compute_scale_calibration(
    fundamental_spacing_px: float,
    *,
    minor_interval_micrometers: float = 10.0,
) -> dict[str, float]:
    """Assign physical calibration after geometric spacing has been fitted."""
    if fundamental_spacing_px <= 0 or minor_interval_micrometers <= 0:
        return {"pixels_per_micrometer": 0.0, "micrometers_per_pixel": 0.0}
    pixels_per_micrometer = fundamental_spacing_px / minor_interval_micrometers
    return {
        "pixels_per_micrometer": float(pixels_per_micrometer),
        "micrometers_per_pixel": float(1.0 / pixels_per_micrometer),
    }


def _tick_mark_dict(
    tick: RefinedTick,
    geometry: ScaleCoordinateSystem,
    scale: float,
) -> dict[str, float | str]:
    u_abs = geometry.u_min + tick.center
    v_center = (geometry.v_min + geometry.v_max) / 2.0
    half_length = max(1.0, tick.length / 2.0)
    v_top = max(geometry.v_min, v_center - half_length)
    v_bottom = min(geometry.v_max, v_center + half_length)
    x, y = scale_to_image_coordinates(geometry, tick.center, v_center)
    return {
        "center": tick.center / scale,
        "u": u_abs / scale,
        "top": v_top / scale,
        "bottom": v_bottom / scale,
        "height": tick.length / scale,
        "class": tick.tick_class,
        "confidence": tick.confidence,
        "x": x / scale,
        "y": y / scale,
        "normal_x": geometry.normal_x,
        "normal_y": geometry.normal_y,
        "tangent_x": geometry.tangent_x,
        "tangent_y": geometry.tangent_y,
        "tick_angle_degrees": geometry.tick_angle_degrees,
    }


def _initial_lattice_spacing(centers: np.ndarray, period_hint: float) -> float:
    diffs = np.diff(np.sort(centers))
    diffs = diffs[diffs > 1.5]
    if diffs.size == 0:
        return float(period_hint)
    pairwise = _pairwise_spacing_estimates(np.sort(centers), period_hint)
    if pairwise.size:
        return float(np.median(pairwise))
    if period_hint > 0:
        ratios = np.maximum(1, np.rint(diffs / period_hint))
        estimates = diffs / ratios
        close = np.abs(estimates - period_hint) <= max(2.0, period_hint * 0.35)
        if np.any(close):
            return float(np.median(estimates[close]))
    base = float(np.percentile(diffs, 35.0))
    close = diffs <= max(base * 1.65, base + 3.0)
    return float(np.median(diffs[close]))


def _pairwise_spacing_estimates(centers: np.ndarray, period_hint: float) -> np.ndarray:
    if centers.size < 3 or period_hint <= 0:
        return np.array([], dtype=np.float64)
    estimates: list[float] = []
    for left_index, left in enumerate(centers[:-1]):
        for right in centers[left_index + 1 :]:
            distance = float(right - left)
            if distance <= period_hint * 0.55:
                continue
            interval = max(1, int(round(distance / period_hint)))
            estimate = distance / interval
            if abs(estimate - period_hint) <= max(2.5, period_hint * 0.30):
                estimates.append(estimate)
    if len(estimates) < 3:
        return np.array([], dtype=np.float64)
    values = np.array(estimates, dtype=np.float64)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    keep = np.abs(values - median) <= max(0.6, 3.5 * mad)
    return values[keep]


def _weighted_line_fit(
    indices: np.ndarray,
    centers: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, float] | None:
    if indices.size < 2:
        return None
    x = indices.astype(np.float64)
    y = centers.astype(np.float64)
    w = weights.astype(np.float64)
    total = float(np.sum(w))
    if total <= 0:
        return None
    x_mean = float(np.sum(w * x) / total)
    y_mean = float(np.sum(w * y) / total)
    denominator = float(np.sum(w * (x - x_mean) ** 2))
    if denominator <= 1e-9:
        return None
    spacing = float(np.sum(w * (x - x_mean) * (y - y_mean)) / denominator)
    origin = y_mean - spacing * x_mean
    return origin, spacing


def _weighted_rms(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return float("inf")
    total = float(np.sum(weights))
    if total <= 0:
        return float(np.sqrt(np.mean(values**2)))
    return float(np.sqrt(np.sum(weights * values**2) / total))


def _quadratic_peak_position(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0:
        return 0.0
    index = int(np.argmax(data))
    if index <= 0 or index >= data.size - 1:
        return float(index)
    left, center, right = float(data[index - 1]), float(data[index]), float(data[index + 1])
    denominator = left - 2.0 * center + right
    if abs(denominator) < 1e-12:
        return float(index)
    offset = 0.5 * (left - right) / denominator
    return float(index + max(-0.75, min(0.75, offset)))


def _line_angle_0_180(angle_degrees: float) -> float:
    angle = float(angle_degrees) % 180.0
    if angle < 0:
        angle += 180.0
    return angle


def _angle_delta_180(angle_degrees: float, reference_degrees: float) -> float:
    return ((float(angle_degrees) - float(reference_degrees) + 90.0) % 180.0) - 90.0


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cutoff = float(cumulative[-1]) * 0.5
    return float(sorted_values[int(np.searchsorted(cumulative, cutoff, side="left"))])


def _active_runs(active: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(active):
        if bool(value) and start is None:
            start = index
        elif not bool(value) and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, int(active.size)))
    return runs
