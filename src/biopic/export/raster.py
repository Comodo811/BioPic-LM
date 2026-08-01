"""Raster image and figure-board export."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont

from biopic.imaging.io import load_asset_pixels
from biopic.imaging.project_render import render_project_image
from biopic.models.annotations import AnnotationKind
from biopic.models.figure_board import FigureBoard, FigurePanel, adjusted_scale_bar_length
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project


def export_image(image: np.ndarray, path: Path, *, dpi: int = 300) -> None:
    """Export a current image to TIFF/PNG/JPEG/BMP."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        tifffile.imwrite(path, image, resolution=(dpi, dpi))
        return
    pil = Image.fromarray(_display_compatible(image))
    if suffix in {".jpg", ".jpeg"} and pil.mode in {"RGBA", "LA", "P"}:
        pil = pil.convert("RGB")
    pil.save(path, dpi=(dpi, dpi))


def export_simple_figure_board(
    board: FigureBoard, assets_by_node: dict[str, ImageAsset], path: Path
) -> None:
    """Export a board from pre-resolved node-to-asset mappings."""
    image_lookup = {
        node_id: load_asset_pixels(asset) for node_id, asset in assets_by_node.items()
    }
    _export_figure_board_pixels(board, image_lookup, path)


def export_project_figure_board(project: Project, board: FigureBoard, path: Path) -> None:
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
                )
    _export_figure_board_pixels(board, image_lookup, path, project=project)
    _export_caption_sidecars(board, path)


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
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = _export_dimensions_px(board)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    content = _content_rect_px(board, width, height)
    gutter_x = _mm_to_px(board.horizontal_gutter, board.page.dpi)
    gutter_y = _mm_to_px(board.vertical_gutter, board.page.dpi)
    for panel in board.panels:
        panel_rect = _panel_rect_px(panel, content, gutter_x, gutter_y)
        if panel.source_node_id:
            pixels = image_lookup.get(panel.source_node_id)
            if pixels is not None:
                image = Image.fromarray(_display_compatible(pixels)).convert("RGBA")
                panel_image = _panel_image(image, panel, panel_rect[2], panel_rect[3])
                canvas.paste(
                    panel_image.convert("RGB"),
                    (panel_rect[0], panel_rect[1]),
                    panel_image.getchannel("A"),
                )
                if project is not None:
                    _draw_panel_scale_bars(draw, project, board, panel, image, panel_rect)
        _draw_panel_label(draw, board, panel, panel_rect)
    _save_canvas(canvas, path, board.page.dpi)


def _panel_image(
    image: Image.Image,
    panel: FigurePanel,
    width: int,
    height: int,
) -> Image.Image:
    """Return the panel-clipped image with crop, zoom and rotation applied."""
    width = max(1, int(width))
    height = max(1, int(height))
    zoom = max(0.1, float(panel.crop[2]))
    target_width, target_height = _rotated_panel_cover_size(
        width,
        height,
        float(panel.rotation),
    )
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
    return layer.crop((pad, pad, pad + width, pad + height))


def _panel_draw_size(
    image: Image.Image,
    panel_width: float,
    panel_height: float,
    zoom: float,
) -> tuple[int, int]:
    target_width = max(1.0, float(panel_width) * zoom)
    target_height = max(1.0, float(panel_height) * zoom)
    source_aspect = image.width / max(1.0, image.height)
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
) -> np.ndarray:
    has_scale_bars = include_scale_bars and any(
        scale_bar.image_node_id == node_id for scale_bar in project.scale_bars.values()
    )
    has_annotations = any(
        annotation.image_node_id == node_id and annotation.visible
        for annotation in project.annotations.values()
    )
    if not has_scale_bars and not has_annotations:
        return pixels
    image = Image.fromarray(_display_compatible(pixels)).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    if include_scale_bars:
        for scale_bar in project.scale_bars.values():
            if scale_bar.image_node_id == node_id:
                _draw_scale_bar_overlay(draw, image.size, scale_bar)
    for annotation in project.annotations.values():
        if annotation.image_node_id == node_id and annotation.visible:
            _draw_annotation_overlay(draw, image.size, annotation)
    return np.asarray(image.convert("RGB"))


def _draw_panel_scale_bars(
    draw: ImageDraw.ImageDraw,
    project: Project,
    board: FigureBoard,
    panel: FigurePanel,
    image: Image.Image,
    panel_rect: tuple[int, int, int, int],
) -> None:
    if panel.source_node_id is None:
        return
    draw_width, _draw_height = _panel_draw_size(
        image,
        *_rotated_panel_cover_size(panel_rect[2], panel_rect[3], float(panel.rotation)),
        max(0.1, float(panel.crop[2])),
    )
    display_scale = draw_width / max(1.0, float(image.width))
    for scale_bar in project.scale_bars.values():
        if scale_bar.image_node_id != panel.source_node_id:
            continue
        physical_length, pixel_length = adjusted_scale_bar_length(
            board,
            float(scale_bar.physical_length),
            float(scale_bar.pixel_length),
            display_scale,
            panel_rect[2],
        )
        length = max(1.0, pixel_length * display_scale)
        thickness = max(1.0, float(scale_bar.width_px) * display_scale)
        text_height = max(6.0, panel_rect[3] * 0.035)
        padding_x = max(3.0, panel_rect[2] * 0.02)
        padding_y = max(3.0, panel_rect[3] * 0.02)
        x = panel_rect[0] + panel_rect[2] - length - padding_x
        y = panel_rect[1] + panel_rect[3] - thickness - padding_y - (
            text_height if scale_bar.display_length else 0.0
        )
        x = max(panel_rect[0] + padding_x, x)
        y = max(panel_rect[1] + padding_y, y)
        color = _rgba(scale_bar.foreground, scale_bar.opacity)
        line_width = max(1, int(round(thickness)))
        draw.line((x, y, x + length, y), fill=color, width=line_width)
        if scale_bar.display_length:
            font = _font(
                max(1, int(round(text_height * 0.65))),
                bold=scale_bar.bold,
                italic=scale_bar.italic,
                family=scale_bar.font_family,
            )
            text = f"{physical_length:g} {scale_bar.unit}"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_x = x + length / 2.0 - (bbox[2] - bbox[0]) / 2.0
            draw.text((text_x, y + thickness + 1.0), text, fill=color, font=font)


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
    x, y = _scale_bar_origin(scale_bar, float(width), float(height), bar_width, bar_height)
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


def _draw_annotation_overlay(draw: ImageDraw.ImageDraw, image_size: tuple[int, int], annotation: object) -> None:
    width, height = image_size
    points = [(float(x) * width, float(y) * height) for x, y in annotation.points]
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
        _draw_wedge_overlay(draw, points[0], points[1], _rgba(annotation.fill or annotation.color, annotation.opacity), annotation.line_width)
    else:
        draw.line(points, fill=color, width=line_width, joint="curve")
        if annotation.kind is AnnotationKind.ARROW:
            _draw_arrow_overlay(draw, points[-2], points[-1], color, line_width)


def _draw_wedge_overlay(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    line_width: float,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    nx = -dy / length
    ny = dx / length
    half = max(5.0, line_width * 4.0)
    draw.polygon(
        (end, (start[0] + nx * half, start[1] + ny * half), (start[0] - nx * half, start[1] - ny * half)),
        fill=color,
    )


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


def _save_canvas(canvas: Image.Image, path: Path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        tifffile.imwrite(
            path,
            np.asarray(canvas),
            resolution=(float(dpi), float(dpi)),
            resolutionunit="INCH",
        )
        return
    canvas.save(path, dpi=(dpi, dpi))


def _export_caption_sidecars(board: FigureBoard, image_path: Path) -> None:
    caption = board.caption.visible_text().strip()
    if not caption:
        return
    image_path.with_suffix(".caption.txt").write_text(caption + "\n", encoding="utf-8")
    tex_path = image_path.with_suffix(".caption.tex")
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
