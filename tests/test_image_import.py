import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from biopic.imaging.io import SUPPORTED_EXTENSIONS, import_images, import_stack, read_image_asset
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.stack_import_resolution import (
    duplicate_basename_extension_groups,
    filter_duplicate_basename_extensions,
    prioritized_extensions,
)


def test_png_import_reads_dimensions_and_dtype(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "sample.png"
    Image.fromarray(np.arange(12, dtype=np.uint8).reshape(3, 4)).save(path)

    result = read_image_asset(path)

    assert result.asset.width == 4
    assert result.asset.height == 3
    assert result.asset.dtype == "uint8"
    assert result.asset.color_model == "grayscale"
    assert result.asset.checksum is not None


def test_tiff_import_preserves_16_bit_stack_metadata(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "stack.tif"
    data = np.arange(2 * 5 * 7, dtype=np.uint16).reshape(2, 5, 7)
    tifffile.imwrite(path, data, imagej=True, metadata={"unit": "um", "spacing": 1.25})

    result = read_image_asset(path, load_pixels=True)

    assert result.asset.width == 7
    assert result.asset.height == 5
    assert result.asset.frames == 2
    assert result.asset.dtype == "uint16"
    assert result.pixels.dtype == np.uint16
    assert result.pixels.shape == (2, 5, 7)


def test_tiff_load_pixels_accepts_uncompressed_memmappable_data(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "large_uncompressed.tif"
    data = np.arange(4 * 5, dtype=np.uint16).reshape(4, 5)
    tifffile.imwrite(path, data, compression=None)

    result = read_image_asset(path, load_pixels=True)

    assert result.asset.width == 5
    assert result.asset.height == 4
    assert result.pixels.dtype == np.uint16
    assert np.array_equal(result.pixels, data)


def test_raw_extension_reports_optional_dependency_when_rawpy_missing(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    path = workspace_tmp_path / "camera.dng"
    path.write_bytes(b"not a real raw")
    monkeypatch.setitem(sys.modules, "rawpy", None)

    assert ".dng" in SUPPORTED_EXTENSIONS
    try:
        read_image_asset(path)
    except ValueError as exc:
        assert "rawpy" in str(exc)
    else:  # pragma: no cover - would require rawpy to be installed despite monkeypatching
        raise AssertionError("RAW import should require rawpy when the module is unavailable")


def test_import_stack_preserves_order_and_round_trips(workspace_tmp_path: Path) -> None:
    paths: list[Path] = []
    for index in range(3):
        path = workspace_tmp_path / f"z_{index}.png"
        Image.fromarray(np.full((4, 4), index, dtype=np.uint8)).save(path)
        paths.append(path)
    project = Project.new("Stack Project")

    stack = import_stack(project, paths, StackKind.FOCAL)

    assert stack.asset_ids == list(project.assets.keys())
    assert stack.enabled_asset_ids == stack.asset_ids
    assert len(project.graph.nodes) == 3

    save_path = workspace_tmp_path / "stack_project.biopic.json"
    store = ProjectStore()
    store.save(project, save_path)
    loaded = store.load(save_path)

    loaded_stack = loaded.stacks[stack.id]
    assert loaded_stack.asset_ids == stack.asset_ids
    assert [loaded.assets[asset_id].filename for asset_id in loaded_stack.asset_ids] == [
        "z_0.png",
        "z_1.png",
        "z_2.png",
    ]


def test_stack_import_duplicate_file_types_can_prioritize_raw(
    workspace_tmp_path: Path,
) -> None:
    paths = [
        workspace_tmp_path / "sample_001.CR2",
        workspace_tmp_path / "sample_001.JPG",
        workspace_tmp_path / "sample_002.CR2",
        workspace_tmp_path / "sample_002.JPG",
        workspace_tmp_path / "sample_003.CR2",
    ]

    conflicts = duplicate_basename_extension_groups(paths)
    filtered = filter_duplicate_basename_extensions(paths, preferred_extension=".cr2")

    assert set(conflicts) == {"sample_001", "sample_002"}
    assert prioritized_extensions(paths)[0] == ".cr2"
    assert [path.name for path in filtered] == [
        "sample_001.CR2",
        "sample_002.CR2",
        "sample_003.CR2",
    ]


def test_import_images_as_independent_sources(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "independent.bmp"
    Image.fromarray(np.zeros((2, 3, 3), dtype=np.uint8)).save(path)
    project = Project.new("Independent")

    assets = import_images(project, [path])

    assert len(assets) == 1
    assert not project.stacks
    assert assets[0].color_model == "rgb"
