from math import isclose, pi

from biopic.imaging.paint_engine import (
    BrushState,
    DrawablePaintSession,
    GimpPaintCore,
    PaintCoordinates,
    PaintWorkItem,
    PaintWorkQueue,
    PaintWorkType,
    StrokeInterpolator,
    constrain_line_angle,
)


def test_spacing_interpolator_preserves_residual_across_segments() -> None:
    interpolator = StrokeInterpolator(BrushState(size=10.0, spacing=0.5))
    dabs: list[PaintCoordinates] = []

    first = interpolator.interpolate_segment(
        PaintCoordinates(0.0, 0.0),
        PaintCoordinates(3.0, 0.0),
        dabs.append,
    )
    second = interpolator.interpolate_segment(
        PaintCoordinates(3.0, 0.0),
        PaintCoordinates(8.0, 0.0),
        dabs.append,
    )

    assert first == 0
    assert second == 1
    assert len(dabs) == 1
    assert isclose(dabs[0].x, 5.0)


def test_fast_segment_generates_spaced_dabs_not_every_pixel() -> None:
    interpolator = StrokeInterpolator(BrushState(size=20.0, spacing=0.25))
    dabs: list[PaintCoordinates] = []

    count = interpolator.interpolate_segment(
        PaintCoordinates(0.0, 0.0),
        PaintCoordinates(1_000_000.0, 0.0),
        dabs.append,
    )

    assert count == interpolator.limits.maximum_dabs_per_segment
    assert len(dabs) == interpolator.limits.maximum_dabs_per_segment
    assert dabs[0].x == 5.0


def test_gimp_paint_core_owns_spacing_state() -> None:
    core = GimpPaintCore()
    core.begin()

    first = core.motion(PaintCoordinates(1.0, 1.0), 2)
    second = core.motion(PaintCoordinates(6.0, 1.0), 2)

    assert first == [(1, 1)]
    assert second == [(2, 1), (3, 1), (4, 1), (5, 1), (6, 1)]
    assert core.generated_dabs == 6


def test_paint_work_queue_coalesces_motion_but_preserves_barrier_order() -> None:
    queue = PaintWorkQueue(coalesce_after=1)
    stroke = "stroke"
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(1, 1), 1))
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(2, 2), 2))
    queue.insert_finish_barrier(stroke, 3)

    first = queue.pop_nowait()
    second = queue.pop_nowait()

    assert first is not None
    assert first.coordinates.x == 2
    assert second is not None
    assert second.type is PaintWorkType.FINISH_BARRIER
    assert queue.coalesced_events == 1


def test_paint_work_queue_preserves_motion_until_backlog_limit() -> None:
    queue = PaintWorkQueue(coalesce_after=4)
    stroke = "stroke"

    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(1, 1), 1))
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(2, 2), 2))
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(3, 3), 3))
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(4, 4), 4))
    queue.push_motion(PaintWorkItem(PaintWorkType.INTERPOLATE, stroke, PaintCoordinates(5, 5), 5))

    samples = [queue.pop_nowait() for _ in range(4)]

    assert [item.coordinates.x for item in samples if item is not None] == [1, 2, 3, 5]
    assert queue.coalesced_events == 1


def test_drawable_paint_session_tracks_tile_copy_and_display_update_regions() -> None:
    session = DrawablePaintSession("drawable")
    session.begin()
    session.mark_dirty((17, 19, 3, 5))

    copy_rects, update_rects = session.flush_regions()

    assert copy_rects == [(0, 0, 256, 256)]
    assert update_rects == [(0, 0, 32, 32)]
    assert not session.copy_region.rectangles()
    assert not session.update_region.rectangles()


def test_constrain_line_angle_uses_geometric_segment_not_pixel_iteration() -> None:
    start = PaintCoordinates(0.0, 0.0)
    end = PaintCoordinates(10.0, 3.0)

    constrained = constrain_line_angle(start, end, pi / 4.0)

    assert constrained.y == 0.0
    assert constrained.x > 10.0
