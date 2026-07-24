"""Qt worker for focus stacking."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from biopic.imaging.io import load_asset_pixels
from biopic.imaging.stacking import FocusStackParameters, FocusStackResult, focus_stack
from biopic.models.image_asset import ImageAsset


@dataclass(frozen=True, slots=True)
class FocusStackJob:
    """Inputs for a focus-stack worker."""

    assets: list[ImageAsset]
    parameters: FocusStackParameters


class FocusStackWorker(QThread):
    """Run focus stacking off the GUI thread."""

    progressChanged = Signal(str, float)
    stackFinished = Signal(object)
    stackFailed = Signal(str)

    def __init__(self, job: FocusStackJob) -> None:
        super().__init__()
        self.job = job
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cancellation before the next major processing stage."""
        self._cancel_requested = True

    def run(self) -> None:
        """Load stack images and compute the focus-stacked result."""
        try:
            if self._cancel_requested:
                self.stackFailed.emit("Stacking cancelled.")
                return
            self.progressChanged.emit("Loading images", 0.0)
            images = [load_asset_pixels(asset) for asset in self.job.assets]
            if self._cancel_requested:
                self.stackFailed.emit("Stacking cancelled.")
                return
            result: FocusStackResult = focus_stack(
                images, self.job.parameters, progress=self.progressChanged.emit
            )
        except Exception as exc:  # noqa: BLE001 - convert worker failures to UI signal
            self.stackFailed.emit(str(exc))
            return
        self.stackFinished.emit(result)
