"""Qt worker for sharpness comparison."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from biopic.imaging.io import load_asset_pixels
from biopic.imaging.stacking import FocusStackParameters
from biopic.models.image_asset import ImageAsset
from biopic.sharpness_comparison.comparison_runner import run_comparison
from biopic.sharpness_comparison.config_models import SharpnessComparisonConfig


@dataclass(frozen=True, slots=True)
class SharpnessComparisonJob:
    assets: list[ImageAsset]
    base_parameters: FocusStackParameters
    config: SharpnessComparisonConfig
    project_id: str
    stack_name: str


class SharpnessComparisonWorker(QThread):
    """Run sharpness comparison off the GUI thread."""

    progressChanged = Signal(str, float)
    comparisonFinished = Signal(object)
    comparisonFailed = Signal(str)

    def __init__(self, job: SharpnessComparisonJob) -> None:
        super().__init__()
        self.job = job
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            images = [load_asset_pixels(asset) for asset in self.job.assets]
            summary = run_comparison(
                images=images,
                base_parameters=self.job.base_parameters,
                config=self.job.config,
                project_id=self.job.project_id,
                stack_name=self.job.stack_name,
                progress=self.progressChanged.emit,
                cancelled=lambda: self._cancel_requested,
            )
        except Exception as exc:  # noqa: BLE001
            self.comparisonFailed.emit(str(exc))
            return
        self.comparisonFinished.emit(summary)
