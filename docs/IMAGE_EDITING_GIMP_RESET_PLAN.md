# Image Editing GIMP Reset Plan

SPDX-License-Identifier: GPL-3.0-or-later

BioPic LM's image editing module is being reset around the same responsibilities
GIMP separates internally. The goal is not to embed the whole GTK/GEGL
application, but to study the relevant architecture for BioPic LM's Qt/native
runtime.

## Upstream Reference Files

- `app/tools/gimppainttool-paint.c`
  - Paint thread/queue.
  - Paint timeout.
  - Drawable flush.
  - Projection and display flush.

- `app/paint/gimppaintcore.c`
  - Paint lifecycle.
  - Current/last coordinates.
  - Stroke smoothing and interpolation entry points.
  - Finish/cancel behavior.

- `app/paint/gimpbrushcore.c`
  - Brush spacing.
  - Dab generation.
  - Exact-integer coordinate avoidance.
  - Brush footprint/bounds.

- `app/core/gimpdrawable.c`
  - Drawable paint mode.
  - Dirty region tracking.
  - Buffer update/invalidation.

- `app/core/gimplayer.c`
  - Layer properties over drawable pixels.
  - Opacity, mode, masks, locks, offsets.

- `app/core/gimpprojection.c`
  - Projection graph.
  - Dirty-region invalidation and flush.

- `app/display/gimpdisplayshell-render.c`
  - Display cache/render path.
  - Area updates rather than full repaint where possible.

## BioPic LM Target Architecture

```text
PySide tool UI
    -> PaintToolController
    -> GimpPaintCore-style stroke state
    -> Native brush/dab generator
    -> TileDrawable paint mode
    -> Native tile paint kernels
    -> Projection graph dirty regions
    -> Native display tile conversion
    -> QGraphicsView display shell
```

## Required Replacement Work

1. Move all stroke state out of `EditWorkspace`.
2. Keep one paint path for brush/eraser/pencil; delete competing smoothers.
3. Paint drawables through tile sessions only.
4. Apply content and alpha in one native traversal.
5. Flush only dirty drawables/projection/display regions.
6. Move layer transforms through metadata and projection nodes, not pixel copies.
7. Keep masks as independent grayscale drawables.
8. Implement tool options as data objects, not ad hoc widget state reads.
9. Implement filter layers as graph nodes with dirty-region invalidation.
10. Replace UI-thread painting with a worker paint queue after the single-threaded
    core is structurally clean.

## Current Native Image-Editing Components

- `src/biopic/imaging/core/`
  - GIMP-inspired core document layer below UI tools and display.
  - `CoreImage` mirrors the central image container.
  - `CoreItem` stores identity, visibility, offsets and generation.
  - `CoreDrawable` stores content/alpha/mask state and dirty regions.
  - `CoreLayer` and `CoreGroupLayer` model compositing nodes and nested groups.
  - `CoreSelection` and `CoreChannel` provide independent mask/channel state.
  - `CoreProjection` stores validated alpha-carrying projection state and
    invalidated regions.
  - `CoreUndoManager` groups metadata/tile changes into undo transactions.

- `src/biopic/imaging/engine/`
  - Stable document/projection boundary between UI tools and image output.
  - GEGL/Babl/PyGObject runtime detection.
  - GEGL ctypes bridge for real `GeglBuffer` creation, full reads, dirty-region
    reads and dirty-region writes.
  - GEGL graph execution through `gegl:buffer-source`, `gegl:over` and
    `gegl_node_blit`.
  - Experimental projection renderer covering masks, group layers, current
    non-normal blend modes (`add`, `multiply`, `screen`) and uint8/uint16/float32
    image data.
  - Alpha-carrying projection state so color and projection alpha are no longer
    collapsed during compositing.
  - Normal uint8 projection can use GEGL `over`; broader dtypes and the current
    non-normal modes use matching projection math until dedicated GEGL operation
    nodes are mapped for each mode.
  - GEGL-backed drawable buffer wrapper with generation tracking.
  - Native-assisted NumPy projection backend while GEGL projection compositing is
    completed for masks, groups and non-normal blend modes.
  - Full projection, dirty-region projection, and excluding-one-layer projection
    entry points.

- `src/biopic/native/_stroke_native.c`
  - Dab rasterization.
  - GIMP-style spacing dab generation.
  - Paired content/alpha dab painting.

- `src/biopic/native/_composite_native.c`
  - Normal layer compositing.
  - Offset-aware compositing.
  - Mask-aware compositing.

- `src/biopic/native/_display_native.c`
  - Scientific tile to 8-bit display conversion.

## Non-Negotiable Verification

Pytest is currently not used for this thread because it hangs. Each image-editing
slice must have direct smoke checks:

- native function check,
- tile/drawable check,
- workspace/editor path check,
- no full-image repaint for local dirty operations where applicable.
