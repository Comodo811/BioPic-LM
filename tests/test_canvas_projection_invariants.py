from pathlib import Path


def test_live_paint_preview_is_not_promoted_to_current_projection() -> None:
    workspace_source = Path("src/biopic/ui/workspace.py").read_text(encoding="utf-8")

    assert "_current_pixels = self._paint_stroke_preview" not in workspace_source
    assert "set_pixels(self._paint_stroke_preview" not in workspace_source
    assert "update_tile_region(self._paint_stroke_preview" not in workspace_source
    assert "update_tile_regions(self._paint_stroke_preview" not in workspace_source
