"""Publication export preflight checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from biopic.models.figure_board import FigureBoard
from biopic.models.project import Project


class PreflightSeverity(StrEnum):
    """Preflight finding severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    """Single preflight report item."""

    severity: PreflightSeverity
    code: str
    message: str


def preflight_project(project: Project, board: FigureBoard | None = None) -> list[PreflightIssue]:
    """Run basic publication export checks."""
    issues: list[PreflightIssue] = []
    if not project.assets:
        issues.append(
            PreflightIssue(PreflightSeverity.ERROR, "missing_images", "No source images.")
        )
    for scale_bar in project.scale_bars.values():
        if scale_bar.image_node_id not in project.calibrations:
            issues.append(
                PreflightIssue(
                    PreflightSeverity.WARNING,
                    "missing_calibration",
                    f"Scale bar {scale_bar.id} references an uncalibrated image.",
                )
            )
        if scale_bar.pixel_length < 8:
            issues.append(
                PreflightIssue(
                    PreflightSeverity.WARNING,
                    "small_scale_bar",
                    f"Scale bar {scale_bar.id} is shorter than 8 pixels.",
                )
            )
    abbreviations: dict[str, str] = {}
    for definition in project.annotation_definitions.values():
        previous = abbreviations.get(definition.abbreviation)
        if previous is not None and previous != definition.full_definition:
            issues.append(
                PreflightIssue(
                    PreflightSeverity.ERROR,
                    "duplicate_abbreviation",
                    f"{definition.abbreviation} has multiple definitions.",
                )
            )
        abbreviations[definition.abbreviation] = definition.full_definition
    for annotation in project.annotations.values():
        if (
            annotation.definition_id
            and annotation.definition_id not in project.annotation_definitions
        ):
            issues.append(
                PreflightIssue(
                    PreflightSeverity.WARNING,
                    "undefined_abbreviation",
                    f"Annotation {annotation.id} references a missing definition.",
                )
            )
    if board is not None:
        if not board.panels:
            issues.append(
                PreflightIssue(
                    PreflightSeverity.ERROR, "empty_board", "Figure board has no panels."
                )
            )
        for panel in board.panels:
            if panel.source_node_id is None:
                issues.append(
                    PreflightIssue(
                        PreflightSeverity.WARNING,
                        "empty_panel",
                        f"Panel {panel.label} has no source image.",
                    )
                )
    return issues
