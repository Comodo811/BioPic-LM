"""Dialogs for Stack from Video."""

from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from biopic.models.video_edit import VideoSegment, frame_timestamps
from biopic.ui.workspaces.stack_from_video_media import MAX_EXTRACTED_FRAMES, format_time


class FrameExtractionDialog(QDialog):
    """Dialog for choosing extraction interval."""

    def __init__(
        self,
        retained_segments: list[VideoSegment],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._segments = retained_segments
        self.setWindowTitle("Create Stack from Video")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.value = QDoubleSpinBox()
        self.value.setRange(0.001, 3600.0)
        self.value.setValue(0.5)
        self.value.setDecimals(3)
        self.unit = QComboBox()
        self.unit.addItem("Seconds between frames", "seconds")
        self.unit.addItem("Milliseconds between frames", "milliseconds")
        self.unit.addItem("Frames per second", "fps")
        form.addRow("Interval", self.value)
        form.addRow("Unit", self.unit)
        layout.addLayout(form)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.value.valueChanged.connect(lambda _value: self._update_summary())
        self.unit.currentIndexChanged.connect(lambda _index: self._update_summary())
        self._update_summary()

    def interval_seconds(self) -> float:
        unit = str(self.unit.currentData())
        value = float(self.value.value())
        if unit == "milliseconds":
            return value / 1000.0
        if unit == "fps":
            return 1.0 / value
        return value

    def _accept_if_valid(self) -> None:
        interval = self.interval_seconds()
        if not math.isfinite(interval) or interval <= 0:
            QMessageBox.warning(self, "Create Stack from Video", "Enter a positive interval.")
            return
        count = len(frame_timestamps(self._segments, interval))
        if count <= 0:
            QMessageBox.warning(self, "Create Stack from Video", "No frames would be extracted.")
            return
        if count > MAX_EXTRACTED_FRAMES:
            QMessageBox.warning(
                self,
                "Create Stack from Video",
                f"This would create {count} frames. Increase the interval.",
            )
            return
        self.accept()

    def _update_summary(self) -> None:
        interval = self.interval_seconds()
        retained_duration = sum(segment.duration for segment in self._segments)
        count = len(frame_timestamps(self._segments, interval)) if interval > 0 else 0
        self.summary.setText(
            f"Effective duration after cuts: {format_time(retained_duration)}\n"
            f"Extraction interval: {interval:.3f} s\n"
            f"Estimated output images: {count}"
        )
