from biopic.imaging.display import DisplayShellState, DisplayTileCache


def test_display_shell_tracks_view_state_without_pixels() -> None:
    shell = DisplayShellState()

    shell.set_image_size(1024, 768)
    shell.set_offsets(12.5, -3.0)
    shell.set_scale(2.25)

    assert shell.image_rect() == (0, 0, 1024, 768)
    assert shell.offset_x == 12.5
    assert shell.offset_y == -3.0
    assert shell.scale_x == 2.25
    assert shell.scale_y == 2.25
    assert shell.render_scale == 4


def test_display_cache_invalidates_only_intersecting_tiles() -> None:
    cache = DisplayTileCache(tile_size=256)
    for tile in [(0, 0), (1, 0), (2, 0), (0, 1)]:
        cache.mark_valid(*tile)

    dirty_tiles = cache.invalidate_area((250, 10, 20, 20))

    assert dirty_tiles == {(0, 0), (1, 0)}
    assert not cache.is_valid(0, 0)
    assert not cache.is_valid(1, 0)
    assert cache.is_valid(2, 0)
    assert cache.is_valid(0, 1)


def test_display_shell_clips_invalid_regions() -> None:
    shell = DisplayShellState(image_width=100, image_height=50)

    clipped = shell.invalidate_area((-10, 40, 30, 30))

    assert clipped == (0, 40, 20, 10)
    assert shell.take_invalid_regions() == [clipped]
