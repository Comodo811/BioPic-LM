import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from PySide6.QtWidgets import QApplication

from biopic.imaging.io import (
    BIOPIC_METADATA_KEY,
    RAW_DECODE_WIC_DISPLAY,
    SUPPORTED_EXTENSIONS,
    export_metadata_payload,
    import_images,
    import_stack,
    read_image_asset,
    rembi_metadata,
    write_image_metadata,
)
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.stack_import_resolution import (
    duplicate_basename_extension_groups,
    filter_duplicate_basename_extensions,
    prioritized_extensions,
)
from biopic.ui.workspaces.metadata import MetadataWorkspace


def test_png_import_reads_dimensions_and_dtype(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "sample.png"
    Image.fromarray(np.arange(12, dtype=np.uint8).reshape(3, 4)).save(path)

    result = read_image_asset(path)

    assert result.asset.width == 4
    assert result.asset.height == 3
    assert result.asset.dtype == "uint8"
    assert result.asset.color_model == "grayscale"
    assert result.asset.checksum is not None


def test_jpeg_import_applies_exif_orientation(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "oriented.jpg"
    image = Image.fromarray(np.zeros((3, 5, 3), dtype=np.uint8))
    exif = image.getexif()
    exif[274] = 6
    image.save(path, exif=exif)

    result = read_image_asset(path, load_pixels=True)

    assert result.asset.width == 3
    assert result.asset.height == 5
    assert result.pixels.shape[:2] == (5, 3)


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


def test_write_image_metadata_embeds_tiff_metadata(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "metadata.tif"
    data = np.arange(4 * 5, dtype=np.uint16).reshape(4, 5)
    tifffile.imwrite(path, data)

    assert write_image_metadata(
        path,
        {"scientific_name": "Brachionus calyciflorus", "camera": "Axiocam"},
    )

    result = read_image_asset(path, load_pixels=True)
    assert result.asset.metadata["scientific_name"] == "Brachionus calyciflorus"
    assert result.asset.metadata["camera"] == "Axiocam"
    assert np.array_equal(result.pixels, data)


def test_tiff_metadata_embeds_rembi_mapping_and_drops_jfif_fields(
    workspace_tmp_path: Path,
) -> None:
    path = workspace_tmp_path / "rembi-metadata.tif"
    data = np.arange(4 * 5, dtype=np.uint16).reshape(4, 5)
    tifffile.imwrite(path, data)

    metadata = {
        "scientific_name": "Brachionus calyciflorus",
        "taxonomy": "http://purl.obolibrary.org/obo/NCBITaxon_10195",
        "sex": "female",
        "life_stage": "adult",
        "body_part": "whole organism",
        "orientation": "dorsal",
        "microscope": "Zeiss Axioscope",
        "camera": "Axiocam",
        "magnification": "40x",
        "physical_pixel_size": 0.5,
        "jfif": 257,
        "jfif_version": (1, 1),
        "jfif_unit": 1,
        "jfif_density": (300, 300),
    }

    assert write_image_metadata(path, metadata)

    result = read_image_asset(path, load_pixels=True)
    assert result.asset.metadata["scientific_name"] == "Brachionus calyciflorus"
    assert "jfif" not in result.asset.metadata
    assert "jfif_version" not in result.asset.metadata
    with tifffile.TiffFile(path) as tif:
        xmp = tif.pages[0].tags[700].value.decode("utf-8")
    assert "biopic:rembi" in xmp
    assert "biosample" in xmp
    assert "image_acquisition" in xmp
    assert "nominal_magnification" in xmp
    assert "imaging_instrument" in xmp
    assert "detector" in xmp
    assert "jfif" not in xmp


def test_rembi_metadata_maps_biopic_fields_to_standard_sections() -> None:
    rembi = rembi_metadata(
        {
            "scientific_name": "Hydra vulgaris",
            "body_part": "head",
            "orientation": "lateral",
            "microscope": "Olympus BX53",
            "camera": "DP74",
            "magnification": "20x",
            "physical_pixel_size": 0.25,
        }
    )

    assert rembi["rembi_version"] == "1.5"
    assert rembi["biosample"]["organism"]["scientific_name"] == "Hydra vulgaris"
    assert rembi["biosample"]["biological_entity"] == "head"
    assert rembi["specimen"]["location_within_biosample"] == "orientation: lateral; body_part: head"
    assert rembi["image_acquisition"]["imaging_instrument"] == "Olympus BX53"
    assert rembi["image_acquisition"]["detector"] == "DP74"
    assert rembi["image_acquisition"]["nominal_magnification"] == "20x"
    assert rembi["image_data"]["pixel_voxel_size"] == 0.25


def test_export_metadata_payload_removes_container_specific_jfif() -> None:
    payload = export_metadata_payload(
        {
            "scientific_name": "Hydra vulgaris",
            "jfif": 257,
            "jfif_version": (1, 1),
            "jfif_unit": 1,
            "jfif_density": (72, 72),
        }
    )

    assert payload == {"scientific_name": "Hydra vulgaris"}


def test_write_image_metadata_embeds_png_metadata(workspace_tmp_path: Path) -> None:
    path = workspace_tmp_path / "metadata.png"
    Image.fromarray(np.full((4, 5), 32, dtype=np.uint8)).save(path)

    assert write_image_metadata(path, {"scientific_name": "Hydra vulgaris"})

    with Image.open(path) as image:
        assert BIOPIC_METADATA_KEY in image.info
    result = read_image_asset(path)
    assert result.asset.metadata["scientific_name"] == "Hydra vulgaris"


def test_metadata_workspace_writes_typed_metadata_to_tiff_file(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    path = workspace_tmp_path / "metadata-workspace.tif"
    tifffile.imwrite(path, np.full((4, 5), 100, dtype=np.uint16))
    project = Project.new("Metadata Workspace")
    asset = import_images(project, [path])[0]
    workspace = MetadataWorkspace(project)
    workspace.refresh()

    editor = workspace.fields["scientific_name"]
    editor.setText("Paramecium caudatum")  # type: ignore[attr-defined]
    workspace._store_current_metadata()

    result = read_image_asset(Path(asset.path))
    assert result.asset.metadata["scientific_name"] == "Paramecium caudatum"


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


def test_raw_load_pixels_uses_active_crop_and_fixed_brightness(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    path = workspace_tmp_path / "camera.dng"
    path.write_bytes(b"fake raw")
    calls: list[dict[str, object]] = []

    class _Sizes:
        width = 4
        height = 3
        crop_width = 2
        crop_height = 2
        flip = 0

    class _Raw:
        sizes = _Sizes()
        raw_image_visible = np.zeros((2, 2), dtype=np.uint16)
        black_level_per_channel = (64, 65, 66, 67)
        camera_whitebalance = (2.0, 1.0, 1.5, 0.0)
        daylight_whitebalance = (1.8, 1.0, 1.3, 0.0)
        white_level = 65535
        color_desc = b"RGBG"
        num_colors = 3
        raw_pattern = np.array([[0, 1], [1, 2]], dtype=np.uint8)
        color_matrix = np.eye(3, dtype=np.float32)
        rgb_xyz_matrix = np.eye(3, dtype=np.float32)
        camera_white_level_per_channel = (65535, 65535, 65535, 65535)

        def __enter__(self) -> "_Raw":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def postprocess(self, **kwargs: object) -> np.ndarray:
            calls.append(kwargs)
            return np.full((3, 4, 3), 40000, dtype=np.uint16)

    class _RawPy:
        @staticmethod
        def imread(_path: str) -> _Raw:
            return _Raw()

    monkeypatch.setitem(sys.modules, "rawpy", _RawPy)

    result = read_image_asset(path, load_pixels=True)

    assert result.pixels.dtype == np.uint16
    assert result.pixels.shape == (2, 2, 3)
    assert result.asset.width == 2
    assert result.asset.height == 2
    assert calls[-1]["no_auto_bright"] is True
    assert calls[-1]["bright"] == 3.75
    assert calls[-1]["use_camera_wb"] is True
    assert result.asset.metadata["raw_pipeline_available"] is True
    assert result.asset.metadata["raw_import_backend"] == "rawpy"
    assert result.asset.metadata["raw_import_use_camera_wb"] is True
    assert result.asset.metadata["raw_visible_shape"] == [2, 2]
    assert result.asset.metadata["camera_whitebalance"] == [2.0, 1.0, 1.5, 0.0]
    assert result.asset.metadata["daylight_whitebalance"] == [1.8, 1.0, 1.3, 0.0]
    assert result.asset.metadata["raw_color_description"] == "RGBG"
    assert result.asset.metadata["raw_rgb_xyz_matrix"] == np.eye(3, dtype=np.float32).tolist()


def test_raw_wic_display_mode_uses_display_decode_when_available(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    path = workspace_tmp_path / "camera.cr2"
    path.write_bytes(b"fake raw")
    pixels = np.full((3, 4, 3), 127, dtype=np.uint8)

    monkeypatch.setattr("biopic.imaging.io._decode_wic_32bpp_bgra", lambda _path: pixels)

    result = read_image_asset(
        path,
        load_pixels=True,
        raw_decode_mode=RAW_DECODE_WIC_DISPLAY,
    )

    assert result.pixels.dtype == np.uint8
    assert result.pixels.shape == (3, 4, 3)
    assert result.asset.width == 4
    assert result.asset.height == 3
    assert result.asset.metadata["raw_import_backend"] == "windows_wic_32bpp_bgra"


def test_raw_wic_display_mode_falls_back_to_rawpy(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    path = workspace_tmp_path / "camera.cr2"
    path.write_bytes(b"fake raw")

    class _Sizes:
        width = 2
        height = 2
        crop_width = 2
        crop_height = 2
        flip = 0

    class _Raw:
        sizes = _Sizes()
        black_level_per_channel = ()
        camera_whitebalance = ()
        daylight_whitebalance = ()
        white_level = 65535

        def __enter__(self) -> "_Raw":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def postprocess(self, **_kwargs: object) -> np.ndarray:
            return np.full((2, 2, 3), 40000, dtype=np.uint16)

    class _RawPy:
        @staticmethod
        def imread(_path: str) -> _Raw:
            return _Raw()

    monkeypatch.setattr(
        "biopic.imaging.io._decode_wic_32bpp_bgra",
        lambda _path: (_ for _ in ()).throw(OSError("no codec")),
    )
    monkeypatch.setitem(sys.modules, "rawpy", _RawPy)

    result = read_image_asset(
        path,
        load_pixels=True,
        raw_decode_mode=RAW_DECODE_WIC_DISPLAY,
    )

    assert result.pixels.dtype == np.uint16
    assert result.asset.metadata["raw_import_brightness"] == 3.75


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


def test_import_stack_reports_progress(workspace_tmp_path: Path) -> None:
    paths: list[Path] = []
    for index in range(2):
        path = workspace_tmp_path / f"progress_{index}.png"
        Image.fromarray(np.full((4, 4), index, dtype=np.uint8)).save(path)
        paths.append(path)
    project = Project.new("Stack Progress")
    updates: list[tuple[int, int, str]] = []

    import_stack(
        project,
        paths,
        StackKind.FOCAL,
        progress=lambda done, total, path: updates.append((done, total, path.name)),
    )

    assert updates == [(1, 2, "progress_0.png"), (2, 2, "progress_1.png")]


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
