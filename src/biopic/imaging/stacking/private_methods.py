"""Private stacking-method discovery and loading."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType


PRIVATE_METHOD_FILENAMES = {
    "custom": "custom.py",
    "custom2": "custom2.py",
}


def private_stacking_enabled() -> bool:
    """Return whether any private stack methods should be exposed."""
    value = os.environ.get("BIOPIC_ENABLE_PRIVATE_STACKING", "")
    return value.strip().lower() in {"1", "true", "yes", "on"} or any(
        private_method_available(method_name) for method_name in PRIVATE_METHOD_FILENAMES
    )


def private_method_available(method_name: str) -> bool:
    """Return whether a private method implementation can be loaded."""
    if external_private_method_path(method_name) is not None:
        return True
    return _source_method_path(method_name).is_file()


def load_private_method(method_name: str, function_name: str) -> Callable[..., object]:
    """Load a private method function from source or an external drop-in folder."""
    path = external_private_method_path(method_name)
    if path is not None:
        module = _load_module_from_path(method_name, path)
        return _method_function(module, method_name, function_name)
    try:
        module = __import__(
            f"biopic.imaging.stacking.methods.{method_name}",
            fromlist=[function_name],
        )
    except ModuleNotFoundError as package_error:
        raise ValueError(
            f"{method_name} stacking is enabled, but {PRIVATE_METHOD_FILENAMES[method_name]} "
            "is not installed in the package or a private_methods folder."
        ) from package_error
    return _method_function(module, method_name, function_name)


def _method_function(
    module: ModuleType,
    method_name: str,
    function_name: str,
) -> Callable[..., object]:
    function = getattr(module, function_name, None)
    if not callable(function):
        raise ValueError(
            f"{PRIVATE_METHOD_FILENAMES[method_name]} must define a callable {function_name}."
        )
    return function


def external_private_method_path(method_name: str) -> Path | None:
    """Return the first external drop-in path for a private method."""
    filename = PRIVATE_METHOD_FILENAMES[method_name]
    for folder in private_method_folders():
        path = folder / filename
        if path.is_file():
            return path
    return None


def private_method_folders() -> list[Path]:
    """Return folders searched for private stacking method drop-ins."""
    folders: list[Path] = []
    env_paths = os.environ.get("BIOPIC_PRIVATE_STACKING_PATH", "")
    for raw_path in env_paths.split(os.pathsep):
        if raw_path.strip():
            folders.append(Path(raw_path).expanduser())
    if getattr(sys, "frozen", False):
        folders.append(Path(sys.executable).resolve().parent / "private_methods")
    folders.append(Path.cwd() / "private_methods")
    return _deduplicate_paths(folders)


def _source_method_path(method_name: str) -> Path:
    return Path(__file__).resolve().parent / "methods" / PRIVATE_METHOD_FILENAMES[method_name]


def _load_module_from_path(method_name: str, path: Path) -> ModuleType:
    module_name = f"biopic_private_stacking_{method_name}_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load private method module from {path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _deduplicate_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
