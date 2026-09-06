"""Measurement geometry and CSV export helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from biopic.models.measurement import Measurement


def measurement_rows(measurements: list[Measurement]) -> list[dict[str, object]]:
    """Return tabular measurement rows."""
    rows: list[dict[str, object]] = []
    for measurement in measurements:
        length_unit = measurement.display_unit
        area_unit = measurement.area_display_unit
        rows.append(
            {
                "id": measurement.id,
                "label": measurement.label,
                "kind": measurement.kind.value,
                "image_node_id": measurement.image_node_id,
                "length": measurement.length_display(length_unit)
                if measurement.length_pixels() > 0
                else "",
                "length_unit": length_unit,
                "area": measurement.area_display(area_unit)
                if measurement.area_pixels() > 0
                else "",
                "area_unit": area_unit,
                "label_alignment": measurement.label_alignment.value,
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
        "length",
        "length_unit",
        "area",
        "area_unit",
        "label_alignment",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
