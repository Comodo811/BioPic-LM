# Stacking Method Modules

Each stacking method should expose one small entry point that accepts already
loaded, oriented and aligned float images plus `FocusStackParameters`.

Current entry points:

- `depth_map.stack_depth_map(images, parameters)`
- `pyramid.stack_pyramid_max_contrast(images, parameters)`
- `custom.stack_custom(images, parameters, progress, preview)`

Register new methods in `methods/__init__.py` and route them from
`stacker.focus_stack`. Method functions should return the internal stack result
shape used by `stacker._PyramidStack`, or an object with the same attributes:
`image`, `depth_map`, `focus_map` and `weights`.
