"""Focus-stacking method entry points."""

from __future__ import annotations

from biopic.imaging.stacking.methods.depth_map import stack_depth_map
from biopic.imaging.stacking.methods.pyramid import stack_pyramid_max_contrast


def stack_custom(*args: object, **kwargs: object) -> object:
    """Load the private Custom implementation on demand."""
    from biopic.imaging.stacking.private_methods import private_stacking_enabled

    if not private_stacking_enabled():
        raise ValueError("Custom stacking is private and is disabled in this build.")
    try:
        from biopic.imaging.stacking.methods.custom import stack_custom as _stack_custom
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Custom stacking is enabled, but the private Custom module is not installed."
        ) from exc

    return _stack_custom(*args, **kwargs)


def stack_custom2(*args: object, **kwargs: object) -> object:
    """Load the private Custom2 implementation on demand."""
    from biopic.imaging.stacking.private_methods import private_stacking_enabled

    if not private_stacking_enabled():
        raise ValueError("Custom2 stacking is private and is disabled in this build.")
    try:
        from biopic.imaging.stacking.methods.custom2 import stack_custom2 as _stack_custom2
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Custom2 stacking is enabled, but the private Custom2 module is not installed."
        ) from exc

    return _stack_custom2(*args, **kwargs)


METHOD_RUNNERS = {
    "depth_map": stack_depth_map,
    "pyramid_max_contrast": stack_pyramid_max_contrast,
    "custom": stack_custom,
    "custom2": stack_custom2,
}

__all__ = [
    "METHOD_RUNNERS",
    "stack_custom",
    "stack_custom2",
    "stack_depth_map",
    "stack_pyramid_max_contrast",
]
