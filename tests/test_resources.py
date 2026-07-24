from pathlib import Path

from biopic.resources import resource_path


def test_resource_path_uses_source_tree_by_default() -> None:
    assert resource_path("icons", "biopic_logo.png").is_file()


def test_resource_path_uses_pyinstaller_meipass(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    assert resource_path("icons", "biopic_logo.png") == tmp_path / "icons" / "biopic_logo.png"
