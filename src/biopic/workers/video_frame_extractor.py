"""Qt worker for extracting stack frames from video."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread, Signal

from biopic.models.video_edit import VideoSegment, frame_timestamps
from biopic.utilities.video_logging import configure_video_backend_logging, quiet_cv2

configure_video_backend_logging()

try:  # pragma: no cover - depends on optional video backend
    import cv2

    quiet_cv2(cv2)
except ImportError:  # pragma: no cover
    cv2 = None


@dataclass(frozen=True, slots=True)
class VideoExtractionJob:
    """Frame extraction request."""

    video_path: Path
    output_dir: Path
    interval_seconds: float
    retained_segments: list[VideoSegment]
    base_name: str


class VideoFrameExtractor(QThread):
    """Extract video frames off the GUI thread with bounded memory."""

    progressChanged = Signal(str, float)
    extractionFinished = Signal(object)
    extractionFailed = Signal(str)

    def __init__(self, job: VideoExtractionJob) -> None:
        super().__init__()
        self.job = job
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        created: list[tuple[Path, float]] = []
        try:
            if cv2 is None:
                raise ValueError("OpenCV is required for video frame extraction.")
            timestamps = frame_timestamps(self.job.retained_segments, self.job.interval_seconds)
            if not timestamps:
                raise ValueError("No frames would be extracted from the retained video sections.")
            self.job.output_dir.mkdir(parents=True, exist_ok=True)
            capture = cv2.VideoCapture(str(self.job.video_path))
            if not capture.isOpened():
                raise ValueError("The video could not be opened for frame extraction.")
            try:
                total = len(timestamps)
                for index, timestamp in enumerate(timestamps, start=1):
                    if self._cancel_requested:
                        raise _VideoExtractionCancelled
                    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        raise ValueError(f"Could not read frame at {timestamp:.3f} seconds.")
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    filename = (
                        f"{self.job.base_name}_frame_{index:06d}_t_{timestamp:010.3f}.png"
                    )
                    path = self.job.output_dir / filename
                    Image.fromarray(rgb).save(path, format="PNG")
                    created.append((path, timestamp))
                    self.progressChanged.emit(
                        f"Extracted {index} of {total} frames",
                        index / total,
                    )
            finally:
                capture.release()
        except _VideoExtractionCancelled:
            shutil.rmtree(self.job.output_dir, ignore_errors=True)
            self.extractionFailed.emit("Frame extraction cancelled.")
            return
        except Exception as exc:  # noqa: BLE001 - worker boundary
            shutil.rmtree(self.job.output_dir, ignore_errors=True)
            self.extractionFailed.emit(str(exc))
            return
        self.extractionFinished.emit(created)


class _VideoExtractionCancelled(Exception):
    """Internal cancellation sentinel."""
