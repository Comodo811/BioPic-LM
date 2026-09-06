"""Shared tool-mode classification for editor UI controllers."""

from __future__ import annotations

POINT_TOOL_MODES = frozenset(
    {
        "brush",
        "erase",
        "clone",
        "heal",
        "text",
        "measure",
        "color_picker",
        "bucket_fill",
        "dodge_burn",
        "smudge",
        "pencil",
        "scale",
        "fuzzy_select",
    }
)

PAINT_TOOL_MODES = frozenset(
    {
        "brush",
        "erase",
        "clone",
        "heal",
        "bucket_fill",
        "dodge_burn",
        "smudge",
        "pencil",
    }
)

RECTANGLE_TOOL_MODES = frozenset({"select", "ellipse_select", "crop"})
SELECTION_TOOL_MODES = frozenset(
    {"rectangle_select", "ellipse_select", "free_select", "fuzzy_select"}
)


def is_point_tool(mode: str) -> bool:
    return mode in POINT_TOOL_MODES


def is_paint_tool(mode: str) -> bool:
    return mode in PAINT_TOOL_MODES


def is_rectangle_tool(mode: str) -> bool:
    return mode in RECTANGLE_TOOL_MODES


def is_selection_tool(mode: str) -> bool:
    return mode in SELECTION_TOOL_MODES
