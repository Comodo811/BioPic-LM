# BioPic LM

BioPic LM is a lightweight cross-platform desktop application for building reproducible,
publication-quality microbiological figures from light-microscopy images.

> Beta release: BioPic LM is currently pre-release software. Expect bugs and
> incomplete workflows.

Milestones 1 through 8 provide the runnable application shell, project/document
model, dependency invalidation, atomic project persistence, logging, baseline
tests, image import, stack import, metadata inspection, thumbnail/canvas
workspaces, project save/load for imported sources, and an independent
focus-stacking engine, non-destructive image-editing foundations, and
measurement/calibration/scale-bar models, annotations, figure boards, and
export/preflight foundations.

## Technology

- Python 3.12+
- PySide6 / Qt 6 for native Windows and Linux desktop UI
- NumPy, SciPy, Pillow, tifffile, imageio for scientific imaging foundations
- SQLite-ready project metadata with human-readable JSON manifests
- pytest, ruff, mypy for quality checks
- PyInstaller planned for Windows and Linux packaging

## Run

```powershell
python -m pip install -e .[dev]
biopic-lm
```

If PySide6 is not installed, non-GUI tests and model code still run.

## Test

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
python -m pytest -q
ruff check .
mypy src
```

## Current Scope

The current focus stacker supports translation alignment, Laplacian/modified
Laplacian/Tenengrad/local-variance focus metrics, regularized focus maps, smooth
weighted blending, halo suppression, depth-map output, and parameter provenance.
Rotation/scale alignment and manual mask painting are planned follow-ups.

## Beta Limitations

- Stack from Video is experimental and has not been fully tested.
- Stitch Images is experimental and has not been fully tested.
- Some UI tools and image-editing operations may still have bugs.
- Presets created locally through the app are user settings or project data;
  they are not bundled into the source repository unless exported or saved in a
  project file.

## Distribution

Packaged application builds are kept separate from the source repository.
Local `build/` and `dist/` folders are ignored and should not be committed.
Upload packaged `.zip` builds through GitHub Releases instead.

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for the exact source upload
and release workflow.
