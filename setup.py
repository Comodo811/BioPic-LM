"""Setuptools native extension declarations."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from setuptools import Extension, setup

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - build-system dependency should provide it
    raise RuntimeError("NumPy is required to build BioPic LM native extensions") from exc


def _windows_sdk_paths() -> tuple[list[str], list[str]]:
    sdk_root = Path("C:/Program Files (x86)/Windows Kits/10")
    include_root = sdk_root / "Include"
    lib_root = sdk_root / "Lib"
    if not include_root.exists() or not lib_root.exists():
        return [], []
    versions = sorted(
        (path for path in include_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for version in versions:
        libs = lib_root / version.name
        includes = [
            version / "ucrt",
            version / "shared",
            version / "um",
            version / "winrt",
        ]
        library_dirs = [libs / "ucrt" / "x64", libs / "um" / "x64"]
        if all(path.exists() for path in includes + library_dirs):
            return [str(path) for path in includes], [str(path) for path in library_dirs]
    return [], []


_sdk_include_dirs, _sdk_library_dirs = _windows_sdk_paths()
_include_dirs = [np.get_include(), *_sdk_include_dirs]


def _ensure_msvc_tools_on_path() -> None:
    if os.name != "nt" or shutil.which("cl.exe"):
        return
    tools_root = Path("C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC")
    if not tools_root.exists():
        return
    versions = sorted((path for path in tools_root.iterdir() if path.is_dir()), reverse=True)
    for version in versions:
        tool_dir = version / "bin" / "Hostx64" / "x64"
        if (tool_dir / "cl.exe").exists() and (tool_dir / "link.exe").exists():
            os.environ["PATH"] = str(tool_dir) + os.pathsep + os.environ.get("PATH", "")
            return


_ensure_msvc_tools_on_path()


def _native_extension(name: str, source: str) -> Extension:
    return Extension(
        name,
        sources=[source],
        include_dirs=_include_dirs,
        library_dirs=_sdk_library_dirs,
        extra_link_args=["/MANIFEST:NO"],
    )


setup(
    ext_modules=[
        _native_extension("biopic.native._stroke_native", "src/biopic/native/_stroke_native.c"),
        _native_extension(
            "biopic.native._composite_native",
            "src/biopic/native/_composite_native.c",
        ),
        _native_extension("biopic.native._display_native", "src/biopic/native/_display_native.c"),
        _native_extension(
            "biopic.native._white_balance_native",
            "src/biopic/native/_white_balance_native.c",
        ),
        _native_extension(
            "biopic.native._hue_saturation_native",
            "src/biopic/native/_hue_saturation_native.c",
        ),
        _native_extension(
            "biopic.native._adjustments_native",
            "src/biopic/native/_adjustments_native.c",
        ),
    ]
)
