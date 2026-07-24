"""Video validation, thumbnails, and formatting helpers."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QPainter, QPixmap

from biopic.models.video_edit import VideoSegment
from biopic.resources import resource_path
from biopic.ui.image_canvas import ndarray_to_qimage
from biopic.utilities.video_logging import configure_video_backend_logging, quiet_cv2

configure_video_backend_logging()

try:  # pragma: no cover - depends on optional video backend
    import cv2

    quiet_cv2(cv2)
except ImportError:  # pragma: no cover
    cv2 = None


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm"}
MAX_EXTRACTED_FRAMES = 10_000


class VideoInfo:
    """Validated video metadata."""

    def __init__(self, duration_seconds: float, fps: float) -> None:
        self.duration_seconds = duration_seconds
        self.fps = fps


def validate_video(path: Path | None) -> VideoInfo:
    """Validate that a video is supported and has readable frames."""
    if cv2 is None:
        raise ValueError("OpenCV is required to validate and extract video frames.")
    if path is None:
        raise ValueError("No video is loaded.")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video format: {path.suffix}")
    if not path.exists():
        raise FileNotFoundError(path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("Unsupported or corrupted video file.")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        if duration <= 0:
            raise ValueError("The video duration could not be determined.")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError("The video opened but no readable frames were found.")
        return VideoInfo(duration, fps if fps > 0 else 25.0)
    finally:
        capture.release()


def is_video_url(url: QUrl) -> bool:
    """Return whether the URL points at a supported local video."""
    return url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in VIDEO_EXTENSIONS


def video_thumbnail(path: Path, size: QSize) -> QPixmap:
    """Return a fixed-size thumbnail for a video."""
    frame = video_preview_frame(path)
    if frame.isNull():
        frame = QPixmap(str(resource_path("icons", "biopic_logo.png")))
    return _thumbnail_canvas(frame, size)


def video_preview_frame(path: Path) -> QPixmap:
    """Return the first readable non-black video frame as a pixmap."""
    if cv2 is None:
        return QPixmap()
    capture = cv2.VideoCapture(str(path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        sample_limit = min(30, max(1, frame_count))
        for _index in range(sample_limit):
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            if float(frame.std()) < 1.0:
                continue
            rgb = frame[:, :, ::-1].copy()
            return QPixmap.fromImage(ndarray_to_qimage(rgb))
        return QPixmap()
    finally:
        capture.release()


def video_timeline_frames(
    path: Path,
    segments: list[VideoSegment] | None = None,
    count: int = 12,
) -> list[QPixmap]:
    """Return lightweight timestamp thumbnails for the video timeline."""
    if cv2 is None:
        return []
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return []
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        retained = (
            [segment for segment in segments if segment.retained and segment.duration > 0.0]
            if segments is not None
            else [VideoSegment(0.0, duration, True)]
        )
        effective_duration = sum(segment.duration for segment in retained)
        if frame_count <= 0 or fps <= 0 or effective_duration <= 0:
            return []
        sample_count = max(1, min(int(count), frame_count))
        frames: list[QPixmap] = []
        for index in range(sample_count):
            effective_time = index * effective_duration / max(1, sample_count - 1)
            source_time = _effective_to_source_time(retained, effective_time)
            position = int(round(source_time * fps))
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            rgb = frame[:, :, ::-1].copy()
            frames.append(QPixmap.fromImage(ndarray_to_qimage(rgb)))
        return frames
    finally:
        capture.release()


def _effective_to_source_time(segments: list[VideoSegment], effective_seconds: float) -> float:
    elapsed = 0.0
    for segment in segments:
        next_elapsed = elapsed + segment.duration
        if effective_seconds <= next_elapsed:
            return segment.start + (effective_seconds - elapsed)
        elapsed = next_elapsed
    return segments[-1].end if segments else 0.0


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS.mmm."""
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    whole_seconds = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000.0))
    return f"{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def safe_stem(stem: str) -> str:
    """Return a filesystem-safe filename stem."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "video"


def _thumbnail_canvas(pixmap: QPixmap, size: QSize) -> QPixmap:
    canvas = QPixmap(size)
    canvas.fill(QColor("#242424"))
    if pixmap.isNull():
        return canvas
    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    painter = QPainter(canvas)
    painter.drawPixmap(
        (size.width() - scaled.width()) // 2,
        (size.height() - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas
