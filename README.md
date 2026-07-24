# BioPic LM

BioPic LM is a desktop application for organizing light-microscopy images and
building reproducible, publication-ready biological figure panels.

This repository contains the source code. Packaged Windows builds are published
separately as GitHub Release assets.

## Beta Status

BioPic LM `0.1.0 beta 1` is a pre-release build. It is intended for early
testing, not final production work.

Known beta limitations:

- Stack from Video is experimental and not fully tested.
- Stitch Images is experimental and not fully tested.
- Some image-editing tools and UI workflows may still contain bugs.
- Performance for very large images can still vary by operation and hardware.

When publishing this version on GitHub, mark the release as a pre-release.

## Main Features

- Import common microscopy image formats, including TIFF and RAW when `rawpy` is
  installed.
- Manage image sources, image stacks, metadata, measurements, annotations, and
  figure boards in one project.
- Create focus stacks with alignment, focus metrics, depth maps, and provenance.
- Apply non-destructive edit layers, adjustment layers, filters, selections,
  scale bars, and annotations.
- Build figure boards with panel layout, labels, spacing, captions, and export
  support.
- Save projects as human-readable `.biopic.json` manifests.

## Experimental Features

- Stack from Video: import video, cut retained sections, extract frames, and
  create an image stack.
- Stitch Images: combine overlapping standalone images into a stitched result.

These workflows are included for testing, but they should not be considered
stable yet.

## Requirements

For source/development use:

- Python 3.12 or newer
- Windows or Linux
- PySide6 / Qt 6
- NumPy, SciPy, Pillow, tifffile, imageio, OpenCV, scikit-image
- Optional RAW support: `rawpy`

For end users, a packaged release build should run without installing Python.

## Run From Source

From the repository root:

```powershell
python -m pip install -e .[dev,raw]
biopic-lm
```

The legacy command alias also works:

```powershell
biopic
```

## Tests And Checks

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
python -m pytest -q
python -m ruff check .
python -m mypy src
```

Some test workflows may still need local cleanup during beta development.

## Build A Windows Distribution

Install packaging dependencies:

```powershell
python -m pip install -e .[packaging,raw]
```

Build the app:

```powershell
python -m PyInstaller BioPicLM.spec --clean --noconfirm
```

The packaged application is created at:

```text
dist/BioPic LM/
```

Create a release ZIP:

```powershell
Compress-Archive -Path "dist\BioPic LM" -DestinationPath BioPic-LM-windows-x64.zip -Force
```

Do not commit `build/`, `dist/`, or release ZIP files. Upload the ZIP as a
GitHub Release asset instead.

## Presets

User-created presets are not automatically bundled into a source upload or
binary release.

Preset storage depends on how the preset was created:

- Project-specific presets are saved inside `.biopic.json` project files.
- Persistent user presets are stored in local application settings.
- Bundled presets must be exported or added explicitly under
  `src/biopic/presets/` before packaging.

At the moment, `src/biopic/presets/` does not contain user preset data.

## GitHub Release Workflow

Commit source code to the repository:

```powershell
git status
git add .gitignore README.md AUTHORS NOTICE docs src tests icons packaging pyproject.toml setup.py BioPicLM.spec LICENSE COPYING
git commit -m "Prepare BioPic LM beta source repository"
git branch -M main
git remote add origin https://github.com/YOUR_USER_OR_ORG/biopic-lm.git
git push -u origin main
```

Tag the beta release:

```powershell
git tag v0.1.0-beta.1
git push origin v0.1.0-beta.1
```

Create a GitHub Release for `v0.1.0-beta.1`, mark it as a pre-release, and
attach `BioPic-LM-windows-x64.zip`.

## Repository Layout

```text
src/biopic/       Application source code
tests/            Tests and regression checks
docs/             Architecture, licensing, and release notes
icons/            Application icon and logo assets
packaging/        PyInstaller launcher and packaging helpers
BioPicLM.spec     PyInstaller build specification
```

## Licensing And Attribution

BioPic LM is distributed under GPL-3.0-or-later.

GIMP and RawTherapee are used only as behavior and user-interface references.
No GIMP or RawTherapee source file, icon, brush, cursor, preset, or other asset
has been copied into this repository.

See:

- `LICENSE`
- `COPYING`
- `NOTICE`
- `AUTHORS`
- `docs/THIRD_PARTY_CODE.md`
