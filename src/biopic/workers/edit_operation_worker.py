"""Worker for expensive edit preview operations."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, Signal

from biopic.imaging.editing import apply_edit_operation


class EditOperationWorker(QObject):
    """Run expensive preview operations away from the GUI event path."""

    resultReady = Signal(int, object)
    finished = Signal()

    def __init__(
        self,
        token: int,
        image: np.ndarray,
        operation: str,
        parameters: dict[str, object],
    ) -> None:
        super().__init__()
        self._token = token
        self._image = image
        self._operation = operation
        self._parameters = parameters

    def run(self) -> None:
        try:
            result = apply_edit_operation(self._image, self._operation, self._parameters)
        except Exception as exc:  # pragma: no cover - surfaced in the UI
            result = exc
        self.resultReady.emit(self._token, result)
        self.finished.emit()
