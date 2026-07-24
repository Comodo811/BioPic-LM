# GIMP Reference Notes

SPDX-License-Identifier: GPL-3.0-or-later

BioPic LM uses GIMP as a design and behavior reference only. The paint-stroke
pipeline is an independent implementation of common brush-editor behavior:

- persistent brush-distance/spacing state,
- brush-spaced dab generation instead of endpoint-connecting strokes,
- native dab rasterization,
- dirty-region publication to the tiled display path.

No GIMP source file, icon, brush, cursor, preset, or other asset has been
copied into BioPic LM. Any future verbatim source reuse must keep the upstream
copyright header in the local file and be listed with file-level provenance in
`docs/THIRD_PARTY_CODE.md`.

BioPic LM now also supports an external GIMP/Krita round trip: the current edit
target is written as a lossless TIFF, opened in the real GPL editor when
installed, and imported back as an unlocked raster layer after the user saves.
This path does not copy upstream source code.

Relevant upstream areas that may be useful as behavior references:

- `app/paint/gimpbrushcore.c`
- `app/paint/gimppaintcore.c`
- `app/paint/gimppaintbrush.c`
- `app/tools/gimp-tools.c`
- `app/tools/gimp-tool-options-manager.c`
- `app/tools/gimprectangleselecttool.*`
- `app/tools/gimpellipseselecttool.*`
- `app/tools/gimpfreeselecttool.*`
- `app/tools/gimpfuzzyselecttool.*`
- `app/tools/gimpbycolorselecttool.*`
- `app/tools/gimpcroptool.*`
- `app/tools/gimpbrushtool.*`
- `app/tools/gimperasertool.*`
- `app/tools/gimpclonetool.*`
- `app/tools/gimphealtool.*`
- `app/tools/gimpcolorpickertool.*`
- `app/tools/gimpmeasuretool.*`
- `app/tools/gimpcurvestool.*`
- `app/tools/gimpfiltertool.*`
