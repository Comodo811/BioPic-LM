import numpy as np

from biopic.imaging.selection import (
    SelectionCombineMode,
    combine_mask_region,
    combine_masks,
    ellipse_mask,
    polygon_mask,
    rectangle_mask,
    selection_shape_region,
)
from biopic.imaging.tiles import TilePaintSession
from biopic.ui.workspace_helpers.paint import fuzzy_selection_region


def test_selection_modes_preserve_soft_coverage() -> None:
    existing = np.zeros((8, 8), dtype=np.float32)
    existing[1:5, 1:5] = 0.5
    new = np.zeros((8, 8), dtype=np.float32)
    new[3:7, 3:7] = 0.75

    added = combine_masks(existing, new, SelectionCombineMode.ADD)
    subtracted = combine_masks(existing, new, SelectionCombineMode.SUBTRACT)
    intersected = combine_masks(existing, new, SelectionCombineMode.INTERSECT)

    assert added[3, 3] == 0.75
    assert subtracted[3, 3] == 0.125
    assert intersected[3, 3] == 0.375


def test_selection_rasterizers_create_float_masks() -> None:
    rect = rectangle_mask((20, 20), (2, 2, 8, 8))
    ellipse = ellipse_mask((20, 20), (2, 2, 9, 9), antialias=True)
    polygon = polygon_mask(
        (20, 20),
        [(2.0, 2.0), (10.0, 2.0), (6.0, 10.0)],
        antialias=True,
        feather_radius_px=2.0,
    )

    for mask in (rect, ellipse, polygon):
        assert mask.dtype == np.float32
        assert float(mask.min()) >= 0.0
        assert float(mask.max()) <= 1.0
    assert np.any((polygon > 0.0) & (polygon < 1.0))


def test_region_selection_matches_full_mask_combination() -> None:
    shape = (120, 160)
    existing = rectangle_mask(shape, (30, 20, 50, 35), feather_radius_px=3.0)
    polygon_points = [(55.0, 40.0), (110.0, 48.0), (85.0, 92.0)]
    full_polygon = polygon_mask(
        shape,
        polygon_points,
        antialias=True,
        feather_radius_px=2.0,
    )
    region = selection_shape_region(
        shape,
        "free",
        (55, 40, 56, 53),
        polygon_points,
        antialias=True,
        feather_radius_px=2.0,
    )
    assert region is not None
    region_rect, region_mask = region

    for mode in (
        SelectionCombineMode.REPLACE,
        SelectionCombineMode.ADD,
        SelectionCombineMode.SUBTRACT,
        SelectionCombineMode.INTERSECT,
    ):
        expected = combine_masks(existing, full_polygon, mode)
        actual = combine_mask_region(existing, region_mask, region_rect, shape, mode)
        np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_tile_paint_respects_soft_selection_mask() -> None:
    base = np.zeros((12, 12), dtype=np.float32)
    content = base.copy()
    alpha = np.zeros((12, 12), dtype=np.float32)
    mask = np.zeros((12, 12), dtype=np.float32)
    mask[3:9, 3:9] = 0.5
    session = TilePaintSession(base, content, alpha, tile_size=8)

    session.paint_content_and_alpha(
        [(6, 6)],
        3,
        1.0,
        alpha_value=1.0,
        selection_mask=mask,
    )
    out, out_alpha = session.materialize()

    assert 0.45 < float(out[6, 6]) < 0.55
    assert 0.45 < float(out_alpha[6, 6]) < 0.55
    assert float(out[1, 1]) == 0.0


def test_fuzzy_selection_returns_contiguous_mask_not_bounding_box() -> None:
    image = np.zeros((12, 12), dtype=np.float32)
    image[2:10, 2:10] = 0.5
    image[5, 5] = 0.0

    region = fuzzy_selection_region(image, 3, 3, tolerance=1.0)

    assert region is not None
    rect, mask = region
    assert rect == (2, 2, 8, 8)
    assert mask.shape == (8, 8)
    assert float(mask[1, 1]) == 1.0
    assert float(mask[3, 3]) == 0.0
