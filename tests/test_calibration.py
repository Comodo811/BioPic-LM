import pytest

from biopic.models.calibration import Calibration


def test_calibration_calculations() -> None:
    calibration = Calibration.from_known_distance(200, 50, "um")

    assert calibration.unit_per_pixel == 0.25
    assert calibration.pixels_per_unit == 4
    assert calibration.physical_to_pixels(10) == 40


def test_calibration_rejects_invalid_distance() -> None:
    with pytest.raises(ValueError):
        Calibration.from_known_distance(0, 10)
