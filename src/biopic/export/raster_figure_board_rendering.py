"""Figure-board raster rendering primitives and overlay drawing."""

from __future__ import annotations

from math import cos, pi, radians, sin
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

from biopic.imaging.io import BIOPIC_METADATA_KEY, image_metadata_text, image_metadata_tiff_extratags
from biopic.models.annotations import AnnotationKind, normalize_wedge_points
from biopic.models.figure_board import (
    FigureBoard,
    FigurePanel,
    adjusted_scale_bar_length,
)
from biopic.models.measurement import Measurement, MeasurementKind, ScaleBar, scale_bar_origin
from biopic.models.project import Project


def _panel_draw_size(
    image: Image.Image,
    panel_width: float,
    panel_height: float,
    zoom: float,
) -> tuple[int, int]:
    return _panel_draw_size_for_dimensions(
        image.width,
        image.height,
        panel_width,
        panel_height,
        zoom,
    )


def _panel_draw_size_for_dimensions(
    source_width: float,
    source_height: float,
    panel_width: float,
    panel_height: float,
    zoom: float,
) -> tuple[int, int]:
    target_width = max(1.0, float(panel_width) * zoom)
    target_height = max(1.0, float(panel_height) * zoom)
    source_aspect = float(source_width) / max(1.0, float(source_height))
    target_aspect = target_width / max(1.0, target_height)
    if source_aspect > target_aspect:
        draw_height = target_height
        draw_width = draw_height * source_aspect
    else:
        draw_width = target_width
        draw_height = draw_width / max(1e-6, source_aspect)
    return max(1, int(round(draw_width))), max(1, int(round(draw_height)))


def _rotated_panel_cover_size(
    panel_width: int,
    panel_height: int,
    rotation: float,
) -> tuple[float, float]:
    angle = abs(radians(rotation % 180.0))
    c = abs(cos(angle))
    s = abs(sin(angle))
    return (
        max(1.0, panel_width * c + panel_height * s),
        max(1.0, panel_width * s + panel_height * c),
    )


def _draw_panel_label(
    draw: ImageDraw.ImageDraw,
    board: FigureBoard,
    panel: FigurePanel,
    panel_rect: tuple[int, int, int, int],
) -> None:
    label = panel.label.strip()
    if not label:
        return
    font = _font(
        _points_to_px(panel.label_font_size_pt, board.page.dpi),
        bold=panel.label_bold,
        italic=panel.label_italic,
        family=panel.label_font_family,
    )
    bbox = draw.textbbox((0, 0), label, font=font)
    label_width = bbox[2] - bbox[0]
    label_height = bbox[3] - bbox[1]
    offset_x = _label_offset_px(panel.label_offset[0], panel_rect[2], board.page.dpi)
    offset_y = _label_offset_px(panel.label_offset[1], panel_rect[3], board.page.dpi)
    x = panel_rect[0] + min(max(0, offset_x), max(0, panel_rect[2] - label_width))
    y = panel_rect[1] + min(max(0, offset_y), max(0, panel_rect[3] - label_height))
    draw.text((x, y), label, fill=_rgb(panel.label_color, "#111111"), font=font)


def _render_image_overlays(
    project: Project,
    node_id: str,
    pixels: np.ndarray,
    *,
    include_scale_bars: bool = True,
    include_annotations: bool = True,
    include_measurements: bool = True,
) -> np.ndarray:
    has_scale_bars = include_scale_bars and any(
        scale_bar.image_node_id == node_id for scale_bar in project.scale_bars.values()
    )
    has_annotations = include_annotations and any(
        annotation.image_node_id == node_id and annotation.visible
        for annotation in project.annotations.values()
    )
    has_measurements = include_measurements and any(
        measurement.image_node_id == node_id for measurement in project.measurements.values()
    )
    if not has_scale_bars and not has_annotations and not has_measurements:
        return pixels
    image = Image.fromarray(_display_compatible(pixels)).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    if include_scale_bars:
        for scale_bar in project.scale_bars.values():
            if scale_bar.image_node_id == node_id:
                _draw_scale_bar_overlay(draw, image.size, scale_bar)
    if include_annotations:
        for annotation in project.annotations.values():
            if annotation.image_node_id == node_id and annotation.visible:
                _draw_annotation_overlay(image, draw, image.size, annotation)
    if include_measurements:
        for measurement in project.measurements.values():
            if measurement.image_node_id == node_id:
                _draw_measurement_overlay(draw, image.size, measurement)
    return np.asarray(image.convert("RGB"))


def _draw_panel_scale_bars(
    draw: ImageDraw.ImageDraw,
    project: Project,
    board: FigureBoard,
    panel: FigurePanel,
    image: Image.Image,
    panel_rect: tuple[int, int, int, int],
    hidden_value: tuple[float, str] | None = None,
) -> None:
    if panel.source_node_id is None:
        return
    draw_width, _draw_height = _panel_draw_size(
        image,
        panel_rect[2],
        panel_rect[3],
        max(0.1, float(panel.crop[2])),
    )
    display_scale = draw_width / max(1.0, float(image.width))
    panel_scale_bars = [
        scale_bar
        for scale_bar in project.scale_bars.values()
        if scale_bar.image_node_id == panel.source_node_id
    ]
    for scale_bar in panel_scale_bars:
        physical_length, pixel_length = adjusted_scale_bar_length(
            board,
            float(scale_bar.physical_length),
            float(scale_bar.pixel_length),
            display_scale,
            panel_rect[2],
        )
        length = max(1.0, pixel_length * display_scale)
        thickness = max(1.0, _points_to_px(float(scale_bar.width_px), board.page.dpi))
        font_size = _points_to_px(float(scale_bar.font_size), board.page.dpi)
        text_height = max(float(font_size) * 1.6, 6.0)
        padding_x = max(3.0, panel_rect[2] * 0.02)
        padding_y = max(3.0, panel_rect[3] * 0.02)
        x = panel_rect[0] + panel_rect[2] - length - padding_x
        show_value = scale_bar.display_length and hidden_value != (
            round(float(physical_length), 9),
            str(scale_bar.unit),
        )
        y = panel_rect[1] + panel_rect[3] - thickness - padding_y - (
            text_height if show_value else 0.0
        )
        x = max(panel_rect[0] + padding_x, x)
        y = max(panel_rect[1] + padding_y, y)
        color = _rgba(scale_bar.foreground, scale_bar.opacity)
        line_width = max(1, int(round(thickness)))
        draw.line((x, y, x + length, y), fill=color, width=line_width)
        if show_value:
            font = _font(font_size, bold=scale_bar.bold, italic=scale_bar.italic, family=scale_bar.font_family)
            text = f"{physical_length:g} {scale_bar.unit}"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_x = x + length / 2.0 - (bbox[2] - bbox[0]) / 2.0
            draw.text((text_x, y + thickness + 1.0), text, fill=color, font=font)


def _common_displayed_scale_bar_value_key(
    project: Project,
    board: FigureBoard,
    image_lookup: dict[str, np.ndarray],
    content: tuple[int, int, int, int],
    gutter_x: int,
    gutter_y: int,
) -> tuple[float, str] | None:
    counts: dict[tuple[float, str], int] = {}
    for panel in board.panels:
        if panel.source_node_id is None:
            continue
        pixels = image_lookup.get(panel.source_node_id)
        if pixels is None:
            continue
        image = Image.fromarray(_display_compatible(pixels))
        panel_rect = _panel_rect_px(panel, content, gutter_x, gutter_y)
        draw_width, _draw_height = _panel_draw_size(
            image,
            panel_rect[2],
            panel_rect[3],
            max(0.1, float(panel.crop[2])),
        )
        display_scale = draw_width / max(1.0, float(image.width))
        for scale_bar in project.scale_bars.values():
            if scale_bar.image_node_id != panel.source_node_id or not scale_bar.display_length:
                continue
            physical_length, _pixel_length = adjusted_scale_bar_length(
                board,
                float(scale_bar.physical_length),
                float(scale_bar.pixel_length),
                display_scale,
                panel_rect[2],
            )
            key = (round(float(physical_length), 9), str(scale_bar.unit))
            counts[key] = counts.get(key, 0) + 1
    repeated = [(count, key) for key, count in counts.items() if count > 1]
    if not repeated:
        return None
    repeated.sort(key=lambda item: (-item[0], item[1]))
    return repeated[0][1]


def _draw_panel_measurements(
    draw: ImageDraw.ImageDraw,
    project: Project,
    panel: FigurePanel,
    image: Image.Image,
    panel_rect: tuple[int, int, int, int],
) -> None:
    if panel.source_node_id is None:
        return
    source_width = max(1.0, float(image.width))
    source_height = max(1.0, float(image.height))
    panel_x, panel_y, panel_width, panel_height = panel_rect
    for measurement in project.measurements.values():
        if measurement.image_node_id != panel.source_node_id:
            continue
        mapped = [
            (
                panel_x + point.x / source_width * panel_width,
                panel_y + point.y / source_height * panel_height,
            )
            for point in measurement.points
        ]
        _draw_measurement_shape(
            draw,
            measurement,
            mapped,
            max(1, int(round(measurement.line_width))),
        )
        label_xy = _measurement_label_xy(measurement, mapped)
        _draw_measurement_text(
            draw,
            measurement,
            label_xy,
            panel_width / source_width,
            panel_height / source_height,
        )
        _draw_measurement_side_labels(draw, measurement, mapped, panel_width, source_width)


def _draw_scale_bar_overlay(
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
    x, y = scale_bar_origin(scale_bar, float(width), float(height), bar_width, bar_height)
    if scale_bar.background:
        pad = max(4.0, thickness * 2.0)
        draw.rectangle(
            (x - pad, y - pad, x + bar_width + pad, y + bar_height + pad),
            fill=_rgba(scale_bar.background, scale_bar.opacity),
        )
    color = _rgba(scale_bar.foreground, scale_bar.opacity)
    line_width = max(1, int(round(thickness)))
    if is_vertical:
        draw.line((x + thickness / 2.0, y, x + thickness / 2.0, y + length), fill=color, width=line_width)
    else:
        draw.line((x, y + thickness / 2.0, x + length, y + thickness / 2.0), fill=color, width=line_width)
    if scale_bar.display_length:
        text = f"{scale_bar.physical_length:g} {scale_bar.unit}"
        font = _font(max(1, int(round(scale_bar.font_size))), bold=scale_bar.bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if is_vertical:
            text_xy = (x + thickness + 6.0, y + length / 2.0)
        else:
            text_xy = (x + length / 2.0 - (bbox[2] - bbox[0]) / 2.0, y + thickness + 4.0)
        draw.text(text_xy, text, fill=color, font=font)


def _draw_measurement_overlay(
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    measurement: Measurement,
) -> None:
    _width, _height = image_size
    points = [(point.x, point.y) for point in measurement.points]
    _draw_measurement_shape(draw, measurement, points, max(1, int(round(measurement.line_width))))
    label_xy = _measurement_label_xy(measurement, points)
    _draw_measurement_text(draw, measurement, label_xy)
    _draw_measurement_side_labels(draw, measurement, points, _width, _width)


def _draw_measurement_shape(
    draw: ImageDraw.ImageDraw,
    measurement: Measurement,
    points: list[tuple[float, float]],
    line_width: int,
) -> None:
    if not points:
        return
    color = _rgba(measurement.color, 1.0)
    if measurement.kind is MeasurementKind.LINE and len(points) >= 2:
        draw.line((points[0], points[1]), fill=color, width=line_width)
    elif measurement.kind is MeasurementKind.RECTANGLE:
        if len(points) >= 4:
            draw.line(points[:4] + [points[0]], fill=color, width=line_width)
        elif len(points) >= 2:
            draw.rectangle((points[0], points[1]), outline=color, width=line_width)
    elif measurement.kind is MeasurementKind.ELLIPSE:
        if len(points) >= 3:
            draw.line(_ellipse_polyline(points), fill=color, width=line_width)
        elif len(points) >= 2:
            draw.ellipse((points[0], points[1]), outline=color, width=line_width)
    elif measurement.kind is MeasurementKind.POLYGON and len(points) >= 3:
        draw.line(points + [points[0]], fill=color, width=line_width, joint="curve")
    elif len(points) >= 2:
        draw.line(points, fill=color, width=line_width, joint="curve")


def _ellipse_polyline(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    center, major_point, minor_point = points[0], points[1], points[2]
    major = (major_point[0] - center[0], major_point[1] - center[1])
    minor = (minor_point[0] - center[0], minor_point[1] - center[1])
    polyline = []
    for index in range(73):
        angle = 2.0 * pi * index / 72.0
        polyline.append(
            (
                center[0] + cos(angle) * major[0] + sin(angle) * minor[0],
                center[1] + cos(angle) * major[1] + sin(angle) * minor[1],
            )
        )
    return polyline


def _measurement_label_xy(
    measurement: Measurement,
    points: list[tuple[float, float]],
) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    if measurement.kind is MeasurementKind.LINE and len(points) >= 2:
        return (
            (points[0][0] + points[1][0]) / 2.0 + 6.0,
            (points[0][1] + points[1][1]) / 2.0 + 6.0,
        )
    return sum(point[0] for point in points) / len(points) + 6.0, min(point[1] for point in points) - 18.0


def _draw_measurement_text(
    draw: ImageDraw.ImageDraw,
    measurement: Measurement,
    base_xy: tuple[float, float],
    x_scale: float = 1.0,
    y_scale: float = 1.0,
) -> None:
    font = _font(
        max(1, int(round(measurement.font_size))),
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
        draw.text(label_xy, measurement.label_text(), fill=color, font=font)
    draw.text(value_xy, measurement.value_text(), fill=color, font=font)


def _draw_measurement_side_labels(
    draw: ImageDraw.ImageDraw,
    measurement: Measurement,
    points: list[tuple[float, float]],
    panel_width: float,
    source_width: float,
    font_size_px: int | None = None,
) -> None:
    if measurement.kind is not MeasurementKind.RECTANGLE or not measurement.show_side_lengths:
        return
    if len(points) < 4:
        return
    unit = measurement.display_unit
    width, height = measurement.rectangle_side_lengths_display(unit)
    decimals = max(0, min(6, int(measurement.decimal_places)))
    font_size = max(1, int(round(measurement.font_size))) if font_size_px is None else font_size_px
    font = _font(
        font_size,
        bold=measurement.bold,
        italic=measurement.italic,
        family=measurement.font_family,
    )
    color = _rgba(measurement.color, 1.0)
    for label, point in (
        (f"{width:.{decimals}f} {unit}", _midpoint_xy(points[0], points[1])),
        (f"{height:.{decimals}f} {unit}", _midpoint_xy(points[1], points[2])),
    ):
        draw.text(point, label, fill=color, font=font)


def _midpoint_xy(
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float]:
    return (a[0] + b[0]) / 2.0 + 4.0, (a[1] + b[1]) / 2.0 + 4.0


def _draw_annotation_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    annotation: object,
) -> None:
    width, height = image_size
    annotation_points = (
        normalize_wedge_points(list(annotation.points))
        if annotation.kind is AnnotationKind.WEDGE
        else annotation.points
    )
    points = [(float(x) * width, float(y) * height) for x, y in annotation_points]
    if not points:
        return
    color = _rgba(annotation.color, annotation.opacity)
    if annotation.kind is AnnotationKind.TEXT:
        draw.text(points[0], annotation.text or "Label", fill=color, font=_font(int(round(annotation.size)), bold=False))
        return
    if len(points) < 2:
        return
    line_width = max(1, int(round(annotation.line_width)))
    if annotation.kind is AnnotationKind.WEDGE:
        _draw_wedge_overlay(
            image,
            draw,
            points,
            _rgba(annotation.fill or annotation.color, annotation.opacity),
            annotation.line_width,
        )
    else:
        draw.line(points, fill=color, width=line_width, joint="curve")
        if annotation.kind is AnnotationKind.ARROW:
            _draw_arrow_overlay(draw, points[-2], points[-1], color, line_width)


def _draw_wedge_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    color: tuple[int, int, int, int],
    line_width: float,
) -> None:
    _ = draw, line_width
    if len(points) < 2:
        return
    _draw_antialiased_polygon(image, _normal_wedge_triangle(points, 0.0), color)


def _draw_antialiased_polygon(
    image: Image.Image,
    points: list[tuple[float, float]],
    color: tuple[int, int, int, int],
    *,
    scale: int = 4,
) -> None:
    if len(points) < 3 or color[3] <= 0:
        return
    min_x = int(max(0, np.floor(min(point[0] for point in points) - 2)))
    min_y = int(max(0, np.floor(min(point[1] for point in points) - 2)))
    max_x = int(min(image.width, np.ceil(max(point[0] for point in points) + 2)))
    max_y = int(min(image.height, np.ceil(max(point[1] for point in points) + 2)))
    if max_x <= min_x or max_y <= min_y:
        return
    width = max_x - min_x
    height = max_y - min_y
    hi_size = (max(1, width * scale), max(1, height * scale))
    hi_points = [
        ((point[0] - min_x) * scale, (point[1] - min_y) * scale)
        for point in points
    ]
    mask = Image.new("L", hi_size, 0)
    ImageDraw.Draw(mask).polygon(hi_points, fill=color[3])
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    patch = Image.new("RGBA", (width, height), color[:3] + (0,))
    patch.putalpha(mask)
    image.alpha_composite(patch, (min_x, min_y))


def _normal_wedge_triangle(
    points: list[tuple[float, float]],
    minimum_base_width: float,
) -> list[tuple[float, float]]:
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
        return [tip, base_a, base_b]
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


def _draw_arrow_overlay(
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


def _export_dimensions_px(board: FigureBoard) -> tuple[int, int]:
    page_width, page_height = board.page.pixel_dimensions()
    left = _mm_to_px(board.margin_left, board.page.dpi)
    right = _mm_to_px(board.margin_right, board.page.dpi)
    top = _mm_to_px(board.margin_top, board.page.dpi)
    bottom = _mm_to_px(board.margin_bottom, board.page.dpi)
    caption = _caption_height_px(board, page_height)
    return (
        max(1, page_width - left - right),
        max(1, page_height - top - bottom - caption),
    )


def _content_rect_px(board: FigureBoard, page_width: int, page_height: int) -> tuple[int, int, int, int]:
    printable = (
        0,
        0,
        page_width,
        page_height,
    )
    x, y, width, height = board.content_rect
    return (
        printable[0] + int(round(float(x) * printable[2])),
        printable[1] + int(round(float(y) * printable[3])),
        max(1, int(round(float(width) * printable[2]))),
        max(1, int(round(float(height) * printable[3]))),
    )


def _panel_rect_px(
    panel: FigurePanel,
    content: tuple[int, int, int, int],
    gutter_x: int,
    gutter_y: int,
) -> tuple[int, int, int, int]:
    x = content[0] + int(round(panel.rect[0] * content[2]))
    y = content[1] + int(round(panel.rect[1] * content[3]))
    width = int(round(panel.rect[2] * content[2]))
    height = int(round(panel.rect[3] * content[3]))
    left_gap = 0 if panel.rect[0] <= 0.0 else gutter_x // 2
    right_gap = 0 if panel.rect[0] + panel.rect[2] >= 1.0 else gutter_x // 2
    top_gap = 0 if panel.rect[1] <= 0.0 else gutter_y // 2
    bottom_gap = 0 if panel.rect[1] + panel.rect[3] >= 1.0 else gutter_y // 2
    return (
        x + left_gap,
        y + top_gap,
        max(1, width - left_gap - right_gap),
        max(1, height - top_gap - bottom_gap),
    )


def _label_offset_px(stored_offset: float, panel_length_px: int, dpi: int) -> int:
    if stored_offset <= 1.0:
        return int(round(stored_offset * panel_length_px))
    return _mm_to_px(stored_offset, dpi)


def _caption_height_px(board: FigureBoard, page_height: int) -> int:
    text = board.caption.visible_text().strip()
    if not text:
        return 0
    lines = max(2, len(text.splitlines()))
    line_height = _mm_to_px(4.2, board.page.dpi)
    return min(
        int(round(page_height * 0.35)),
        max(int(round(page_height * 0.10)), lines * line_height),
    )


def _points_to_px(points: float, dpi: int) -> int:
    return max(1, int(round(points * dpi / 72.0)))


def _mm_to_px(length_mm: float, dpi: int) -> int:
    return int(round(float(length_mm) * dpi / 25.4))


def _font(
    pixel_size: int,
    *,
    bold: bool,
    italic: bool = False,
    family: str = "Arial",
) -> ImageFont.ImageFont:
    family_base = "arial" if family.strip().lower() == "arial" else family.strip()
    candidates = (
        "arialbi.ttf" if bold and italic else "",
        "arialbd.ttf" if bold else "",
        "ariali.ttf" if italic else "",
        "arial.ttf",
        f"{family_base} Bold Italic.ttf" if bold and italic else "",
        f"{family_base} Bold.ttf" if bold else "",
        f"{family_base} Italic.ttf" if italic else "",
        f"{family_base}.ttf",
    )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, max(1, pixel_size))
        except OSError:
            continue
    return ImageFont.load_default()


def _save_canvas(
    canvas: Image.Image,
    path: Path,
    dpi: int,
    *,
    metadata: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        kwargs: dict[str, object] = {
            "resolution": (float(dpi), float(dpi)),
            "resolutionunit": "INCH",
        }
        if metadata:
            kwargs["description"] = image_metadata_text(metadata)
            kwargs["extratags"] = image_metadata_tiff_extratags(metadata)
        tifffile.imwrite(
            path,
            np.asarray(canvas),
            **kwargs,
        )
        return
    save_kwargs: dict[str, object] = {"dpi": (dpi, dpi)}
    if metadata and suffix == ".png":
        pnginfo = PngInfo()
        pnginfo.add_text(BIOPIC_METADATA_KEY, image_metadata_text(metadata))
        save_kwargs["pnginfo"] = pnginfo
    elif metadata and suffix in {".jpg", ".jpeg"}:
        exif = canvas.getexif()
        exif[270] = image_metadata_text(metadata)
        save_kwargs["exif"] = exif
    canvas.save(path, **save_kwargs)

def _display_compatible(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    while array.ndim > 3:
        array = array[0]
    if array.ndim == 3 and array.shape[-1] not in {3, 4}:
        array = array[0]
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return np.clip((array.astype(np.float32) / float(info.max)) * 255.0, 0, 255).astype(np.uint8)
    return np.clip(array * 255.0, 0, 255).astype(np.uint8)

def _rgb(value: str, fallback: str) -> tuple[int, int, int]:
    text = value if value.startswith("#") and len(value) >= 7 else fallback
    try:
        return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    except ValueError:
        return int(fallback[1:3], 16), int(fallback[3:5], 16), int(fallback[5:7], 16)


def _rgba(value: str, opacity: float) -> tuple[int, int, int, int]:
    red, green, blue = _rgb(value[:7] if len(value) == 9 else value, "#ffffff")
    alpha = max(0, min(255, int(round(255.0 * max(0.0, min(1.0, opacity))))))
    if value.startswith("#") and len(value) == 9:
        try:
            alpha = int(value[7:9], 16)
        except ValueError:
            pass
    return red, green, blue, alpha
