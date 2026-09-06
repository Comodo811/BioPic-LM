# Milestone 3: Focus Stacking

Implemented:

- Independent focus-stacking code derived from documented algorithms.
- Translation alignment with phase correlation.
- Focus metrics:
  - Laplacian magnitude
  - Modified Laplacian
  - Tenengrad gradient
  - Local variance
- Spatially regularized focus maps.
- Soft per-frame focus weights instead of hard pixel maxima.
- Weighted blending with basic halo suppression.
- Optional depth-map output.
- Reproducible `FocusStackParameters` serialization.
- Qt worker thread for stack processing with progress and cancellation request state.
- Stack workspace controls for metric, radius, smoothing, alignment, and preview scale.
- Result display in the lower-right stack pane.
- Focus-stack processing nodes linked to imported source-image nodes with transform provenance.

Reference behavior preserved:

- Explicit Stacking and Alignment concepts.
- Optional alignment before stacking.
- Depth-map output as a first-class result.
- Stack/result progress reporting.
- Source/result workspace separation.
- Source image skipping is represented in the stack model through enabled asset ids.

Known limitations:

- Alignment is translation-only in this milestone; rotation and scale correction are next.
- Preview/full result is computed in memory rather than through a tiled cache.
- Manual correction masks and paint tools are not implemented yet.
- Step export is represented in provenance but not written as image files yet.
- Cancellation is checked between major stages; fine-grained cancellation inside numerical kernels is pending.

Verification:

- `python -m pytest -q` passes when run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- `python -m ruff check .` passes.
- `python -m mypy src` passes.
- The pytest environment variable avoids unrelated globally installed pytest plugins that hang during startup in this desktop environment.
