"""Debug artifact writer for focus stacking."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time

import cv2
import numpy as np
import tifffile


class _StackDebugWriter:
    """Write full-resolution Custom stack stages for visual/pixel debugging."""

    def __init__(self, enabled: bool, method_name: str = "custom") -> None:
        self.enabled = enabled
        self.directory: Path | None = None
        self._last_stack_stage: tuple[str, np.ndarray] | None = None
        self._report_lines: list[str] = []
        if not enabled:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        use_this = Path.cwd() / "tmp_image" / "use_this"
        root = (
            use_this / "biopic_stack_debug"
            if use_this.is_dir()
            else Path(tempfile.gettempdir()) / "biopic_stack_debug"
        )
        self.directory = root / f"{method_name}-{stamp}-{time.time_ns() % 1_000_000:06d}"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._report_lines.append(f"debug_dir={self.directory}")

    def save(self, name: str, image: np.ndarray, *, stack_stage: bool = False) -> None:
        if not self.enabled or self.directory is None:
            return
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        path = self.directory / f"{safe_name}.tif"
        pixels = _debug_uint8_image(image)
        tifffile.imwrite(path, pixels, photometric="rgb" if pixels.ndim == 3 else "minisblack")
        stats = _debug_image_stats(np.asarray(image, dtype=np.float32))
        self._report_lines.append(f"{safe_name}: {stats}")
        if stack_stage:
            self._last_stack_stage = (safe_name, np.asarray(image, dtype=np.float32).copy())

    def compare_final(self, final_image: np.ndarray) -> None:
        if not self.enabled or self.directory is None:
            return
        if self._last_stack_stage is None:
            self._report_lines.append("comparison: no progressive stack stage was saved")
        else:
            name, last = self._last_stack_stage
            final = np.asarray(final_image, dtype=np.float32)
            self._report_lines.append(
                f"comparison {name} -> final: {_debug_image_delta(last, final)}"
            )
        (self.directory / "stage_report.txt").write_text(
            "\n".join(self._report_lines) + "\n",
            encoding="utf-8",
        )


def _debug_uint8_image(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if np.issubdtype(array.dtype, np.integer):
        if array.dtype == np.uint8:
            return array
        info = np.iinfo(array.dtype)
        return np.rint(
            np.clip(array.astype(np.float32) / max(float(info.max), 1.0), 0.0, 1.0)
            * 255.0
        ).astype(np.uint8)
    return np.rint(np.clip(array.astype(np.float32), 0.0, 1.0) * 255.0).astype(np.uint8)


def _debug_image_stats(image: np.ndarray) -> str:
    array = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    mean = float(np.mean(array))
    std = float(np.std(array))
    min_value = float(np.min(array))
    max_value = float(np.max(array))
    if array.ndim == 3 and array.shape[-1] >= 3:
        hsv = cv2.cvtColor(array[..., :3], cv2.COLOR_RGB2HSV)
        saturation = float(np.mean(hsv[..., 1]))
    else:
        saturation = 0.0
    return (
        f"mean={mean:.6f} std={std:.6f} min={min_value:.6f} "
        f"max={max_value:.6f} saturation={saturation:.6f}"
    )


def _debug_image_delta(before: np.ndarray, after: np.ndarray) -> str:
    a = np.clip(np.asarray(before, dtype=np.float32), 0.0, 1.0)
    b = np.clip(np.asarray(after, dtype=np.float32), 0.0, 1.0)
    if a.shape != b.shape:
        return f"shape_changed before={a.shape} after={b.shape}"
    diff = b - a
    return (
        f"mean_delta={float(np.mean(diff)):.6f} "
        f"mad={float(np.mean(np.abs(diff))):.6f} "
        f"rmse={float(np.sqrt(np.mean(diff * diff))):.6f} "
        f"max_abs={float(np.max(np.abs(diff))):.6f}; "
        f"before=({_debug_image_stats(a)}); after=({_debug_image_stats(b)})"
    )
