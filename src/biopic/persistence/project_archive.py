"""Project save-side asset archive exports."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from biopic.export.raster import export_image, export_project_figure_board
from biopic.imaging.project_render import (
    edit_layers_for_image,
    project_image_cache_key,
    render_project_image,
)
from biopic.models.annotations import AnnotationKind
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project


def export_project_archive(project: Project, manifest_path: Path) -> dict[str, str]:
    """Create/update the project folder next to a saved manifest."""
    project_dir = project_folder_for_manifest(manifest_path)
    unedited_dir = project_dir / "unedited"
    edited_dir = project_dir / "edited"
    boards_dir = project_dir / "figure_boards"
    unedited_dir.mkdir(parents=True, exist_ok=True)
    edited_dir.mkdir(parents=True, exist_ok=True)
    boards_dir.mkdir(parents=True, exist_ok=True)

    archived_paths: dict[str, str] = {}
    for asset in project.assets.values():
        source_path = Path(asset.path)
        original_path = str(source_path)
        if source_path.exists():
            archived = _archive_unedited_asset(asset, source_path, unedited_dir)
            archived_paths[asset.id] = str(archived)
        else:
            archived_paths[asset.id] = asset.path
        _write_asset_metadata(asset, unedited_dir, original_path, archived_paths[asset.id])

        node_id = project.source_node_id_for_asset(asset.id)
        if node_id is not None and _node_has_saved_outputs(project, node_id):
            edited_path = edited_dir / f"{_asset_stem(asset)}__edited.tif"
            signature = _edited_output_signature(project, node_id)
            if _output_is_current(edited_path, signature):
                continue
            rendered = render_project_image(project, node_id)
            if rendered is None:
                continue
            if _node_has_raster_overlays(project, node_id):
                rendered = _render_measurements_and_annotations(project, node_id, rendered)
            export_image(rendered, edited_path)
            _write_output_signature(edited_path, signature)

    for board in project.figure_boards.values():
        board_name = _safe_name(board.name or board.id)
        board_path = boards_dir / f"{board_name}.tif"
        signature = _board_output_signature(project, board.id)
        if _output_is_current(board_path, signature):
            continue
        export_project_figure_board(project, board, board_path)
        _write_output_signature(board_path, signature)
    return archived_paths


def project_folder_for_manifest(manifest_path: Path) -> Path:
    """Return the sibling folder used for project-owned assets."""
    name = manifest_path.name
    if name.endswith(".biopic.json"):
        folder_name = name[: -len(".biopic.json")]
    else:
        folder_name = manifest_path.stem
    return manifest_path.with_name(folder_name)


def _archive_unedited_asset(asset: ImageAsset, source_path: Path, unedited_dir: Path) -> Path:
    suffix = source_path.suffix or ".tif"
    destination = unedited_dir / f"{_asset_stem(asset)}__source{suffix}"
    try:
        if source_path.resolve() != destination.resolve():
            source_stat = source_path.stat()
            if not _same_file_snapshot(destination, source_stat.st_size, source_stat.st_mtime_ns):
                shutil.copy2(source_path, destination)
    except FileNotFoundError:
        return source_path
    return destination


def _write_asset_metadata(
    asset: ImageAsset,
    unedited_dir: Path,
    original_path: str,
    archived_path: str,
) -> None:
    metadata = {
        "id": asset.id,
        "display_name": asset.display_name,
        "original_path": original_path,
        "archived_path": archived_path,
        "width": asset.width,
        "height": asset.height,
        "frames": asset.frames,
        "dtype": asset.dtype,
        "color_model": asset.color_model,
        "metadata": asset.metadata,
    }
    path = unedited_dir / f"{_asset_stem(asset)}__metadata.json"
    _write_json_if_changed(path, metadata)


def _same_file_snapshot(path: Path, size: int, mtime_ns: int) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    return stat.st_size == size and stat.st_mtime_ns == mtime_ns


def _edited_output_signature(project: Project, node_id: str) -> dict[str, object]:
    return {
        "kind": "edited",
        "node_id": node_id,
        "render": repr(project_image_cache_key(project, node_id)),
        "overlays": _overlay_signature(project, node_id),
        "measurements": [
            measurement.to_dict()
            for measurement in project.measurements.values()
            if measurement.image_node_id == node_id
        ],
    }


def _board_output_signature(project: Project, board_id: str) -> dict[str, object]:
    board = project.figure_boards[board_id]
    source_signatures = {
        panel.source_node_id: _edited_output_signature(project, panel.source_node_id)
        for panel in board.panels
        if panel.source_node_id is not None
    }
    return {
        "kind": "figure_board",
        "board": board.to_dict(),
        "sources": source_signatures,
    }


def _overlay_signature(project: Project, node_id: str) -> dict[str, object]:
    return {
        "scale_bars": [
            scale_bar.to_dict()
            for scale_bar in project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ],
        "annotations": [
            annotation.to_dict()
            for annotation in project.annotations.values()
            if annotation.image_node_id == node_id
        ],
    }


def _output_is_current(path: Path, signature: dict[str, object]) -> bool:
    if not path.exists():
        return False
    signature_path = _signature_path(path)
    try:
        current = json.loads(signature_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return current == signature


def _write_output_signature(path: Path, signature: dict[str, object]) -> None:
    _write_json_if_changed(_signature_path(path), signature)


def _signature_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".signature.json")


def _write_json_if_changed(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    path.write_text(text + "\n", encoding="utf-8")


def _node_has_saved_outputs(project: Project, node_id: str) -> bool:
    return (
        bool(project.adjustment_layers_for_image(node_id))
        or bool(edit_layers_for_image(project, node_id))
        or _node_has_raster_overlays(project, node_id)
        or any(measurement.image_node_id == node_id for measurement in project.measurements.values())
    )


def _node_has_raster_overlays(project: Project, node_id: str) -> bool:
    return (
        any(scale_bar.image_node_id == node_id for scale_bar in project.scale_bars.values())
        or any(annotation.image_node_id == node_id for annotation in project.annotations.values())
    )


def _render_measurements_and_annotations(
    project: Project,
    node_id: str,
    pixels: np.ndarray,
) -> np.ndarray:
    display = _display_compatible(pixels)
    image = Image.fromarray(display).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    for scale_bar in project.scale_bars.values():
        if scale_bar.image_node_id == node_id:
            _draw_scale_bar(draw, image.size, scale_bar)
    for annotation in project.annotations.values():
        if annotation.image_node_id == node_id and annotation.visible:
            _draw_annotation(draw, image.size, annotation)
    return np.asarray(image.convert("RGB"))


def _draw_scale_bar(
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    scale_bar: ScaleBar,
) -> None:
    width, height = image_size
    length = max(1.0, float(scale_bar.pixel_length))
    thickness = max(1.0, float(scale_bar.width_px))
    is_vertical = scale_bar.orientation == "vertical"
    bar_width = thickness if is_vertical else length
    bar_height = length if is_vertical else thickness
    x, y = _scale_bar_origin(scale_bar, float(width), float(height), bar_width, bar_height)
    if scale_bar.background:
        pad = max(4.0, thickness * 2.0)
        draw.rectangle(
            (x - pad, y - pad, x + bar_width + pad, y + bar_height + pad),
            fill=_rgba(scale_bar.background, scale_bar.opacity),
        )
    color = _rgba(scale_bar.foreground, scale_bar.opacity)
    if is_vertical:
        draw.line((x + thickness / 2.0, y, x + thickness / 2.0, y + length), fill=color, width=int(round(thickness)))
    else:
        draw.line((x, y + thickness / 2.0, x + length, y + thickness / 2.0), fill=color, width=int(round(thickness)))
    if scale_bar.display_length:
        text = f"{scale_bar.physical_length:g} {scale_bar.unit}"
        font = _font(scale_bar.font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        if is_vertical:
            text_xy = (x + thickness + 6.0, y + length / 2.0)
        else:
            text_xy = (x + length / 2.0 - text_width / 2.0, y + thickness + 4.0)
        draw.text(text_xy, text, fill=color, font=font)


def _draw_annotation(draw: ImageDraw.ImageDraw, image_size: tuple[int, int], annotation: object) -> None:
    width, height = image_size
    points = [(float(x) * width, float(y) * height) for x, y in annotation.points]
    if not points:
        return
    color = _rgba(annotation.color, annotation.opacity)
    if annotation.kind is AnnotationKind.TEXT:
        draw.text(points[0], annotation.text or "Label", fill=color, font=_font(annotation.size))
        return
    if len(points) < 2:
        return
    line_width = max(1, int(round(annotation.line_width)))
    if annotation.kind is AnnotationKind.WEDGE and len(points) >= 2:
        fill = _rgba(annotation.fill or annotation.color, annotation.opacity)
        start, end = points[0], points[1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        nx = -dy / length
        ny = dx / length
        half = max(5.0, annotation.line_width * 4.0)
        draw.polygon((end, (start[0] + nx * half, start[1] + ny * half), (start[0] - nx * half, start[1] - ny * half)), fill=fill)
        return
    draw.line(points, fill=color, width=line_width, joint="curve")
    if annotation.kind is AnnotationKind.ARROW:
        _draw_arrow_head(draw, points[-2], points[-1], color, line_width)


def _draw_arrow_head(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    line_width: int,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux
    head = max(8.0, line_width * 5.0)
    back = (end[0] - ux * head, end[1] - uy * head)
    draw.line((end, (back[0] + nx * head * 0.45, back[1] + ny * head * 0.45)), fill=color, width=line_width)
    draw.line((end, (back[0] - nx * head * 0.45, back[1] - ny * head * 0.45)), fill=color, width=line_width)


def _scale_bar_origin(
    scale_bar: ScaleBar,
    image_width: float,
    image_height: float,
    bar_width: float,
    bar_height: float,
) -> tuple[float, float]:
    offset_x = float(scale_bar.offset_x)
    offset_y = float(scale_bar.offset_y)
    if scale_bar.location == "Upper Left":
        return offset_x, offset_y
    if scale_bar.location == "Upper Right":
        return image_width - bar_width - offset_x, offset_y
    if scale_bar.location == "Lower Left":
        return offset_x, image_height - bar_height - offset_y
    return image_width - bar_width - offset_x, image_height - bar_height - offset_y


def _display_compatible(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype == np.uint8:
        return array
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return np.clip((array.astype(np.float32) / float(info.max)) * 255.0, 0, 255).astype(np.uint8)
    return np.clip(array * 255.0, 0, 255).astype(np.uint8)


def _rgba(value: str, opacity: float) -> tuple[int, int, int, int]:
    text = value.strip()
    alpha = max(0, min(255, int(round(255.0 * max(0.0, min(1.0, opacity))))))
    if text.startswith("#") and len(text) in {7, 9}:
        red = int(text[1:3], 16)
        green = int(text[3:5], 16)
        blue = int(text[5:7], 16)
        if len(text) == 9:
            alpha = int(text[7:9], 16)
        return red, green, blue, alpha
    return 255, 255, 255, alpha


def _font(size: float) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", max(1, int(round(size))))
    except OSError:
        return ImageFont.load_default()


def _asset_stem(asset: ImageAsset) -> str:
    return f"{_safe_name(Path(asset.filename).stem)}_{asset.id[:8]}"


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return safe.strip("_") or "item"
