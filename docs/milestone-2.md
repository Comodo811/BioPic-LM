# Milestone 2: Image Import and Canvas

Implemented:

- PNG, JPEG, BMP, TIFF, and multi-page TIFF metadata import.
- Source-image checksums for provenance.
- Preservation of dimensions, frame count, dtype, color model, and readable metadata.
- Independent image import and ordered focal-stack import.
- Project persistence of imported assets and image stacks.
- Zoomable image canvas with fit, 100% view, pan, coordinate display, and pixel-value inspection.
- Import workspace with source list, canvas, and metadata inspector.
- Stack workspace with horizontal thumbnail strip and source/result panes.
- File menu actions for New, Open, Save, Save As, Import Image, and Import Image Stack.

Known limitations:

- Thumbnails currently use placeholder icons; real downsampled thumbnails will be cached when the tiled preview cache lands.
- Stack import defaults to focal stacks from the file dialog; a richer independent/focal/time chooser is planned.
- The result pane exists for Milestone 3 stacking output but does not compute a stacked result yet.
- Drag-and-drop loading is still pending.

Verification:

- `python -m compileall src tests` passed before cleanup.
- Manual synthetic image import tests passed with PNG, BMP, 16-bit TIFF stack, stack order, and project save/load.
- `pytest`, `ruff`, and `mypy` are not installed for the active Python interpreter in this environment.
