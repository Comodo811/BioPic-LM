# Distribution and GitHub Releases

SPDX-License-Identifier: GPL-3.0-or-later

Keep BioPic LM source code and packaged application builds separate.

This release line is a beta. Mark GitHub releases as pre-release until the
Stack from Video and Stitch Images workflows have been tested and stabilized.

## Source Repository

Commit the files needed to build, test, and package BioPic LM:

- `src/`
- `tests/`
- `docs/`
- `icons/`
- `packaging/`
- `README.md`
- `LICENSE`, `COPYING`, `NOTICE`, `AUTHORS`
- `pyproject.toml`
- `setup.py`
- `BioPicLM.spec`

Do not commit local build output:

- `build/`
- `dist/`
- `.biopic_cache/`
- test/cache folders
- release archives such as `.zip`, `.7z`, `.tar.gz`, or `.whl`

These paths are ignored by `.gitignore`.

## Presets

Built-in repository presets are bundled only if they exist under
`src/biopic/presets/`. At the moment this folder contains no user preset data.

User-created presets are stored in one of two places:

- Saved project files, for project-specific metadata and scale presets.
- Local application settings, for persistent user presets created inside the app.

Local application settings are not included in a source upload, GitHub Release,
or PyInstaller build by default. Export any preset you want to distribute and
commit it as an explicit data file before building.

## Windows Distribution Build

From a clean checkout:

```powershell
python -m pip install -e .[packaging,raw]
python -m PyInstaller BioPicLM.spec --clean --noconfirm
```

For a CUDA-enabled build, the build machine must have a compatible NVIDIA
driver and CUDA runtime support. Install the optional CUDA extra before running
PyInstaller:

```powershell
python -m pip install -e .[packaging,raw,cuda]
python -c "from biopic.imaging.stacking import gpu_backend_status; print(gpu_backend_status())"
python -m PyInstaller BioPicLM.spec --clean --noconfirm
```

The packaged app bundles the Python CUDA-array package from the build
environment. Target machines still need a compatible NVIDIA driver. If CuPy or
CUDA is unavailable, BioPic falls back to the CPU stacking path.

Current CUDA coverage:

- Depth Map uses a CuPy GPU-first path for focus scoring, smoothing, depth
  selection, confidence, blending and final cleanup.
- Depth Map can fall back to overlapping tiled GPU processing when the full
  stack does not fit in the configured VRAM budget. BioPic defaults to a
  conservative 4 GB budget for microscopy-camera stacks.
- Pyramid Max Contrast uses a CuPy GPU-first path for pyramid construction,
  contrast maps, winner selection, depth voting and reconstruction.
- Pyramid Max Contrast also has tiled GPU processing for stacks that exceed the
  configured VRAM budget.
- Alignment can use OpenCV CUDA for the full-resolution affine warp when a CUDA
  OpenCV build is present. Transform estimation remains CPU-based.
- Custom stacking has partial CUDA/OpenCV acceleration for focus scoring and
  filtering, but the decompiled-style multi-buffer update logic remains CPU.

The packaged app is created under:

```text
dist/BioPic LM/
```

Create a release archive outside the tracked source tree or from the ignored
`dist/` folder:

```powershell
Compress-Archive -Path "dist\BioPic LM" -DestinationPath BioPic-LM-windows-x64.zip -Force
```

Upload that archive to a GitHub Release. Do not commit it to the source branch.

## GitHub Upload Workflow

Create or choose a GitHub repository, then from this repository:

```powershell
git status
git add .gitignore README.md AUTHORS NOTICE docs src tests icons packaging pyproject.toml setup.py BioPicLM.spec LICENSE COPYING
git commit -m "Prepare BioPic LM beta source repository"
git branch -M main
git remote add origin https://github.com/YOUR_USER_OR_ORG/biopic.git
git push -u origin main
```

For each packaged app build, create a GitHub Release from a tag:

```powershell
git tag v0.1.0-beta.1
git push origin v0.1.0-beta.1
```

Then create a GitHub Release for `v0.1.0-beta.1`, mark it as a pre-release, and
attach `BioPic-LM-windows-x64.zip`.
