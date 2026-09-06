# Architecture

## 1. Reference Behavior

BioPic LM preserves the important user-visible stacking and alignment behavior
from the reference workflow:

- named modes: `Stacking`, `Colour stacking`, `Alignment`, `Dividing`;
- progress captions: `PROGRAM: Stacking in progress...`,
  `PROGRAM: Alignment in progress...`, `Alignment done.`;
- result naming: `stk#`, `map#`, `depthmap_grey.bmp`, timestamp naming, and
  optional export of stacking steps;
- outputs: stacked image, depth map, and an overlay named
  `Overlay: Stacked image + depth map`;
- alignment controls: auto-align positions, optional resize during alignment,
  and optional rotation correction;
- stack controls: skip cadence options (`Off`, `1`, `2`, `4`, `9`) and image
  inclusion indicated by checked/unchecked list entries;
- background/output variants suggested by suffixes such as `_bgdark`,
  `_bgbrit`, `_bgmix`, `_bglast`, `_bgcol`, `_fil`, `_sup`, and `_skip`.

BioPic LM uses those items only as behavioral reference: the user gets explicit
alignment, skip/exclude, preview/result/depth-map outputs, progress state, result
naming, and optional step export. The implementation is original
Python/NumPy/SciPy code with documented parameters and tests.

## 2. Recommended Stack

Python 3.12 with PySide6/Qt 6 is the baseline. It gives native Windows/Linux
desktop behavior, high-DPI support, menus, dock panels, model/view widgets, and
worker threads while staying lighter than Electron. NumPy/SciPy/OpenCV or
scikit-image will handle image registration, filtering, pyramids, and blending.
tifffile/Pillow/imageio preserve scientific image formats and metadata. JSON
project manifests plus cache files give reproducibility and readable diffs.

## 3. Directory Structure

```text
src/biopic/
  app/
  ui/
  models/
  pipeline/
  imaging/
    stacking/
    corrections/
    filters/
    measurement/
    annotations/
    figure_board/
  commands/
  persistence/
  export/
  presets/
  workers/
  utilities/
tests/
resources/
docs/
```

## 4. Data Model

- `Project`: schema version, stable id, name, source assets, processing graph,
  calibration presets, annotations, figure boards, export settings, history.
- `ImageAsset`: stable id, original path, optional embedded package path,
  checksum, dimensions, dtype, color model, metadata.
- `ProcessingNode`: stable id, operation type, upstream node ids, parameters,
  status, version, cache key, provenance record.
- `Calibration`: unit-per-pixel, pixel aspect ratio, unit, source, preset link.
- `Annotation`: vector geometry, normalized coordinates, style, definition id.
- `FigurePanel`: source node id, normalized panel rectangle, crop transform,
  label style, linked scale-bar objects, visibility/lock state.

## 5. Dependency Graph

Processing nodes form a DAG. Updating a node increments its version and marks
dependent descendants stale. Recompute walks only stale descendants whose inputs
changed. Stable ids and normalized coordinates preserve downstream annotations,
masks, scale bars, and panel crops where dimensions remain compatible.

## 6. UI Layout

The persistent frame has a full-width toolbar, main menu, workspace navigation,
left project/status panel, central workspace stack, and bottom status area.
Workspaces are Import, Stack, Edit, Measure and Scale, Annotate, Figure Board,
and Export. The Stack workspace will use a reorderable thumbnail strip across
the top, source image pane lower-left, result pane lower-right, and a side
parameter/status panel.

## 7. Focus-Stacking Design

Milestone 3 will implement optional registration, focus metrics (Laplacian,
modified Laplacian, Tenengrad, variance), regularized focus-map generation,
multi-resolution blending, halo suppression, ghosting reduction, manual masks,
preview/full-resolution modes, depth-map output, and parameter presets. Pixel
hard-max compositing is avoided except as an internal diagnostic.

## 8. Persistence

Project files are versioned JSON manifests (`.biopic.json`) written atomically.
Large generated arrays and previews live in a content-addressed cache folder.
Portable packages will embed assets and cache entries. Schema migration is a
first-class module.

## 9. Export

Raster exports use tifffile/Pillow/imageio with explicit bit depth, metadata,
resolution, and lossy-format warnings. Figure export will rasterize microscopy
panels at target DPI while preserving labels, arrows, shapes, and scale bars as
vectors in PDF/SVG where technically reliable. A preflight report runs first.

## 10. Testing

Model, graph, persistence, calibration, and numerical operations use deterministic
pytest tests with synthetic images. GUI behavior is tested at model/controller
boundaries first, then with lightweight Qt smoke tests when available.

## 11. Risks

- Large 16-bit and multi-page images require tiled rendering and bounded caches.
- Focus stacking must avoid halos and biologically misleading artifacts.
- Cross-platform packaging with Qt and scientific wheels needs repeatable CI.
- Project schema migrations must preserve reproducibility.
- Vector export must not accidentally flatten scientific annotations too early.

## 12. Milestones

1. Architecture and runnable shell.
2. Image import and canvas.
3. Focus stacking.
4. Image editing.
5. Measurement and scale bars.
6. Annotations.
7. Figure Board.
8. Export and packaging.
