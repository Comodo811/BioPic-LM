from math import isclose, pi

import pytest

from biopic.imaging.transforms import (
    Mat3,
    MoveSnapshot,
    MoveToolCore,
    OutputSafety,
    RectD,
    RotationParameters,
    ScaleParameters,
    TransformClipMode,
    TransformError,
    TransformSession,
    Vec2,
    calculate_output_bounds,
    checked_pixel_count,
    rotation_drag_angle,
    snap_angle,
    transform_bounds,
    validate_matrix,
)


def test_mat3_identity_translation_scale_and_composition_order() -> None:
    point = Vec2(2.0, 3.0)
    assert Mat3.identity().transform_point(point) == point
    assert Mat3.translation(5.0, -1.0).transform_point(point) == Vec2(7.0, 2.0)
    assert Mat3.scale(2.0, 3.0).transform_point(point) == Vec2(4.0, 9.0)

    composed = Mat3.translation(10.0, 0.0) @ Mat3.scale(2.0, 2.0)

    assert composed.transform_point(point) == Vec2(14.0, 6.0)


def test_mat3_rotation_about_origin_and_pivot() -> None:
    rotated = Mat3.rotation(pi / 2.0).transform_point(Vec2(1.0, 0.0))
    assert isclose(rotated.x, 0.0, abs_tol=1e-9)
    assert isclose(rotated.y, 1.0, abs_tol=1e-9)

    pivoted = RotationParameters(pi / 2.0, Vec2(1.0, 1.0)).matrix()
    point = pivoted.transform_point(Vec2(2.0, 1.0))

    assert isclose(point.x, 1.0, abs_tol=1e-9)
    assert isclose(point.y, 2.0, abs_tol=1e-9)


def test_mat3_inverse_and_invalid_matrix_rejection() -> None:
    matrix = Mat3.translation(4.0, 3.0) @ Mat3.scale(2.0, 5.0)
    restored = matrix.inverse().transform_point(matrix.transform_point(Vec2(7.0, 11.0)))

    assert isclose(restored.x, 7.0, abs_tol=1e-9)
    assert isclose(restored.y, 11.0, abs_tol=1e-9)
    assert validate_matrix(Mat3.scale(0.0, 1.0)).code is TransformError.SINGULAR_MATRIX
    assert validate_matrix(Mat3(a=float("nan"))).code is TransformError.INVALID_MATRIX


def test_scale_parameters_and_bounds_round_outward() -> None:
    matrix = ScaleParameters(RectD(10.0, 20.0, 100.0, 50.0), RectD(5.0, 8.0, 50.0, 100.0)).matrix()

    assert matrix.transform_point(Vec2(10.0, 20.0)) == Vec2(5.0, 8.0)
    assert matrix.transform_point(Vec2(110.0, 70.0)) == Vec2(55.0, 108.0)

    bounds = transform_bounds(RectD(0.0, 0.0, 10.0, 10.0), Mat3.rotation(pi / 4.0))
    rounded = bounds.rounded_outward()

    assert rounded[2] > 10
    assert rounded[3] > 10


def test_output_bounds_clip_adjust_and_safety() -> None:
    matrix = Mat3.translation(2.4, -3.2)

    assert calculate_output_bounds(matrix, (0, 0, 10, 10), TransformClipMode.CLIP) == (
        0,
        0,
        10,
        10,
    )
    assert calculate_output_bounds(matrix, (0, 0, 10, 10), TransformClipMode.ADJUST) == (
        2,
        -4,
        11,
        11,
    )
    assert checked_pixel_count(100, 100, 4).valid
    assert not checked_pixel_count(-1, 100, 4).valid
    huge = checked_pixel_count(100_000, 100_000, 4, max_bytes=1024)
    assert huge == OutputSafety(
        False,
        estimated_bytes=40_000_000_000,
        message="Transform output would require about 40000000000 bytes.",
    )


def test_move_tool_uses_total_delta_not_incremental_rounding() -> None:
    tool = MoveToolCore()
    tool.begin_move([MoveSnapshot("layer", Vec2(10.0, 10.0))], Vec2(0.0, 0.0))

    assert tool.update_move(Vec2(0.4, 0.4))["layer"] == (10, 10)
    assert tool.update_move(Vec2(0.8, 0.8))["layer"] == (11, 11)
    assert tool.cancel_move()["layer"] == (10, 10)


def test_rotation_drag_angle_crosses_pi_boundary_and_snaps() -> None:
    angle = rotation_drag_angle(Vec2(-1.0, 0.01), Vec2(-1.0, -0.01), Vec2(0.0, 0.0))

    assert abs(angle) < 0.03
    assert isclose(snap_angle(14.0 * pi / 180.0), pi / 12.0)


def test_transform_session_updates_from_original_bounds() -> None:
    session = TransformSession(original_bounds=RectD(0.0, 0.0, 10.0, 20.0))
    result = session.update_matrix(Mat3.translation(5.0, 7.0))

    assert result.valid
    assert session.session_generation == 1
    assert session.transformed_bounds == RectD(5.0, 7.0, 10.0, 20.0)


def test_scale_empty_source_rejected() -> None:
    with pytest.raises(ValueError):
        ScaleParameters(RectD(0.0, 0.0, 0.0, 1.0), RectD(0.0, 0.0, 1.0, 1.0)).matrix()
