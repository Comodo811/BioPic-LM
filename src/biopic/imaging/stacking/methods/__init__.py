"""Focus-stacking method entry points."""

from __future__ import annotations

from biopic.imaging.stacking.methods.depth_map import stack_depth_map
from biopic.imaging.stacking.methods.pyramid import stack_pyramid_max_contrast


def stack_custom(*args: object, **kwargs: object) -> object:
    """Load the private Custom implementation on demand."""
    from biopic.imaging.stacking.private_methods import (
        load_private_method,
        private_method_available,
    )

    if not private_method_available("custom"):
        raise ValueError("Custom stacking is private and is disabled in this build.")
    _stack_custom = load_private_method("custom", "stack_custom")

    return _stack_custom(*args, **kwargs)


def stack_custom2(*args: object, **kwargs: object) -> object:
    """Load the private Custom2 implementation on demand."""
    from biopic.imaging.stacking.private_methods import (
        load_private_method,
        private_method_available,
    )

    if not private_method_available("custom2"):
        raise ValueError("Custom2 stacking is private and is disabled in this build.")
    _stack_custom2 = load_private_method("custom2", "stack_custom2")

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
