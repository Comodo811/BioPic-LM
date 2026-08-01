from biopic.ui.settings import _apply_selected_save_filter_suffix


def test_save_filter_replaces_stale_tiff_suffix_for_jpeg() -> None:
    path = _apply_selected_save_filter_suffix(
        "stacked_result.tif",
        "JPEG (*.jpg *.jpeg)",
    )

    assert path.endswith("stacked_result.jpg")


def test_save_filter_adds_selected_suffix_when_missing() -> None:
    path = _apply_selected_save_filter_suffix(
        "stacked_result",
        "PNG (*.png)",
    )

    assert path.endswith("stacked_result.png")
