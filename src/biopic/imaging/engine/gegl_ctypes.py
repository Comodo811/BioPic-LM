"""ctypes bridge for the GEGL C buffer API.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

import numpy as np

from biopic.imaging.engine.gegl_backend import _find_library, detect_gegl_runtime

GEGL_AUTO_ROWSTRIDE = 0
GEGL_ABYSS_NONE = 0


class GeglRectangle(ctypes.Structure):
    """ctypes representation of GeglRectangle."""

    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
    ]


@dataclass(frozen=True, slots=True)
class GeglArrayFormat:
    """Mapping between NumPy arrays and Babl pixel formats."""

    name: bytes
    channels: int
    dtype: np.dtype


class GeglCtypesError(RuntimeError):
    """Raised when the native GEGL bridge cannot complete an operation."""


class GeglCtypesBridge:
    """Minimal GEGL C bridge for tiled buffer input/output."""

    def __init__(self) -> None:
        runtime = detect_gegl_runtime()
        if not runtime.dll_available:
            raise GeglCtypesError(runtime.reason)
        gobject_library = _find_library("gobject-2.0-0", "libgobject-2.0-0.dll")
        if gobject_library is None:
            raise GeglCtypesError("Missing GObject shared library")
        self._babl = ctypes.CDLL(str(runtime.babl_library))
        self._gobject = ctypes.CDLL(str(gobject_library))
        self._gegl = ctypes.CDLL(str(runtime.gegl_library))
        self._configure_functions()
        self._gegl.gegl_init(None, None)

    def ndarray_to_buffer(self, pixels: np.ndarray) -> ctypes.c_void_p:
        """Create a GeglBuffer containing a copy of a NumPy image."""
        array = _contiguous_supported_array(pixels)
        fmt = _format_for_array(array)
        rect = GeglRectangle(0, 0, int(array.shape[1]), int(array.shape[0]))
        babl_format = self._babl.babl_format(fmt.name)
        if not babl_format:
            raise GeglCtypesError(f"Unsupported Babl format: {fmt.name.decode('ascii')}")
        buffer = self._gegl.gegl_buffer_new(ctypes.byref(rect), babl_format)
        if not buffer:
            raise GeglCtypesError("gegl_buffer_new returned NULL")
        self._gegl.gegl_buffer_set(
            buffer,
            ctypes.byref(rect),
            0,
            babl_format,
            ctypes.c_void_p(array.ctypes.data),
            GEGL_AUTO_ROWSTRIDE,
        )
        return ctypes.c_void_p(buffer)

    def buffer_to_ndarray(
        self,
        buffer: ctypes.c_void_p,
        *,
        width: int,
        height: int,
        channels: int,
        dtype: np.dtype | type[np.generic],
        x: int = 0,
        y: int = 0,
    ) -> np.ndarray:
        """Read a rectangular GeglBuffer region into a NumPy array."""
        np_dtype = np.dtype(dtype)
        shape = (height, width) if channels == 1 else (height, width, channels)
        output = np.empty(shape, dtype=np_dtype)
        fmt = _format_for_shape_dtype(channels, np_dtype)
        babl_format = self._babl.babl_format(fmt.name)
        if not babl_format:
            raise GeglCtypesError(f"Unsupported Babl format: {fmt.name.decode('ascii')}")
        rect = GeglRectangle(int(x), int(y), int(width), int(height))
        self._gegl.gegl_buffer_get(
            buffer,
            ctypes.byref(rect),
            ctypes.c_double(1.0),
            babl_format,
            ctypes.c_void_p(output.ctypes.data),
            GEGL_AUTO_ROWSTRIDE,
            GEGL_ABYSS_NONE,
        )
        return output

    def blit_buffer_source(
        self,
        buffer: ctypes.c_void_p,
        *,
        width: int,
        height: int,
        channels: int,
        dtype: np.dtype | type[np.generic],
        x: int = 0,
        y: int = 0,
    ) -> np.ndarray:
        """Render a `gegl:buffer-source` node through GEGL's graph executor."""
        np_dtype = np.dtype(dtype)
        fmt = _format_for_shape_dtype(channels, np_dtype)
        babl_format = self._babl.babl_format(fmt.name)
        if not babl_format:
            raise GeglCtypesError(f"Unsupported Babl format: {fmt.name.decode('ascii')}")
        graph = self._gegl.gegl_node_new()
        if not graph:
            raise GeglCtypesError("gegl_node_new returned NULL")
        source = None
        try:
            source = self._gegl.gegl_node_new_child(
                graph,
                b"operation",
                b"gegl:buffer-source",
                b"buffer",
                buffer,
                ctypes.c_void_p(),
            )
            if not source:
                raise GeglCtypesError("gegl_node_new_child(buffer-source) returned NULL")
            shape = (height, width) if channels == 1 else (height, width, channels)
            output = np.empty(shape, dtype=np_dtype)
            rect = GeglRectangle(int(x), int(y), int(width), int(height))
            self._gegl.gegl_node_blit(
                source,
                ctypes.c_double(1.0),
                ctypes.byref(rect),
                babl_format,
                ctypes.c_void_p(output.ctypes.data),
                GEGL_AUTO_ROWSTRIDE,
                0,
            )
            return output
        finally:
            self.unref(ctypes.c_void_p(graph))

    def composite_over_rgba(
        self,
        background: np.ndarray,
        foreground: np.ndarray,
    ) -> np.ndarray:
        """Composite two RGBA arrays with GEGL's `gegl:over` operation."""
        bg = _ensure_rgba_u8(background, "background")
        fg = _ensure_rgba_u8(foreground, "foreground")
        if bg.shape != fg.shape:
            raise GeglCtypesError("GEGL over composite expects equal-sized RGBA arrays")
        bg_buffer = self.ndarray_to_buffer(bg)
        fg_buffer = self.ndarray_to_buffer(fg)
        graph = self._gegl.gegl_node_new()
        if not graph:
            self.unref(bg_buffer)
            self.unref(fg_buffer)
            raise GeglCtypesError("gegl_node_new returned NULL")
        try:
            bg_node = self._new_buffer_source_node(graph, bg_buffer)
            fg_node = self._new_buffer_source_node(graph, fg_buffer)
            over_node = self._gegl.gegl_node_new_child(
                graph,
                b"operation",
                b"gegl:over",
                ctypes.c_void_p(),
            )
            if not over_node:
                raise GeglCtypesError("gegl_node_new_child(over) returned NULL")
            if not self._gegl.gegl_node_connect_to(bg_node, b"output", over_node, b"input"):
                raise GeglCtypesError("Failed to connect background to over input")
            if not self._gegl.gegl_node_connect_to(fg_node, b"output", over_node, b"aux"):
                raise GeglCtypesError("Failed to connect foreground to over aux")
            output = np.empty_like(bg)
            rect = GeglRectangle(0, 0, int(bg.shape[1]), int(bg.shape[0]))
            babl_format = self._babl.babl_format(b"RGBA u8")
            self._gegl.gegl_node_blit(
                over_node,
                ctypes.c_double(1.0),
                ctypes.byref(rect),
                babl_format,
                ctypes.c_void_p(output.ctypes.data),
                GEGL_AUTO_ROWSTRIDE,
                0,
            )
            return output
        finally:
            self.unref(ctypes.c_void_p(graph))
            self.unref(bg_buffer)
            self.unref(fg_buffer)

    def _new_buffer_source_node(
        self,
        graph: ctypes.c_void_p,
        buffer: ctypes.c_void_p,
    ) -> ctypes.c_void_p:
        source = self._gegl.gegl_node_new_child(
            graph,
            b"operation",
            b"gegl:buffer-source",
            b"buffer",
            buffer,
            ctypes.c_void_p(),
        )
        if not source:
            raise GeglCtypesError("gegl_node_new_child(buffer-source) returned NULL")
        return ctypes.c_void_p(source)

    def write_region(
        self,
        buffer: ctypes.c_void_p,
        pixels: np.ndarray,
        *,
        x: int = 0,
        y: int = 0,
    ) -> None:
        """Write a NumPy image region into an existing GeglBuffer."""
        array = _contiguous_supported_array(pixels)
        fmt = _format_for_array(array)
        rect = GeglRectangle(int(x), int(y), int(array.shape[1]), int(array.shape[0]))
        babl_format = self._babl.babl_format(fmt.name)
        if not babl_format:
            raise GeglCtypesError(f"Unsupported Babl format: {fmt.name.decode('ascii')}")
        self._gegl.gegl_buffer_set(
            buffer,
            ctypes.byref(rect),
            0,
            babl_format,
            ctypes.c_void_p(array.ctypes.data),
            GEGL_AUTO_ROWSTRIDE,
        )

    def roundtrip_array(self, pixels: np.ndarray) -> np.ndarray:
        """Write pixels through GeglBuffer and read them back."""
        array = _contiguous_supported_array(pixels)
        channels = 1 if array.ndim == 2 else int(array.shape[2])
        buffer = self.ndarray_to_buffer(array)
        try:
            return self.buffer_to_ndarray(
                buffer,
                width=int(array.shape[1]),
                height=int(array.shape[0]),
                channels=channels,
                dtype=array.dtype,
            )
        finally:
            self.unref(buffer)

    def unref(self, pointer: ctypes.c_void_p) -> None:
        """Release a GObject pointer returned by GEGL."""
        if pointer:
            self._gobject.g_object_unref(pointer)

    def _configure_functions(self) -> None:
        self._babl.babl_format.argtypes = [ctypes.c_char_p]
        self._babl.babl_format.restype = ctypes.c_void_p
        self._gegl.gegl_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._gegl.gegl_init.restype = None
        self._gegl.gegl_node_new.argtypes = []
        self._gegl.gegl_node_new.restype = ctypes.c_void_p
        self._gegl.gegl_node_new_child.argtypes = [ctypes.c_void_p]
        self._gegl.gegl_node_new_child.restype = ctypes.c_void_p
        self._gegl.gegl_node_connect_to.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.c_char_p,
        ]
        self._gegl.gegl_node_connect_to.restype = ctypes.c_int
        self._gegl.gegl_node_blit.argtypes = [
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.POINTER(GeglRectangle),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._gegl.gegl_node_blit.restype = None
        self._gegl.gegl_buffer_new.argtypes = [ctypes.POINTER(GeglRectangle), ctypes.c_void_p]
        self._gegl.gegl_buffer_new.restype = ctypes.c_void_p
        self._gegl.gegl_buffer_set.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(GeglRectangle),
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        self._gegl.gegl_buffer_set.restype = None
        self._gegl.gegl_buffer_get.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(GeglRectangle),
            ctypes.c_double,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._gegl.gegl_buffer_get.restype = None
        self._gobject.g_object_unref.argtypes = [ctypes.c_void_p]
        self._gobject.g_object_unref.restype = None


def _contiguous_supported_array(pixels: np.ndarray) -> np.ndarray:
    array = np.asarray(pixels)
    if array.ndim not in {2, 3}:
        raise GeglCtypesError("GEGL bridge expects a 2D or 3D image array")
    if array.ndim == 3 and array.shape[2] not in {3, 4}:
        raise GeglCtypesError("GEGL bridge supports RGB and RGBA arrays")
    _format_for_array(array)
    return np.ascontiguousarray(array)


def _format_for_array(array: np.ndarray) -> GeglArrayFormat:
    channels = 1 if array.ndim == 2 else int(array.shape[2])
    return _format_for_shape_dtype(channels, array.dtype)


def _format_for_shape_dtype(
    channels: int,
    dtype: np.dtype | type[np.generic],
) -> GeglArrayFormat:
    np_dtype = np.dtype(dtype)
    if np_dtype == np.dtype(np.uint8):
        suffix = "u8"
    elif np_dtype == np.dtype(np.uint16):
        suffix = "u16"
    elif np_dtype == np.dtype(np.float32):
        suffix = "float"
    else:
        raise GeglCtypesError(f"Unsupported GEGL bridge dtype: {np_dtype}")
    if channels == 1:
        prefix = "Y"
    elif channels == 3:
        prefix = "RGB"
    elif channels == 4:
        prefix = "RGBA"
    else:
        raise GeglCtypesError(f"Unsupported GEGL bridge channel count: {channels}")
    return GeglArrayFormat(f"{prefix} {suffix}".encode("ascii"), channels, np_dtype)


def _ensure_rgba_u8(array: np.ndarray, name: str) -> np.ndarray:
    pixels = np.asarray(array)
    if pixels.ndim != 3 or pixels.shape[2] != 4:
        raise GeglCtypesError(f"{name} must be an RGBA array")
    if pixels.dtype != np.uint8:
        raise GeglCtypesError(f"{name} must use uint8 pixels")
    return np.ascontiguousarray(pixels)
