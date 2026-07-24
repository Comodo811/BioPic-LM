# GIMP Paint Architecture Mapping

SPDX-License-Identifier: GPL-3.0-or-later

BioPic LM is GPL-3.0-or-later. The editor architecture below is modeled after
GIMP's paint, drawable, projection, and display responsibilities without
copying large upstream source files verbatim.

## Upstream Files Responsible

- `app/tools/gimppainttool-paint.c`
  - Starts/ends paint sessions.
  - Queues paint motion work.
  - Uses a short display update interval.
  - Flushes drawable paint, projection, and display after batched paint work.

- `app/tools/gimppainttool.c`
  - Owns the interactive paint tool shell.
  - Routes pointer/motion events into the paint pipeline.

- `app/paint/gimppaintcore.c`
  - Owns stroke state, interpolation, smoothing, paint start/finish/cancel.

- `app/paint/gimpbrushcore.c`
  - Handles brush-specific dab generation, spacing, and brush masks.

- `app/core/gimpdrawable.c`
  - Represents editable pixel drawables.
  - Starts and ends paint mode on drawable buffers.
  - Flushes painted dirty regions.

- `app/core/gimplayer.c`
  - Adds layer compositing properties on top of drawable pixels.

- `app/core/gimpprojection.c`
  - Maintains the projected image from the layer stack.
  - Flushes invalidated dirty regions.

- `app/display/gimpdisplayshell-render.c`
  - Renders display regions through a cached/tiled display path.
  - Tracks full and area invalidation.

- `app/display/gimpdisplayshell-draw.c`
  - Draws the shell/canvas and requested update areas.

- `app/display/gimpdisplayshell-tool-events.c`
  - Receives pointer events and delegates them to the active tool.

## BioPic LM Counterparts

- `src/biopic/ui/workspace.py`
  - `EditWorkspace._paint_work_queue`
  - `EditWorkspace._paint_flush_timer`
  - `EditWorkspace._flush_queued_paint_points`
  - `EditWorkspace._gimp_style_spacing_points`
  - This recreates the GIMP paint-queue/display-interval pattern and brush
    spacing accumulator.

- `src/biopic/imaging/tiles.py`
  - `TilePaintSession`
  - Dirty tile patches and dirty rectangle union.

- `src/biopic/imaging/layer_buffers.py`
  - Live layer buffers analogous to drawable backing buffers.

- `src/biopic/imaging/project_render.py`
  - Full and dirty-region projection compositing.

- `src/biopic/ui/image_canvas.py`
  - Tiled display items and dirty tile updates.

## Implemented Behavioral Requirements

- Pointer motion is queued during active paint strokes.
- The queue is flushed on a short Qt timer and at stroke end.
- Brush/eraser dabs are emitted from a persistent GIMP-style spacing remainder,
  not by connecting every pointer event endpoint.
- Coordinates are nudged away from exact integers before spacing decisions to
  avoid rounding artifacts.
- Live stroke preview is separate from layer data.
- Brush/pencil/eraser touch layer tiles, not whole image payloads.
- Undo stores tile patches for paint strokes.
- Projection updates dirty regions.
- Canvas display updates dirty tiles.
- Layer payload serialization is deferred until save.
