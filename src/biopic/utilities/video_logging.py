"""Quiet verbose video backend diagnostics."""

from __future__ import annotations

import os


def configure_video_backend_logging() -> None:
    """Suppress noisy Qt Multimedia/OpenCV FFmpeg decoder diagnostics."""
    _append_qt_logging_rule("qt.multimedia.ffmpeg=false")
    _append_qt_logging_rule("qt.multimedia.ffmpeg.*=false")
    os.environ["QT_FFMPEG_DEBUG"] = "0"
    os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
    os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")


def quiet_cv2(cv2_module: object) -> None:
    """Set OpenCV's runtime logger to silent where the binding exposes it."""
    try:
        cv2_module.setLogLevel(0)
    except AttributeError:
        return


def _append_qt_logging_rule(rule: str) -> None:
    current = os.environ.get("QT_LOGGING_RULES", "")
    if rule in current:
        return
    os.environ["QT_LOGGING_RULES"] = f"{current};{rule}" if current else rule
