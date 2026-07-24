# GPL Editor Integration

SPDX-License-Identifier: GPL-3.0-or-later

BioPic LM is distributed as GPL-3.0-or-later, so GPL-compatible source from GIMP,
Krita, GEGL, babl, or similarly licensed dependencies may be adapted into the
project when provenance is recorded and the combined work remains GPL.

## Current Integration

The first implemented route is an external editor round trip:

1. BioPic LM renders the active image, edit layers, and adjustment layers into a
   lossless TIFF handoff file under `.biopic_cache/<project>/external_edit/`.
2. BioPic LM launches a locally installed GIMP or Krita executable when one is
   discovered on `PATH` or in common Windows install locations.
3. The user edits and saves the handoff file in the external editor.
4. BioPic LM imports the saved file back as a new, unlocked raster edit layer.

This uses the real GIMP/Krita application backends without copying their source
code into BioPic LM.

## Source-Level Vendoring Rules

Before copying or adapting upstream editor source code into BioPic LM:

1. Confirm the upstream file license and copyright header.
2. Copy the upstream license notice into the adapted local file.
3. Record the upstream project, URL, file path, commit hash, local target path,
   license, copyright holder, modification summary, and modification date in
   `docs/THIRD_PARTY_CODE.md`.
4. Keep the local file under GPL-3.0-or-later unless the upstream file requires
   stricter terms.
5. Do not reuse upstream trademarks or application branding for BioPic LM builds.

The preferred source-level direction is to adapt small, isolated algorithms or
interaction state machines first, not to paste a full application subsystem into
the PySide workspace. Full Krita/GIMP embedding would require taking their
document, tile, brush, and event systems as first-class architectural
dependencies rather than treating them as helper functions.
