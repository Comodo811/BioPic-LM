"""GPU memory planning helpers for large microscopy stacks."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True, slots=True)
class GpuMemoryPlan:
    """Estimated GPU memory plan for one stack operation."""

    full_frame_possible: bool
    free_memory_mb: int
    required_memory_mb: int
    tile_height: int
    tile_overlap: int


def plan_gpu_memory(
    images: list[np.ndarray],
    *,
    multiplier: float,
    overlap: int = 96,
    reserve_mb: int = 512,
    memory_limit_mb: int | None = 4096,
) -> GpuMemoryPlan:
    """Estimate whether a full-frame GPU pass is possible and propose tile height."""
    shapes = [np.asarray(image).shape for image in images]
    return plan_gpu_memory_from_shapes(
        shapes,
        multiplier=multiplier,
        overlap=overlap,
        reserve_mb=reserve_mb,
        memory_limit_mb=memory_limit_mb,
    )


def plan_gpu_memory_from_shapes(
    shapes: list[tuple[int, ...]],
    *,
    multiplier: float,
    overlap: int = 96,
    reserve_mb: int = 512,
    memory_limit_mb: int | None = 4096,
) -> GpuMemoryPlan:
    """Estimate GPU memory from image shapes without allocating image arrays."""
    free = _free_gpu_memory()
    stack_bytes = sum(_float32_frame_bytes_from_shape(shape) for shape in shapes)
    required = int(stack_bytes * multiplier)
    height = int(shapes[0][0]) if shapes else 0
    budget_bytes = None
    if memory_limit_mb is not None and memory_limit_mb > 0:
        budget_bytes = int(memory_limit_mb) * 1024 * 1024
    if free is None:
        effective = budget_bytes
        if effective is None:
            effective = required + reserve_mb * 1024 * 1024
        usable = max(0, effective - reserve_mb * 1024 * 1024)
        full = usable >= required
        tile_height = _tile_height_from_budget(
            stack_bytes,
            height,
            multiplier,
            usable,
            full,
        )
        return GpuMemoryPlan(
            full_frame_possible=full,
            free_memory_mb=int(effective // (1024 * 1024)),
            required_memory_mb=required // (1024 * 1024),
            tile_height=tile_height,
            tile_overlap=overlap,
        )
    effective_free = min(free, budget_bytes) if budget_bytes is not None else free
    usable = max(0, effective_free - reserve_mb * 1024 * 1024)
    full = usable >= required
    tile_height = _tile_height_from_budget(stack_bytes, height, multiplier, usable, full)
    return GpuMemoryPlan(
        full_frame_possible=full,
        free_memory_mb=int(effective_free // (1024 * 1024)),
        required_memory_mb=int(required // (1024 * 1024)),
        tile_height=tile_height,
        tile_overlap=overlap,
    )


def _free_gpu_memory() -> int | None:
    try:
        configure_cupy_cache()
        import cupy as cp

        free, _total = cp.cuda.runtime.memGetInfo()
        return int(free)
    except Exception:
        return None


def _tile_height_from_budget(
    stack_bytes: int,
    height: int,
    multiplier: float,
    usable: int,
    full: bool,
) -> int:
    if full or height <= 0:
        return height
    bytes_per_row = max(1, stack_bytes // max(1, height))
    tile_height = int(max(128, math.floor(usable / max(1.0, bytes_per_row * multiplier))))
    return min(height, max(128, tile_height))


def _float32_frame_bytes(image: np.ndarray) -> int:
    return _float32_frame_bytes_from_shape(np.asarray(image).shape)


def _float32_frame_bytes_from_shape(shape: tuple[int, ...]) -> int:
    return int(np.prod(shape) * np.dtype(np.float32).itemsize)


def configure_cupy_cache() -> None:
    """Point CuPy cache/temp paths at BioPic's writable local cache when unset."""
    base_dir = Path.cwd() / ".biopic_cache"
    temp_dir = base_dir / "cupy_temp"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    else:
        os.environ["TMP"] = str(temp_dir)
        os.environ["TEMP"] = str(temp_dir)
    if os.environ.get("CUPY_CACHE_DIR"):
        os.environ.setdefault("CUPY_CACHE_IN_MEMORY", "1")
        return
    cache_dir = base_dir / "cupy_kernel_cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    os.environ["CUPY_CACHE_DIR"] = str(cache_dir)
    os.environ.setdefault("CUPY_CACHE_IN_MEMORY", "1")
