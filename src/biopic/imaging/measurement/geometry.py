"""Measurement geometry and CSV export helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from biopic.models.measurement import Measurement


def measurement_rows(measurements: list[Measurement]) -> list[dict[str, object]]:
    """Return tabular measurement rows."""
    rows: list[dict[str, object]] = []
    for measurement in measurements:
        rows.append(
            {
                "id": measurement.id,
                "label": measurement.label,
                "kind": measurement.kind.value,
                "image_node_id": measurement.image_node_id,
                "length_pixels": measurement.length_pixels(),
                "length": measurement.length_physical(),
                "area_pixels": measurement.area_pixels(),
                "area": measurement.area_physical(),
                "unit": measurement.calibration.unit,
            }
        )
    return rows


def export_measurements_csv(measurements: list[Measurement], path: Path) -> None:
    """Export measurements to CSV."""
    rows = measurement_rows(measurements)
    fieldnames = [
        "id",
        "label",
        "kind",
        "image_node_id",
        "length_pixels",
        "length",
        "area_pixels",
        "area",
        "unit",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
