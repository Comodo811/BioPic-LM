"""Qt worker for image stitching."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QThread, Signal

from biopic.imaging.io import load_asset_pixels
from biopic.models.image_asset import ImageAsset
from biopic.utilities.video_logging import configure_video_backend_logging, quiet_cv2

configure_video_backend_logging()

try:  # pragma: no cover - optional backend availability is environment-specific
    import cv2

    quiet_cv2(cv2)
except ImportError:  # pragma: no cover
    cv2 = None


@dataclass(frozen=True, slots=True)
class ImageStitchJob:
    """Input assets for stitching in explicit order."""

    assets: list[ImageAsset]


@dataclass(frozen=True, slots=True)
class StitchResult:
    """Completed stitch output."""

    pixels: np.ndarray
    metadata: dict[str, object]


class ImageStitchWorker(QThread):
    """Run OpenCV panorama stitching off the UI thread."""

    progressChanged = Signal(str, float)
    stitchFinished = Signal(object)
    stitchFailed = Signal(str)

    def __init__(self, job: ImageStitchJob) -> None:
        super().__init__()
        self.job = job
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            if cv2 is None:
                raise ValueError("OpenCV is required for image stitching.")
            if len(self.job.assets) < 2:
                raise ValueError("Select at least two images to stitch.")
            self.progressChanged.emit("Loading images", 0.05)
            images: list[np.ndarray] = []
            for index, asset in enumerate(self.job.assets):
                if self._cancel_requested:
                    self.stitchFailed.emit("Stitching cancelled.")
                    return
                pixels = load_asset_pixels(asset)
                if pixels.ndim == 2:
                    pixels = np.repeat(pixels[..., None], 3, axis=2)
                if pixels.ndim != 3 or pixels.shape[-1] < 3:
                    raise ValueError(f"Unsupported color format for {asset.filename}.")
                images.append(_to_bgr_u8(pixels[..., :3]))
                self.progressChanged.emit(
                    f"Loaded {index + 1} of {len(self.job.assets)} images",
                    0.05 + 0.20 * ((index + 1) / len(self.job.assets)),
                )
            if self._cancel_requested:
                self.stitchFailed.emit("Stitching cancelled.")
                return
            self.progressChanged.emit("Detecting and matching image features", 0.35)
            stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
            status, panorama = stitcher.stitch(images)
            if self._cancel_requested:
                self.stitchFailed.emit("Stitching cancelled.")
                return
            if status != cv2.Stitcher_OK or panorama is None:
                raise ValueError(_stitch_status_message(int(status), self.job.assets))
            output = cv2.cvtColor(panorama, cv2.COLOR_BGR2RGB)
            metadata = {
                "source_image_ids": [asset.id for asset in self.job.assets],
                "source_filenames": [asset.filename for asset in self.job.assets],
                "stitching_order": list(range(1, len(self.job.assets) + 1)),
                "algorithm": "OpenCV Stitcher PANORAMA",
                "output_dimensions": [int(output.shape[1]), int(output.shape[0])],
            }
        except MemoryError:
            self.stitchFailed.emit("Stitching failed: not enough memory for the output image.")
            return
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.stitchFailed.emit(str(exc))
            return
        self.progressChanged.emit("Stitch complete", 1.0)
        self.stitchFinished.emit(StitchResult(output, metadata))


def _to_bgr_u8(pixels: np.ndarray) -> np.ndarray:
    array = np.asarray(pixels)
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        scaled = (array.astype(np.float32) - float(info.min)) / max(
            1.0, float(info.max - info.min)
        )
    else:
        scaled = np.clip(array.astype(np.float32, copy=False), 0.0, 1.0)
    rgb = np.clip(scaled * 255.0, 0.0, 255.0).astype(np.uint8)
    assert cv2 is not None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _stitch_status_message(status: int, assets: list[ImageAsset]) -> str:
    names = ", ".join(asset.filename for asset in assets)
    messages = {
        1: "Need more matching images or overlapping features.",
        2: "Homography estimation failed; image overlap may be insufficient.",
        3: "Camera parameter adjustment failed; the images may not form one panorama.",
    }
    detail = messages.get(status, f"OpenCV stitcher status {status}.")
    return f"Image stitching failed: {detail} Images: {names}"
