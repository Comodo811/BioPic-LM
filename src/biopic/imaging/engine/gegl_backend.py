"""GEGL backend detection and integration point.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import ctypes
import ctypes.util
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from biopic.imaging.engine.types import EngineStatus


@dataclass(frozen=True, slots=True)
class GeglRuntime:
    """Detected GEGL runtime state."""

    gegl_library: str | None
    babl_library: str | None
    gi_available: bool
    reason: str

    @property
    def dll_available(self) -> bool:
        """Return whether GEGL/Babl DLLs are available to native code."""
        return self.gegl_library is not None and self.babl_library is not None

    @property
    def usable_for_python_graphs(self) -> bool:
        """Return whether Python can build GEGL graphs through GI directly."""
        return self.dll_available and self.gi_available


def detect_gegl_runtime() -> GeglRuntime:
    """Detect whether GEGL/Babl and GI bindings are available."""
    _add_known_dll_directories()
    gegl_library = _find_library(
        "gegl-0.4",
        "gegl-0.4-0",
        "libgegl-0.4-0.dll",
    )
    babl_library = _find_library(
        "babl-0.1",
        "babl-0.1-0",
        "libbabl-0.1-0.dll",
    )
    gi_available = importlib.util.find_spec("gi") is not None
    missing: list[str] = []
    if gegl_library is None:
        missing.append("GEGL shared library")
    if babl_library is None:
        missing.append("Babl shared library")
    if gegl_library is not None and babl_library is not None and not gi_available:
        missing.append("PyGObject gi bindings for direct Python GEGL graphs")
    elif not gi_available:
        missing.append("PyGObject gi bindings")
    if gegl_library is not None and babl_library is not None and not gi_available:
        reason = "GEGL DLLs are available for native backends; " + ", ".join(missing)
    else:
        reason = "GEGL runtime is available" if not missing else "Missing " + ", ".join(missing)
    return GeglRuntime(
        gegl_library=gegl_library,
        babl_library=babl_library,
        gi_available=gi_available,
        reason=reason,
    )


def status_for_backend(active_backend: str, runtime: GeglRuntime) -> EngineStatus:
    """Create a stable diagnostic status object."""
    return EngineStatus(
        active_backend=active_backend,
        gegl_library=runtime.gegl_library,
        babl_library=runtime.babl_library,
        gi_available=runtime.gi_available,
        gegl_reason=runtime.reason,
    )


def _add_known_dll_directories() -> None:
    """Register common GEGL DLL directories for python.org Python on Windows."""
    _seed_gegl_environment()
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    for directory in _candidate_dll_directories():
        if directory.is_dir():
            try:
                os.add_dll_directory(str(directory))
            except OSError:
                continue


def _find_library(*names: str) -> str | None:
    """Find a shared library through system lookup and common MSYS2 paths."""
    for name in names:
        found = ctypes.util.find_library(name)
        if found:
            return found
    for directory in _candidate_dll_directories():
        for name in names:
            candidate = directory / name
            if _loadable(candidate):
                return str(candidate)
    return None


def _candidate_dll_directories() -> list[Path]:
    """Return likely DLL directories, including MSYS2 UCRT64."""
    seen: set[Path] = set()
    directories: list[Path] = []
    raw_dirs = [
        os.environ.get("MSYSTEM_PREFIX"),
        r"C:\msys64\ucrt64",
        r"C:\msys64\mingw64",
        r"C:\msys64\clang64",
    ]
    raw_dirs.extend(os.environ.get("PATH", "").split(os.pathsep))
    for raw in raw_dirs:
        if not raw:
            continue
        path = Path(raw)
        if path.name.lower() != "bin":
            path = path / "bin"
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in seen:
            seen.add(resolved)
            directories.append(resolved)
        module_dir = resolved.parent / "lib" / "gegl-0.4"
        if module_dir not in seen:
            seen.add(module_dir)
            directories.append(module_dir)
    return directories


def _loadable(candidate: Path) -> bool:
    """Return whether a candidate DLL exists and can be loaded."""
    if not candidate.is_file():
        return False
    try:
        ctypes.CDLL(str(candidate))
    except OSError:
        return False
    return True


def _seed_gegl_environment() -> None:
    """Set conservative defaults for MSYS2 GEGL when launched by Windows Python."""
    prefix = Path(os.environ.get("MSYSTEM_PREFIX", r"C:\msys64\ucrt64"))
    bin_dir = prefix / "bin"
    module_dir = prefix / "lib" / "gegl-0.4"
    if bin_dir.is_dir():
        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(os.pathsep) if current_path else []
        if str(bin_dir) not in path_parts:
            os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
    if module_dir.is_dir() and not os.environ.get("GEGL_PATH"):
        os.environ["GEGL_PATH"] = str(module_dir)
    if not os.environ.get("GEGL_SWAP"):
        os.environ["GEGL_SWAP"] = "RAM"
