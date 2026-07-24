# Milestone 5: Measurement and Scale Bars

Implemented:

- Calibration from known pixel and physical distance.
- Magnification parsing for `10`, `10x`, `10 x`, and `10x`/multiplication-sign forms.
- Permanent camera and microscope scale preset model.
- Magnification scale rows with fluid, unit, pixels/unit, and unit/pixel calculations.
- Measurement model for line, polyline, angle, rectangle, ellipse, and polygon kinds.
- Length and area calculations using current image calibration.
- Measurement table rows and CSV export.
- Vector-like scale-bar model linked to calibration.
- Scale-bar pixel length calculation from physical length and unit-per-pixel calibration.
- Project save/load for calibrations, presets, measurements, and scale bars.
- Measure and Scale workspace:
  - image selector
  - Set Scale controls
  - permanent preset creation
  - Add Scale Bar controls
  - simple line measurement creation
  - record/status panel

Known limitations:

- Measurement drawing is not yet interactive on the canvas; the workspace uses numeric entry.
- Full preset edit/duplicate/import/export dialogs are represented by models and persistence, but not complete dialogs.
- Scale bars are stored as vector-like objects and listed, but not yet overlaid on the image canvas.
- Unit conversion between differing physical units is not implemented yet; scale bars currently require the calibration unit.

Verification:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`: 24 passed.
- `python -m ruff check .`: passed.
- `python -m mypy src`: passed.
