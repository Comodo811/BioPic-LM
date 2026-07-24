# Milestone 8: Export and Packaging Foundations

Implemented:

- Raster export for TIFF/PNG/JPEG/BMP-style outputs.
- Simple rasterized figure-board export helper.
- Preflight checks for missing images, empty panels/boards, duplicate definitions,
  missing calibration, small scale bars, and undefined abbreviations.
- Packaging dependencies and documentation hooks remain in `pyproject.toml`.

Known limitations:

- PDF/SVG vector preservation is not fully implemented yet.
- PyInstaller specs are not generated yet.
