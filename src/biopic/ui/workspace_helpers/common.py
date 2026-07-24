"""General workspace formatting and lightweight UI helpers."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLayout

from biopic import __version__ as BIOPIC_VERSION
from biopic.imaging.stacking import FocusStackResult
from biopic.models.figure_board import LayoutPreset, PageUnit
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack
from biopic.pipeline.node import ProcessingNode
from biopic.ui.previews import asset_thumbnail


def asset_metadata_text(asset: ImageAsset) -> str:
    lines = [
        f"File: {asset.path}",
        f"Dimensions: {asset.width} x {asset.height}",
        f"Frames: {asset.frames}",
        f"Data type: {asset.dtype}",
        f"Color model: {asset.color_model}",
        f"Checksum: {asset.checksum}",
        "",
        "Metadata:",
    ]
    for key, value in sorted(asset.metadata.items()):
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def editable_asset_label(asset: ImageAsset) -> str:
    badges = {
        ImageAssetKind.DIRECT_IMPORT: "Direct import",
        ImageAssetKind.STACK_RESULT: "Stacked result",
        ImageAssetKind.EDIT_DERIVATIVE: "Edited",
        ImageAssetKind.EXTERNAL_LINK: "Linked",
        ImageAssetKind.STACK_SOURCE: "Stack source",
    }
    return f"{asset.filename}\n{badges[asset.kind]}"


def stack_display_name(stack: ImageStack, assets_by_id: dict[str, ImageAsset]) -> str:
    """Return a compact user-facing stack label."""
    assets = [assets_by_id[asset_id] for asset_id in stack.asset_ids if asset_id in assets_by_id]
    if not assets:
        return f"{stack.name} (0 frames)"
    first = assets[0].filename
    last = assets[-1].filename
    if len(assets) == 1:
        return f"{first} (1 frame)"
    return f"{first} - {last} ({len(assets)} frames)"


def project_asset_display_name(asset: ImageAsset, stacks: dict[str, ImageStack]) -> str:
    """Return an asset label without exposing internal ids."""
    source_stack_id = asset.metadata.get("source_stack_id")
    if isinstance(source_stack_id, str) and source_stack_id in stacks:
        return f"{stacks[source_stack_id].name} stacked result"
    return asset.filename


def layout_ascii_preview(preset: LayoutPreset) -> str:
    """Return a compact text preview for a normalized layout preset."""
    width = 16
    height = 8
    cells = [[" " for _column in range(width)] for _row in range(height)]
    for rect in preset.panels:
        x, y, panel_width, panel_height = rect
        left = max(0, min(width - 1, int(round(x * width))))
        top = max(0, min(height - 1, int(round(y * height))))
        right = max(left + 1, min(width, int(round((x + panel_width) * width))))
        bottom = max(top + 1, min(height, int(round((y + panel_height) * height))))
        for column in range(left, right):
            cells[top][column] = "-"
            cells[bottom - 1][column] = "-"
        for row in range(top, bottom):
            cells[row][left] = "|"
            cells[row][right - 1] = "|"
    return "\n".join("".join(row).rstrip() for row in cells)


def page_dimension_mm(value: float, unit: PageUnit) -> float:
    if unit is PageUnit.MM:
        return value
    if unit is PageUnit.CM:
        return value * 10.0
    if unit is PageUnit.INCH:
        return value * 25.4
    if unit is PageUnit.POINT:
        return value * 25.4 / 72.0
    return value * 25.4 / 300.0


def scale_preset_table_headers() -> list[str]:
    return [
        "Magnification",
        "Fluid",
        "Distance in Pixels",
        "Known Distance",
        "Unit",
        "Pixel per Unit",
        "Objective (optional)",
    ]


def biological_display_name(
    scientific_name: object,
    taxonomy: object,
    fallback: str,
) -> str:
    name = str(scientific_name or "").strip()
    taxon = str(taxonomy or "").strip()
    lower = name.lower().strip()
    unresolved = {"", "sp", "sp.", "species", "unknown", "unidentified"}
    if lower in unresolved:
        return f"{_title_taxon(taxon)} sp." if taxon else fallback
    tokens = name.split()
    if len(tokens) == 1 and tokens[0].lower() in {"cf.", "cf", "aff.", "aff", "sp.", "sp"}:
        return f"{_title_taxon(taxon)} sp." if taxon else fallback
    if tokens and tokens[-1].lower().rstrip(".") == "sp":
        genus = tokens[0] if tokens[0].lower().rstrip(".") not in {"cf", "aff"} else taxon
        return f"{_title_taxon(genus)} sp." if genus else fallback
    if len(tokens) >= 2 and tokens[1].lower().rstrip(".") in {"cf", "aff"}:
        return " ".join(tokens)
    return name


def point_distance(first: QPointF, second: QPointF) -> float:
    dx = first.x() - second.x()
    dy = first.y() - second.y()
    return (dx * dx + dy * dy) ** 0.5


def stack_result_metadata(
    stack: ImageStack, node: ProcessingNode, result: FocusStackResult
) -> dict[str, object]:
    return {
        "biopic_version": BIOPIC_VERSION,
        "stack_metadata_schema_version": 1,
        "source_stack_id": stack.id,
        "source_asset_ids": list(stack.asset_ids),
        "enabled_asset_ids": list(stack.enabled_asset_ids or []),
        "focus_stack_node_id": node.id,
        "stacking_parameters": result.parameters.to_dict(),
        "transform_count": len(result.transforms),
        "depth_map_recorded": result.depth_map.size > 0,
    }


def stack_thumbnail(assets: list[ImageAsset], size: QSize) -> QPixmap:
    canvas = QPixmap(size)
    canvas.fill(QColor("#f4f4f4"))
    if not assets:
        return canvas
    chosen = _representative_stack_assets(assets)
    frame_size = QSize(max(1, size.width() - 26), max(1, size.height() - 22))
    offsets = [(16, 2), (8, 10), (22, 20)]
    painter = QPainter(canvas)
    painter.setPen(QPen(QColor("#555555"), 1))
    for asset, (x, y) in zip(chosen, offsets, strict=False):
        frame = asset_thumbnail(asset, frame_size)
        painter.drawPixmap(x, y, frame)
        painter.drawRect(QRect(x, y, frame_size.width() - 1, frame_size.height() - 1))
    painter.end()
    return canvas


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def coerce_polygon_points(value: object) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if not isinstance(value, list):
        return points
    for item in value:
        try:
            x, y = item
            points.append((float(x), float(y)))
        except (TypeError, ValueError):
            continue
    return points


def coverage_bounds(mask: np.ndarray | None) -> tuple[int, int, int, int] | None:
    if mask is None:
        return None
    active = np.asarray(mask) > 0.0
    if not np.any(active):
        return None
    ys, xs = np.nonzero(active)
    x0 = int(xs.min())
    y0 = int(ys.min())
    x1 = int(xs.max()) + 1
    y1 = int(ys.max()) + 1
    return (x0, y0, x1 - x0, y1 - y0)


def _representative_stack_assets(assets: list[ImageAsset]) -> list[ImageAsset]:
    if len(assets) <= 3:
        return assets
    middle = len(assets) // 2
    return [assets[-1], assets[middle], assets[0]]


def _title_taxon(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    first = text.split(";")[-1].strip().split(",")[-1].strip().split()[-1]
    return first[:1].upper() + first[1:]
