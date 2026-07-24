from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    """Provide a pytest temp directory inside the writable workspace."""
    root = Path(__file__).resolve().parents[1] / "test_artifacts"
    path = root / uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
