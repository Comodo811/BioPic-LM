"""Figure-board raster export and overlay rendering helpers."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from biopic.export.raster_figure_board_rendering import (
    _common_displayed_scale_bar_value_key,
    _content_rect_px,
    _display_compatible,
    _draw_antialiased_polygon,
    _draw_measurement_shape,
    _draw_measurement_side_labels,
    _draw_panel_label,
    _draw_panel_scale_bars,
    _export_dimensions_px,
    _font,
    _measurement_label_xy,
    _mm_to_px,
    _panel_draw_size,
    _panel_rect_px,
    _points_to_px,
    _render_image_overlays,
    _rgba,
    _rotated_panel_cover_size,
    _save_canvas,
)
from biopic.export.raster_figure_board_rendering import (
    _draw_measurement_overlay as _draw_measurement_overlay,
)
from biopic.imaging.background import fill_transparent_regions_with_background
from biopic.imaging.io import (
    load_asset_pixels,
)
from biopic.imaging.project_render import asset_for_source_node, render_project_image
from biopic.models.annotations import AnnotationKind, normalize_wedge_points
from biopic.models.figure_board import (
    FigureBoard,
    FigurePanel,
    panel_empty_background_signature,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project


def export_simple_figure_board(
    board: FigureBoard, assets_by_node: dict[str, ImageAsset], path: Path
) -> None:
    """Export a board from pre-resolved node-to-asset mappings."""
    image_lookup = {
        node_id: load_asset_pixels(asset) for node_id, asset in assets_by_node.items()
    }
    _export_figure_board_pixels(board, image_lookup, path)


def export_project_figure_board(
    project: Project,
    board: FigureBoard,
    path: Path,
    *,
    save_caption_text: bool = True,
    save_caption_latex: bool = True,
) -> None:
    """Export a board using current rendered project images and board transforms."""
    if path.suffix.lower() == ".tex":
        export_project_figure_board_latex(project, board, path)
        return
    image_lookup: dict[str, np.ndarray] = {}
    for panel in board.panels:
        if panel.source_node_id and panel.source_node_id not in image_lookup:
            pixels = render_project_image(project, panel.source_node_id)
            if pixels is not None:
                image_lookup[panel.source_node_id] = _render_image_overlays(
                    project,
                    panel.source_node_id,
                    pixels,
                    include_scale_bars=False,
                    include_annotations=False,
                    include_measurements=False,
                )
    _export_figure_board_pixels(
        board,
        image_lookup,
        path,
        project=project,
        metadata=_figure_board_metadata(project, board),
    )
    _export_caption_sidecars(
        board,
        path,
        save_text=save_caption_text,
        save_latex=save_caption_latex,
    )


def export_project_figure_board_latex(project: Project, board: FigureBoard, path: Path) -> None:
    """Export a LaTeX figure file plus a sibling board image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image_path = path.with_suffix(".png")
    export_project_figure_board(project, board, image_path)
    caption = board.caption.visible_text().strip()
    label = _latex_label(board)
    path.write_text(
        "\n".join(
            [
                r"\begin{figure}[htbp]",
                r"  \centering",
                f"  \\includegraphics[width=\\textwidth]{{{image_path.name}}}",
                f"  \\caption{{{caption}}}",
                f"  \\label{{{label}}}",
                r"\end{figure}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _export_figure_board_pixels(
    board: FigureBoard,
    image_lookup: dict[str, np.ndarray],
    path: Path,
    *,
    project: Project | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = _export_dimensions_px(board)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    content = _content_rect_px(board, width, height)
    gutter_x = _mm_to_px(board.horizontal_gutter, board.page.dpi)
    gutter_y = _mm_to_px(board.vertical_gutter, board.page.dpi)
    hidden_scale_bar_value = (
        _common_displayed_scale_bar_value_key(
            project,
            board,
            image_lookup,
            content,
            gutter_x,
            gutter_y,
        )
        if project is not None and board.hide_common_scale_bar_value
        else None
    )
    panel_image_jobs: list[tuple[FigurePanel, Image.Image, tuple[int, int, int, int]]] = []
    for panel in board.panels:
        panel_rect = _panel_rect_px(panel, content, gutter_x, gutter_y)
        if panel.source_node_id:
            pixels = image_lookup.get(panel.source_node_id)
            if pixels is not None:
                image = Image.fromarray(_display_compatible(pixels)).convert("RGBA")
                panel_image = _panel_image(
                    image,
                    panel,
                    panel_rect[2],
                    panel_rect[3],
                    cover_rotation=False,
                )
                canvas.paste(
                    panel_image.convert("RGB"),
                    (panel_rect[0], panel_rect[1]),
                    panel_image.getchannel("A"),
                )
                panel_image_jobs.append((panel, image, panel_rect))
    if project is not None:
        for panel, image, panel_rect in panel_image_jobs:
            _draw_panel_scale_bars(
                draw,
                project,
                board,
                panel,
                image,
                panel_rect,
                hidden_scale_bar_value,
            )
        for panel, image, panel_rect in panel_image_jobs:
            _draw_panel_vector_overlays(
                canvas,
                project,
                board,
                panel,
                image,
                panel_rect,
                cover_rotation=False,
            )
    for panel in board.panels:
        panel_rect = _panel_rect_px(panel, content, gutter_x, gutter_y)
        _draw_panel_label(draw, board, panel, panel_rect)
    _save_canvas(canvas, path, board.page.dpi, metadata=metadata)


def _draw_panel_vector_overlays(
    canvas: Image.Image,
    project: Project,
    board: FigureBoard,
    panel: FigurePanel,
    image: Image.Image,
    panel_rect: tuple[int, int, int, int],
    *,
    cover_rotation: bool,
) -> None:
    if panel.source_node_id is None:
        return
    panel_x, panel_y, panel_width, panel_height = panel_rect
    if panel_width <= 0 or panel_height <= 0:
        return
    if cover_rotation:
        target_width, target_height = _rotated_panel_cover_size(
            panel_width,
            panel_height,
            float(panel.rotation),
        )
    else:
        target_width, target_height = panel_width, panel_height
    draw_width, draw_height = _panel_draw_size(
        image,
        target_width,
        target_height,
        max(0.1, float(panel.crop[2])),
    )
    center_x = panel_x + float(panel.crop[0]) * panel_width
    center_y = panel_y + float(panel.crop[1]) * panel_height
    local_rect = (
        -draw_width / 2.0,
        -draw_height / 2.0,
        float(draw_width),
        float(draw_height),
    )
    overlay = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay, "RGBA")
    transform = _panel_overlay_transform(center_x, center_y, float(panel.rotation))
    _draw_panel_annotations(
        overlay,
        overlay_draw,
        project,
        board,
        panel,
        image.size,
        local_rect,
        transform,
    )
    _draw_panel_measurements(
        overlay_draw,
        project,
        board,
        panel,
        image.size,
        local_rect,
        transform,
    )
    if canvas.mode == "RGBA":
        canvas.alpha_composite(overlay)
    else:
        canvas.paste(overlay.convert(canvas.mode), (0, 0), overlay.getchannel("A"))


def _panel_overlay_transform(
    center_x: float,
    center_y: float,
    rotation: float,
):
    angle = radians(rotation)
    cosine = cos(angle)
    sine = sin(angle)

    def transform(x: float, y: float) -> tuple[float, float]:
        return (
            center_x + x * cosine - y * sine,
            center_y + x * sine + y * cosine,
        )

    return transform


def _draw_panel_annotations(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    project: Project,
    board: FigureBoard,
    panel: FigurePanel,
    source_size: tuple[int, int],
    local_rect: tuple[float, float, float, float],
    transform,
) -> None:
    _ = source_size
    left, top, width, height = local_rect
    for annotation in project.annotations.values():
        if annotation.image_node_id != panel.source_node_id or not annotation.visible:
            continue
        annotation_points = (
            normalize_wedge_points(list(annotation.points))
            if annotation.kind is AnnotationKind.WEDGE
            else annotation.points
        )
        points = [
            transform(left + float(x) * width, top + float(y) * height)
            for x, y in annotation_points
        ]
        if annotation.kind is AnnotationKind.TEXT and points:
            draw.text(
                points[0],
                annotation.text or "Label",
                fill=_rgba(annotation.color, annotation.opacity),
                font=_font(
                    _points_to_px(float(annotation.size), board.page.dpi),
                    bold=False,
                    family=annotation.font,
                ),
            )
        elif len(points) >= 2:
            if annotation.kind is AnnotationKind.WEDGE:
                fill = _rgba(annotation.fill or annotation.color, annotation.opacity)
                _draw_antialiased_polygon(
                    image,
                    _visible_wedge_points(
                        points,
                        0.0,
                    ),
                    fill,
                )
            else:
                draw.line(
                    points,
                    fill=_rgba(annotation.color, annotation.opacity),
                    width=_points_to_px(float(annotation.line_width), board.page.dpi),
                    joint="curve",
                )

def _visible_wedge_points(
    points: list[tuple[float, float]],
    minimum_base_width: float,
) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    if len(points) == 2:
        base_mid = points[0]
        tip = points[1]
        axis_x = tip[0] - base_mid[0]
        axis_y = tip[1] - base_mid[1]
        axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
        perp_x = -axis_y / axis_length
        perp_y = axis_x / axis_length
        half = max(minimum_base_width / 2.0, axis_length * 0.22, 0.5)
        return [
            tip,
            (base_mid[0] - perp_x * half, base_mid[1] - perp_y * half),
            (base_mid[0] + perp_x * half, base_mid[1] + perp_y * half),
        ]
    tip = points[0]
    base_a = points[1]
    base_b = points[2]
    base_mid = ((base_a[0] + base_b[0]) / 2.0, (base_a[1] + base_b[1]) / 2.0)
    dx = base_b[0] - base_a[0]
    dy = base_b[1] - base_a[1]
    base_width = (dx * dx + dy * dy) ** 0.5
    if base_width >= minimum_base_width:
        return points
    axis_x = tip[0] - base_mid[0]
    axis_y = tip[1] - base_mid[1]
    axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
    perp_x = -axis_y / axis_length
    perp_y = axis_x / axis_length
    half = max(minimum_base_width / 2.0, 0.5)
    return [
        tip,
        (base_mid[0] - perp_x * half, base_mid[1] - perp_y * half),
        (base_mid[0] + perp_x * half, base_mid[1] + perp_y * half),
    ]


def _draw_panel_measurements(
    draw: ImageDraw.ImageDraw,
    project: Project,
    board: FigureBoard,
    panel: FigurePanel,
    source_size: tuple[int, int],
    local_rect: tuple[float, float, float, float],
    transform,
) -> None:
    source_width = max(1.0, float(source_size[0]))
    source_height = max(1.0, float(source_size[1]))
    left, top, width, height = local_rect
    for measurement in project.measurements.values():
        if measurement.image_node_id != panel.source_node_id:
            continue
        local_points = [
            (
                left + point.x / source_width * width,
                top + point.y / source_height * height,
            )
            for point in measurement.points
        ]
        mapped = [transform(x, y) for x, y in local_points]
        _draw_measurement_shape(
            draw,
            measurement,
            mapped,
            _points_to_px(float(measurement.line_width), board.page.dpi),
        )
        _draw_panel_measurement_text(
            draw,
            measurement,
            board,
            _measurement_label_xy(measurement, local_points),
            transform,
            width / source_width,
            height / source_height,
        )
        _draw_measurement_side_labels(
            draw,
            measurement,
            mapped,
            width,
            source_width,
            _points_to_px(float(measurement.font_size), board.page.dpi),
        )


def _draw_panel_measurement_text(
    draw: ImageDraw.ImageDraw,
    measurement,
    board: FigureBoard,
    base_xy: tuple[float, float],
    transform,
    x_scale: float,
    y_scale: float,
) -> None:
    font = _font(
        _points_to_px(float(measurement.font_size), board.page.dpi),
        bold=measurement.bold,
        italic=measurement.italic,
        family=measurement.font_family,
    )
    color = _rgba(measurement.color, 1.0)
    label_xy = (
        base_xy[0] + measurement.label_offset[0] * x_scale,
        base_xy[1] + measurement.label_offset[1] * y_scale,
    )
    value_y_shift = 18.0 * y_scale if measurement.show_label and measurement.label else 0.0
    value_xy = (
        base_xy[0] + measurement.value_offset[0] * x_scale,
        base_xy[1] + measurement.value_offset[1] * y_scale + value_y_shift,
    )
    if measurement.label_text():
        _draw_baseline_text(
            draw,
            transform(*label_xy),
            measurement.label_text(),
            color,
            font,
        )
    _draw_baseline_text(draw, transform(*value_xy), measurement.value_text(), color, font)


def _draw_baseline_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fill: tuple[int, int, int, int],
    font,
) -> None:
    try:
        draw.text(xy, text, fill=fill, font=font, anchor="ls")
    except (TypeError, ValueError):
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((xy[0], xy[1] - (bbox[3] - bbox[1])), text, fill=fill, font=font)


def _panel_image(
    image: Image.Image,
    panel: FigurePanel,
    width: int,
    height: int,
    *,
    cover_rotation: bool = False,
) -> Image.Image:
    """Return the panel-clipped image with crop, zoom and rotation applied."""
    width = max(1, int(width))
    height = max(1, int(height))
    baked = _baked_empty_background_image(panel, width, height)
    if baked is not None:
        return baked
    zoom = max(0.1, float(panel.crop[2]))
    if cover_rotation:
        target_width, target_height = _rotated_panel_cover_size(
            width,
            height,
            float(panel.rotation),
        )
    else:
        target_width, target_height = width, height
    draw_width, draw_height = _panel_draw_size(image, target_width, target_height, zoom)
    resized = image.resize((draw_width, draw_height), Image.Resampling.LANCZOS)
    center_x = float(panel.crop[0]) * width
    center_y = float(panel.crop[1]) * height
    pad = max(width, height, draw_width, draw_height)
    layer = Image.new("RGBA", (width + pad * 2, height + pad * 2), (255, 255, 255, 0))
    work_center = (pad + center_x, pad + center_y)
    paste_x = int(round(work_center[0] - draw_width / 2.0))
    paste_y = int(round(work_center[1] - draw_height / 2.0))
    layer.alpha_composite(resized, (paste_x, paste_y))
    if abs(float(panel.rotation)) > 0.001:
        layer = layer.rotate(
            -float(panel.rotation),
            resample=Image.Resampling.BICUBIC,
            center=work_center,
            expand=False,
        )
    panel_image = layer.crop((pad, pad, pad + width, pad + height))
    if panel.fill_empty_background:
        filled = fill_transparent_regions_with_background(np.asarray(panel_image))
        panel_image = Image.fromarray(filled)
    return panel_image


def _baked_empty_background_image(
    panel: FigurePanel,
    width: int,
    height: int,
) -> Image.Image | None:
    if not panel.empty_background_path or panel.source_node_id is None:
        return None
    stored_signature = panel.empty_background_signature
    if (
        stored_signature is None
        or len(stored_signature) < 3
        or stored_signature[:3] != panel_empty_background_signature(panel, 1, 1)[:3]
    ):
        return None
    path = Path(panel.empty_background_path)
    if not path.exists():
        return None
    try:
        image = Image.open(path).convert("RGBA")
    except OSError:
        return None
    size = (max(1, int(width)), max(1, int(height)))
    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image

def _figure_board_metadata(project: Project, board: FigureBoard) -> dict[str, object]:
    sources: dict[str, object] = {}
    source_metadata: list[dict[str, object]] = []
    for panel in board.panels:
        if panel.source_node_id is None:
            continue
        asset = asset_for_source_node(project, panel.source_node_id)
        metadata = _source_image_metadata(project, panel.source_node_id)
        if asset is None or not metadata:
            continue
        source_metadata.append(metadata)
        key = panel.label or panel.id
        sources[key] = {
            "source_node_id": panel.source_node_id,
            "asset_id": asset.id,
            "filename": asset.filename,
            "metadata": metadata,
        }
    if not sources:
        return {}
    result: dict[str, object] = {
        "metadata_profile": "Figure Board",
        "figure_board": board.name,
        "figure_sources": sources,
    }
    if len(source_metadata) == 1:
        result.update(source_metadata[0])
    return result


def _source_image_metadata(project: Project, node_id: str) -> dict[str, object]:
    asset = asset_for_source_node(project, node_id)
    metadata: dict[str, object] = {} if asset is None else dict(asset.metadata)
    calibration = project.calibrations.get(node_id)
    if calibration is not None:
        metadata.setdefault("physical_pixel_size", calibration.unit_per_pixel)
        metadata.setdefault("physical_pixel_unit", calibration.unit)
        metadata.setdefault("unit_per_pixel", calibration.unit_per_pixel)
        metadata.setdefault("pixels_per_unit", calibration.pixels_per_unit)
        metadata.setdefault("pixel_aspect_ratio", calibration.pixel_aspect_ratio)
        metadata.setdefault("calibration_source", calibration.source)
    return metadata


def _export_caption_sidecars(
    board: FigureBoard,
    image_path: Path,
    *,
    save_text: bool = True,
    save_latex: bool = True,
) -> None:
    caption = board.caption.visible_text().strip()
    text_path = image_path.with_suffix(".caption.txt")
    tex_path = image_path.with_suffix(".caption.tex")
    if not save_text or not caption:
        text_path.unlink(missing_ok=True)
    if not save_latex or not caption:
        tex_path.unlink(missing_ok=True)
    if not caption or not (save_text or save_latex):
        return
    if save_text:
        text_path.write_text(caption + "\n", encoding="utf-8")
    if save_latex:
        tex_path.write_text(
            "\n".join(
                [
                    f"\\caption{{{caption}}}",
                    f"\\label{{{_latex_label(board)}}}",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _latex_label(board: FigureBoard) -> str:
    safe = "".join(
        char.lower() if char.isalnum() else "-"
        for char in (board.name or board.id).strip()
    ).strip("-")
    return f"fig:{safe or board.id}"
