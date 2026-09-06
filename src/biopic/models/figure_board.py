"""Figure board models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class PanelLabelMode(StrEnum):
    """Automatic panel label sequences."""

    ALPHABETICAL = "alphabetical"
    ALPHABETICAL_LOWER = "alphabetical_lower"
    NUMERICAL = "numerical"


@dataclass(frozen=True, slots=True)
class PageMargins:
    """Printable page margins in millimetres."""

    left: float = 8.0
    right: float = 8.0
    top: float = 8.0
    bottom: float = 8.0

    def to_dict(self) -> dict[str, float]:
        """Serialize margins."""
        return {
            "left": self.left,
            "right": self.right,
            "top": self.top,
            "bottom": self.bottom,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageMargins:
        """Deserialize margins."""
        return cls(
            left=float(data.get("left", 8.0)),
            right=float(data.get("right", 8.0)),
            top=float(data.get("top", 8.0)),
            bottom=float(data.get("bottom", 8.0)),
        )


@dataclass(slots=True)
class FigureCaption:
    """Auto-generated caption with manual-edit protection."""

    auto_generated: str = ""
    user_text: str = ""
    user_modified: bool = False
    locked: bool = False

    def visible_text(self) -> str:
        """Return the caption text that should be shown/exported."""
        return self.user_text if self.user_modified else self.auto_generated

    def update_auto_generated(self, text: str) -> None:
        """Update untouched auto-generated caption text."""
        self.auto_generated = text
        if not self.user_modified and not self.locked:
            self.user_text = text

    def to_dict(self) -> dict[str, Any]:
        """Serialize caption state."""
        return {
            "auto_generated": self.auto_generated,
            "user_text": self.user_text,
            "user_modified": self.user_modified,
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FigureCaption:
        """Deserialize caption state."""
        return cls(
            auto_generated=str(data.get("auto_generated", "")),
            user_text=str(data.get("user_text", "")),
            user_modified=bool(data.get("user_modified", False)),
            locked=bool(data.get("locked", False)),
        )


@dataclass(frozen=True, slots=True)
class JournalPreset:
    """Publication preset controlling defaults and board styling."""

    name: str
    font_family: str = "Arial"
    label_size_pt: float = 10.0
    label_weight: str = "bold"
    label_offset_mm: tuple[float, float] = (2.0, 2.0)
    margins: PageMargins = field(default_factory=PageMargins)
    horizontal_gutter: float = 4.0
    vertical_gutter: float = 4.0
    caption_style: str = "Figure {number}."

    def to_dict(self) -> dict[str, Any]:
        """Serialize journal preset."""
        return {
            "name": self.name,
            "font_family": self.font_family,
            "label_size_pt": self.label_size_pt,
            "label_weight": self.label_weight,
            "label_offset_mm": list(self.label_offset_mm),
            "margins": self.margins.to_dict(),
            "horizontal_gutter": self.horizontal_gutter,
            "vertical_gutter": self.vertical_gutter,
            "caption_style": self.caption_style,
        }


@dataclass(frozen=True, slots=True)
class LayoutPreset:
    """Reusable normalized panel layout template."""

    name: str
    panels: list[tuple[float, float, float, float]]


@dataclass(slots=True)
class FigurePanel:
    """A panel placement on a publication figure board."""

    source_node_id: str | None = None
    rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    crop: tuple[float, float, float] = (0.5, 0.5, 1.0)
    rotation: float = 0.0
    label: str = "A"
    label_color: str = "#111111"
    label_font_family: str = "Arial"
    label_font_size_pt: float = 10.0
    label_bold: bool = True
    label_italic: bool = False
    label_offset: tuple[float, float] = (0.01, 0.01)
    fill_empty_background: bool = False
    empty_background_path: str | None = None
    empty_background_signature: tuple[Any, ...] | None = None
    visible: bool = True
    locked: bool = False
    annotation_layer_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize a panel."""
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "rect": list(self.rect),
            "crop": list(self.crop),
            "rotation": self.rotation,
            "label": self.label,
            "label_color": self.label_color,
            "label_font_family": self.label_font_family,
            "label_font_size_pt": self.label_font_size_pt,
            "label_bold": self.label_bold,
            "label_italic": self.label_italic,
            "label_offset": list(self.label_offset),
            "fill_empty_background": self.fill_empty_background,
            "empty_background_path": self.empty_background_path,
            "empty_background_signature": (
                list(self.empty_background_signature)
                if self.empty_background_signature is not None
                else None
            ),
            "visible": self.visible,
            "locked": self.locked,
            "annotation_layer_id": self.annotation_layer_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FigurePanel:
        """Deserialize a panel."""
        rect_values = [float(value) for value in data.get("rect", (0, 0, 1, 1))]
        crop_values = [float(value) for value in data.get("crop", (0.5, 0.5, 1))]
        if len(rect_values) != 4:
            raise ValueError("FigurePanel rect must contain four values")
        if len(crop_values) != 3:
            raise ValueError("FigurePanel crop must contain three values")
        label_offset_values = [
            float(value) for value in data.get("label_offset", (0.01, 0.01))
        ]
        if len(label_offset_values) != 2:
            raise ValueError("FigurePanel label_offset must contain two values")
        return cls(
            id=str(data["id"]),
            source_node_id=data.get("source_node_id"),
            rect=(rect_values[0], rect_values[1], rect_values[2], rect_values[3]),
            crop=(crop_values[0], crop_values[1], crop_values[2]),
            rotation=float(data.get("rotation", 0.0)),
            label=str(data.get("label", "A")),
            label_color=str(data.get("label_color", "#111111")),
            label_font_family=str(data.get("label_font_family", "Arial")),
            label_font_size_pt=float(data.get("label_font_size_pt", 10.0)),
            label_bold=bool(data.get("label_bold", True)),
            label_italic=bool(data.get("label_italic", False)),
            label_offset=(label_offset_values[0], label_offset_values[1]),
            fill_empty_background=bool(data.get("fill_empty_background", False)),
            empty_background_path=data.get("empty_background_path"),
            empty_background_signature=_empty_background_signature_from_data(
                data.get("empty_background_signature")
            ),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
            annotation_layer_id=data.get("annotation_layer_id"),
        )


@dataclass(slots=True)
class FigureBoard:
    """Publication figure board with editable panels."""

    name: str
    page: PageFormat
    panels: list[FigurePanel] = field(default_factory=list)
    horizontal_gutter: float = 4.0
    vertical_gutter: float = 4.0
    margin_left: float = 8.0
    margin_right: float = 8.0
    margin_top: float = 8.0
    margin_bottom: float = 8.0
    journal_preset: str | None = None
    label_mode: PanelLabelMode = PanelLabelMode.ALPHABETICAL
    caption: FigureCaption = field(default_factory=FigureCaption)
    metadata_profile: str = "Custom"
    content_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    scale_bar_max_fraction: float = 0.8
    scale_bar_min_fraction: float = 0.2
    scale_bar_use_halving: bool = True
    scale_bar_use_snap_lengths: bool = True
    scale_bar_snap_lengths: list[float] = field(default_factory=list)
    hide_common_scale_bar_value: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def margins(self) -> PageMargins:
        """Return margins as a grouped value object."""
        return PageMargins(
            self.margin_left,
            self.margin_right,
            self.margin_top,
            self.margin_bottom,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the board."""
        return {
            "id": self.id,
            "name": self.name,
            "page": self.page.to_dict(),
            "panels": [panel.to_dict() for panel in self.panels],
            "horizontal_gutter": self.horizontal_gutter,
            "vertical_gutter": self.vertical_gutter,
            "margin_left": self.margin_left,
            "margin_right": self.margin_right,
            "margin_top": self.margin_top,
            "margin_bottom": self.margin_bottom,
            "journal_preset": self.journal_preset,
            "label_mode": self.label_mode.value,
            "caption": self.caption.to_dict(),
            "metadata_profile": self.metadata_profile,
            "content_rect": list(self.content_rect),
            "scale_bar_max_fraction": self.scale_bar_max_fraction,
            "scale_bar_min_fraction": self.scale_bar_min_fraction,
            "scale_bar_use_halving": self.scale_bar_use_halving,
            "scale_bar_use_snap_lengths": self.scale_bar_use_snap_lengths,
            "scale_bar_snap_lengths": list(self.scale_bar_snap_lengths),
            "hide_common_scale_bar_value": self.hide_common_scale_bar_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FigureBoard:
        """Deserialize the board."""
        content_rect_values = [
            float(value) for value in data.get("content_rect", (0, 0, 1, 1))
        ]
        if len(content_rect_values) != 4:
            content_rect_values = [0.0, 0.0, 1.0, 1.0]
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            page=PageFormat.from_dict(data["page"]),
            panels=[FigurePanel.from_dict(item) for item in data.get("panels", [])],
            horizontal_gutter=float(data.get("horizontal_gutter", 4.0)),
            vertical_gutter=float(data.get("vertical_gutter", 4.0)),
            margin_left=float(data.get("margin_left", 8.0)),
            margin_right=float(data.get("margin_right", 8.0)),
            margin_top=float(data.get("margin_top", 8.0)),
            margin_bottom=float(data.get("margin_bottom", 8.0)),
            journal_preset=data.get("journal_preset"),
            label_mode=PanelLabelMode(
                data.get("label_mode", PanelLabelMode.ALPHABETICAL.value)
            ),
            caption=FigureCaption.from_dict(data.get("caption", {})),
            metadata_profile=str(data.get("metadata_profile", "Custom")),
            content_rect=(
                content_rect_values[0],
                content_rect_values[1],
                content_rect_values[2],
                content_rect_values[3],
            ),
            scale_bar_max_fraction=max(
                0.1,
                min(1.0, float(data.get("scale_bar_max_fraction", 0.8))),
            ),
            scale_bar_min_fraction=max(
                0.1,
                min(1.0, float(data.get("scale_bar_min_fraction", 0.2))),
            ),
            scale_bar_use_halving=bool(data.get("scale_bar_use_halving", True)),
            scale_bar_use_snap_lengths=bool(data.get("scale_bar_use_snap_lengths", True)),
            scale_bar_snap_lengths=_positive_float_list(
                data.get("scale_bar_snap_lengths", [])
            ),
            hide_common_scale_bar_value=bool(
                data.get("hide_common_scale_bar_value", False)
            ),
        )


def _positive_float_list(values: object) -> list[float]:
    result: list[float] = []
    if not isinstance(values, list):
        return result
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.append(number)
    return result


def common_scale_bar_value_key(scale_bars: list[object]) -> tuple[float, str] | None:
    """Return the repeated scale-bar value whose label should be hidden."""
    counts: dict[tuple[float, str], int] = {}
    for scale_bar in scale_bars:
        if not getattr(scale_bar, "display_length", True):
            continue
        key = (
            round(float(getattr(scale_bar, "physical_length", 0.0)), 9),
            str(getattr(scale_bar, "unit", "")),
        )
        counts[key] = counts.get(key, 0) + 1
    repeated = [(count, key) for key, count in counts.items() if count > 1]
    if not repeated:
        return None
    repeated.sort(key=lambda item: (-item[0], item[1]))
    return repeated[0][1]


def _empty_background_signature_from_data(value: object) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    result: list[Any] = []
    for index, item in enumerate(value):
        if index == 1 and isinstance(item, (list, tuple)):
            result.append(tuple(item))
        else:
            result.append(item)
    return tuple(result)


def visual_panel_order(panels: list[FigurePanel]) -> list[FigurePanel]:
    """Return panels in natural reading order by geometry."""
    return sorted(
        panels,
        key=lambda panel: (
            round(panel.rect[1], 6),
            round(panel.rect[0], 6),
            round(panel.rect[3], 6),
            round(panel.rect[2], 6),
        ),
    )


def panel_empty_background_signature(
    panel: FigurePanel,
    width: int,
    height: int,
) -> tuple[Any, ...]:
    """Return the panel state covered by a baked empty-background fill."""
    return (
        panel.source_node_id,
        tuple(round(float(value), 6) for value in panel.crop),
        round(float(panel.rotation), 6),
        int(width),
        int(height),
    )


def relabel_panels(board: FigureBoard) -> None:
    """Assign automatic labels by visual reading order."""
    ordered = visual_panel_order(board.panels)
    for index, panel in enumerate(ordered):
        panel.label = label_for_index(index, board.label_mode)


def adjusted_scale_bar_length(
    board: FigureBoard,
    physical_length: float,
    pixel_length: float,
    display_scale: float,
    panel_length_px: float,
) -> tuple[float, float]:
    """Return physical/pixel scale-bar length constrained by board settings."""
    physical = float(physical_length)
    pixels = float(pixel_length)
    if physical <= 0 or pixels <= 0 or display_scale <= 0 or panel_length_px <= 0:
        return physical, pixels
    min_fraction = min(board.scale_bar_min_fraction, board.scale_bar_max_fraction)
    max_fraction = max(board.scale_bar_min_fraction, board.scale_bar_max_fraction)
    min_length_px = max(1.0, float(panel_length_px) * min_fraction)
    max_length_px = max(min_length_px, float(panel_length_px) * max_fraction)
    displayed = pixels * display_scale
    if min_length_px <= displayed <= max_length_px:
        return physical, pixels
    candidates: set[float] = {physical}
    if board.scale_bar_use_snap_lengths:
        candidates.update(value for value in board.scale_bar_snap_lengths if value > 0)
    if board.scale_bar_use_halving:
        value = physical
        for _ in range(24):
            value /= 2.0
            if value <= 0:
                break
            candidates.add(value)
        value = physical
        for _ in range(24):
            value *= 2.0
            candidates.add(value)
            if pixels * display_scale * (value / physical) > max_length_px * 4.0:
                break
    scaled_candidates = [
        (candidate, pixels * (candidate / physical))
        for candidate in candidates
        if candidate > 0
    ]
    in_range = [
        (candidate, candidate_pixels)
        for candidate, candidate_pixels in scaled_candidates
        if min_length_px <= candidate_pixels * display_scale <= max_length_px
    ]
    if in_range:
        if displayed < min_length_px:
            return min(
                in_range,
                key=lambda item: (item[1] * display_scale, abs(item[0] - physical)),
            )
        return max(
            in_range,
            key=lambda item: (item[1] * display_scale, -abs(item[0] - physical)),
        )
    target = min_length_px if displayed < min_length_px else max_length_px
    return min(
        scaled_candidates,
        key=lambda item: abs(item[1] * display_scale - target),
    )


def grid_panels(count: int, columns: int | None = None) -> list[FigurePanel]:
    """Generate equal normalized panel placeholders."""
    if count <= 0:
        raise ValueError("count must be greater than zero")
    if columns is None:
        columns = int(count**0.5)
        if columns * columns < count:
            columns += 1
    rows = (count + columns - 1) // columns
    panels: list[FigurePanel] = []
    for index in range(count):
        row, column = divmod(index, columns)
        panels.append(
            FigurePanel(
                rect=(column / columns, row / rows, 1.0 / columns, 1.0 / rows),
                label=chr(ord("A") + index),
            )
        )
    return panels


def label_for_index(index: int, mode: PanelLabelMode) -> str:
    """Return automatic panel label for an index."""
    if mode is PanelLabelMode.NUMERICAL:
        return str(index + 1)
    value = index
    label = ""
    while True:
        value, remainder = divmod(value, 26)
        label = chr(ord("A") + remainder) + label
        if value == 0:
            return label.lower() if mode is PanelLabelMode.ALPHABETICAL_LOWER else label
        value -= 1


def generate_layout_presets(count: int) -> list[LayoutPreset]:
    """Generate publication-oriented layout presets for one to eight panels."""
    if count < 1 or count > 8:
        raise ValueError("figure-board layout presets support 1 to 8 panels")
    presets = [LayoutPreset("Grid", [panel.rect for panel in grid_panels(count)])]
    if count == 1:
        return presets
    presets.extend(_strip_layouts(count))
    if count >= 3:
        presets.append(_large_first_layout(count, "Large left", "left"))
        presets.append(_large_first_layout(count, "Large top", "top"))
    if count >= 4:
        presets.append(_large_first_layout(count, "Large right", "right"))
        presets.append(_large_first_layout(count, "Large bottom", "bottom"))
    if count == 5:
        presets.extend(_five_panel_split_layouts())
    return presets


def panels_from_layout(
    preset: LayoutPreset, label_mode: PanelLabelMode = PanelLabelMode.ALPHABETICAL
) -> list[FigurePanel]:
    """Create empty figure panels from a layout preset."""
    return [
        FigurePanel(rect=rect, label=label_for_index(index, label_mode))
        for index, rect in enumerate(preset.panels)
    ]


def page_format_presets() -> dict[str, PageFormat]:
    """Return supported publication page sizes."""
    return {
        "DIN A4 Portrait": PageFormat("DIN A4 Portrait", 210, 297, PageUnit.MM, 300),
        "DIN A4 Landscape": PageFormat("DIN A4 Landscape", 297, 210, PageUnit.MM, 300),
        "DIN A3 Portrait": PageFormat("DIN A3 Portrait", 297, 420, PageUnit.MM, 300),
        "DIN A3 Landscape": PageFormat("DIN A3 Landscape", 420, 297, PageUnit.MM, 300),
        "Letter Portrait": PageFormat("Letter Portrait", 8.5, 11, PageUnit.INCH, 300),
        "Letter Landscape": PageFormat("Letter Landscape", 11, 8.5, PageUnit.INCH, 300),
        "Poster A2": PageFormat("Poster A2", 420, 594, PageUnit.MM, 300),
        "Poster A1": PageFormat("Poster A1", 594, 841, PageUnit.MM, 300),
        "Poster A0": PageFormat("Poster A0", 841, 1189, PageUnit.MM, 300),
    }


def journal_presets() -> dict[str, JournalPreset]:
    """Return built-in publication journal presets."""
    return {
        "Generic Biology": JournalPreset("Generic Biology"),
        "Nature": JournalPreset(
            "Nature", font_family="Arial", label_size_pt=8.0, margins=PageMargins(5, 5, 5, 5)
        ),
        "Springer Nature": JournalPreset("Springer Nature", font_family="Arial"),
        "Elsevier": JournalPreset("Elsevier", font_family="Arial"),
        "PLOS": JournalPreset("PLOS", font_family="Arial", margins=PageMargins(6, 6, 6, 6)),
        "Cell Press": JournalPreset("Cell Press", font_family="Helvetica"),
        "BMC": JournalPreset("BMC", font_family="Arial"),
        "IEEE": JournalPreset(
            "IEEE", font_family="Times New Roman", label_size_pt=8.0
        ),
    }


def _strip_layouts(count: int) -> list[LayoutPreset]:
    horizontal = [(index / count, 0.0, 1.0 / count, 1.0) for index in range(count)]
    vertical = [(0.0, index / count, 1.0, 1.0 / count) for index in range(count)]
    return [LayoutPreset("Horizontal strip", horizontal), LayoutPreset("Vertical strip", vertical)]


def _large_first_layout(count: int, name: str, side: str) -> LayoutPreset:
    remainder = count - 1
    panels: list[tuple[float, float, float, float]] = []
    if side == "left":
        panels.append((0.0, 0.0, 0.58, 1.0))
        panels.extend(_stack_rects(remainder, 0.58, 0.0, 0.42, 1.0))
    elif side == "right":
        panels.extend(_stack_rects(remainder, 0.0, 0.0, 0.42, 1.0))
        panels.append((0.42, 0.0, 0.58, 1.0))
    elif side == "top":
        panels.append((0.0, 0.0, 1.0, 0.58))
        panels.extend(_row_rects(remainder, 0.0, 0.58, 1.0, 0.42))
    else:
        panels.extend(_row_rects(remainder, 0.0, 0.0, 1.0, 0.42))
        panels.append((0.0, 0.42, 1.0, 0.58))
    return LayoutPreset(name, panels)


def _five_panel_split_layouts() -> list[LayoutPreset]:
    """Return balanced two-by-three split layouts for five panels."""
    return [
        LayoutPreset(
            "Two top, three bottom",
            [
                (0.0, 0.0, 0.5, 0.5),
                (0.5, 0.0, 0.5, 0.5),
                (0.0, 0.5, 1.0 / 3.0, 0.5),
                (1.0 / 3.0, 0.5, 1.0 / 3.0, 0.5),
                (2.0 / 3.0, 0.5, 1.0 / 3.0, 0.5),
            ],
        ),
        LayoutPreset(
            "Three top, two bottom",
            [
                (0.0, 0.0, 1.0 / 3.0, 0.5),
                (1.0 / 3.0, 0.0, 1.0 / 3.0, 0.5),
                (2.0 / 3.0, 0.0, 1.0 / 3.0, 0.5),
                (0.0, 0.5, 0.5, 0.5),
                (0.5, 0.5, 0.5, 0.5),
            ],
        ),
        LayoutPreset(
            "Two left, three right",
            [
                (0.0, 0.0, 0.5, 0.5),
                (0.0, 0.5, 0.5, 0.5),
                (0.5, 0.0, 0.5, 1.0 / 3.0),
                (0.5, 1.0 / 3.0, 0.5, 1.0 / 3.0),
                (0.5, 2.0 / 3.0, 0.5, 1.0 / 3.0),
            ],
        ),
        LayoutPreset(
            "Three left, two right",
            [
                (0.0, 0.0, 0.5, 1.0 / 3.0),
                (0.0, 1.0 / 3.0, 0.5, 1.0 / 3.0),
                (0.0, 2.0 / 3.0, 0.5, 1.0 / 3.0),
                (0.5, 0.0, 0.5, 0.5),
                (0.5, 0.5, 0.5, 0.5),
            ],
        ),
    ]


def _stack_rects(
    count: int, x: float, y: float, width: float, height: float
) -> list[tuple[float, float, float, float]]:
    return [(x, y + index * height / count, width, height / count) for index in range(count)]


def _row_rects(
    count: int, x: float, y: float, width: float, height: float
) -> list[tuple[float, float, float, float]]:
    return [(x + index * width / count, y, width / count, height) for index in range(count)]


def move_vertical_divider(
    left: FigurePanel, right: FigurePanel, delta: float, *, minimum: float = 0.05
) -> tuple[FigurePanel, FigurePanel]:
    """Move a shared vertical divider between adjacent panels."""
    lx, ly, lw, lh = left.rect
    rx, ry, rw, rh = right.rect
    new_lw = max(minimum, lw + delta)
    new_rw = max(minimum, rw - delta)
    return (
        FigurePanel(
            id=left.id,
            source_node_id=left.source_node_id,
            rect=(lx, ly, new_lw, lh),
            crop=left.crop,
            rotation=left.rotation,
            label=left.label,
            label_color=left.label_color,
            label_font_family=left.label_font_family,
            label_font_size_pt=left.label_font_size_pt,
            label_bold=left.label_bold,
            label_italic=left.label_italic,
            label_offset=left.label_offset,
            visible=left.visible,
            locked=left.locked,
            annotation_layer_id=left.annotation_layer_id,
        ),
        FigurePanel(
            id=right.id,
            source_node_id=right.source_node_id,
            rect=(rx + (rw - new_rw), ry, new_rw, rh),
            crop=right.crop,
            rotation=right.rotation,
            label=right.label,
            label_color=right.label_color,
            label_font_family=right.label_font_family,
            label_font_size_pt=right.label_font_size_pt,
            label_bold=right.label_bold,
            label_italic=right.label_italic,
            label_offset=right.label_offset,
            visible=right.visible,
            locked=right.locked,
            annotation_layer_id=right.annotation_layer_id,
        ),
    )
class PageUnit(StrEnum):
    """Supported page units."""

    MM = "mm"
    CM = "cm"
    INCH = "inch"
    POINT = "point"
    PIXEL = "pixel"


@dataclass(frozen=True, slots=True)
class PageFormat:
    """Physical or pixel output page format."""

    name: str
    width: float
    height: float
    unit: PageUnit = PageUnit.MM
    dpi: int = 300

    def pixel_dimensions(self) -> tuple[int, int]:
        """Return output dimensions in pixels."""
        if self.unit is PageUnit.PIXEL:
            return int(round(self.width)), int(round(self.height))
        inches_per_unit = {
            PageUnit.MM: 1.0 / 25.4,
            PageUnit.CM: 1.0 / 2.54,
            PageUnit.INCH: 1.0,
            PageUnit.POINT: 1.0 / 72.0,
        }[self.unit]
        return (
            int(round(self.width * inches_per_unit * self.dpi)),
            int(round(self.height * inches_per_unit * self.dpi)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the page format."""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "unit": self.unit.value,
            "dpi": self.dpi,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageFormat:
        """Deserialize the page format."""
        return cls(
            name=str(data["name"]),
            width=float(data["width"]),
            height=float(data["height"]),
            unit=PageUnit(data.get("unit", PageUnit.MM.value)),
            dpi=int(data.get("dpi", 300)),
        )
