# Milestone 4: Image Editing Foundations

Implemented:

- Non-destructive editing records:
  - editable layers
  - blend mode metadata
  - selection mask metadata
  - project save/load persistence
- Shared edit-operation dispatcher for UI and future pipeline recompute.
- Required correction/filter foundations:
  - flat-field correction with dark-frame support and near-zero denominator safeguards
  - background subtraction
  - levels
  - auto-levels
  - gamma correction
  - monotonic PCHIP curve adjustment
  - high-pass sharpening
  - Gaussian smoothing
  - median filtering
  - bilateral, non-local-means, wavelet, and total-variation denoising functions
- Geometry operations:
  - crop
  - rotate by 90-degree increments
  - horizontal/vertical flip
  - uniform resize that preserves aspect ratio
- Edit workspace:
  - before/after canvases
  - source image selector
  - operation selector
  - real Apply behavior
  - preview display
  - operation history display
  - processing graph nodes recorded as `edit.*`

Known limitations:

- Brush, clone, heal, and freehand selection tools are not interactive yet.
- Edit nodes record operation provenance and preview output, but full graph recompute/caching is still evolving.
- Layer compositing is represented in the model but not exposed as a complete layer panel yet.
- Advanced curve UI is not graphical yet; the mathematical operation is implemented and tested.

Verification:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`: 18 passed.
- `python -m ruff check .`: passed.
- `python -m mypy src`: passed.
