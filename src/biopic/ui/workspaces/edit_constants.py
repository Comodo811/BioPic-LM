"""Static tool tables for the edit workspace."""

GIMP_TOOL_HELP = {
    "move": "Move the active unlocked layer",
    "rectangle_select": "Create a selection rectangle that constrains painting and fills",
    "ellipse_select": "Create an elliptical selection that constrains painting and fills",
    "crop": "Crop using an interactive rectangle",
    "bucket_fill": "Fill image or active selection",
    "brush": "Paint on the active editable raster layer",
    "pencil": "Paint hard-edged pixels on the active editable raster layer",
    "erase": "Erase alpha on the active editable raster layer",
    "color_picker": "Sample the rendered composite",
    "zoom": "Zoom the canvas",
    "pan": "Pan the canvas",
    "free_select": "Create a polygonal lasso selection; click points and close on the start point",
    "fuzzy_select": "Select a contiguous region with similar color",
    "scale": "Scale the rendered image uniformly using Size as percent",
    "rotate": "Rotate the rendered image freely by dragging around the image",
    "paths": "Pen/path tool for path-like selections",
    "pen": "Pen/path tool for path-like selections",
    "clone": "Ctrl-click to sample, then paint copied pixels on the active layer",
    "heal": "Ctrl-click to sample, then heal source texture into destination lighting",
}

GIMP_TOOLBOX_TOOLS = [
    ("pan", "H"),
    ("zoom", "Z"),
    ("move", "M"),
    ("rectangle_select", "R"),
    ("ellipse_select", "E"),
    ("free_select", "F"),
    ("fuzzy_select", "W"),
    ("crop", "C"),
    ("rotate", "Shift+R"),
    ("brush", "B"),
    ("pencil", "N"),
    ("erase", "Shift+E"),
    ("clone", "C"),
    ("heal", "H"),
    ("bucket_fill", "Shift+B"),
    ("color_picker", "O"),
]

TRANSFORM_TOOL_OPERATIONS = {
    "rotate": "rotate_90",
    "scale": "scale_uniform",
    "flip": "flip_horizontal",
}
