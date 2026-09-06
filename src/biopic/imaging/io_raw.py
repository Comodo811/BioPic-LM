"""RAW image import helpers, including optional Windows WIC display decoding."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from biopic.models.image_asset import ImageAsset
from biopic.imaging.io_metadata import _clean_metadata

RAW_STACK_BRIGHTNESS = 3.75
RAW_DECODE_RAWPY = "rawpy"
RAW_DECODE_WIC_DISPLAY = "wic_display"

_S_OK = 0
_RPC_E_CHANGED_MODE = 0x80010106
_CLSCTX_INPROC_SERVER = 0x1
_GENERIC_READ = 0x80000000
_WIC_DECODE_METADATA_CACHE_ON_DEMAND = 0


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: str) -> _GUID:
    parsed = UUID(value)
    return _GUID(
        parsed.time_low,
        parsed.time_mid,
        parsed.time_hi_version,
        (_GUID._fields_[3][1])(*parsed.bytes[8:]),
    )


_CLSID_WIC_IMAGING_FACTORY = _guid("cacaf262-9370-4615-a13b-9f5539da4c0a")
_IID_IWIC_IMAGING_FACTORY = _guid("ec5ec8a9-c395-4314-9c77-54d7a935ff70")
_GUID_WIC_PIXEL_FORMAT_32BPP_BGRA = _guid("6fddc324-4e03-4bfe-b185-3d77768dc90f")


def _read_raw(
    path: Path,
    load_pixels: bool,
    *,
    decode_mode: str = RAW_DECODE_RAWPY,
) -> tuple[ImageAsset, np.ndarray]:
    if decode_mode == RAW_DECODE_WIC_DISPLAY:
        try:
            return _read_raw_wic_display(path, load_pixels)
        except Exception:
            if load_pixels:
                pass
            else:
                return _read_rawpy_metadata(path, load_pixels)

    return _read_rawpy_metadata(path, load_pixels)


def _read_rawpy_metadata(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    try:
        import rawpy  # type: ignore[import-untyped]
    except ImportError as exc:
        message = (
            "RAW image support requires optional dependency rawpy; "
            "install BioPic LM with the raw extra."
        )
        raise ValueError(message) from exc

    with rawpy.imread(str(path)) as raw:
        sizes = raw.sizes
        height, width = _raw_active_size(sizes)
        metadata = _rawpy_metadata(raw, width, height)
        if load_pixels:
            pixels = raw.postprocess(
                output_bps=16,
                no_auto_bright=True,
                bright=RAW_STACK_BRIGHTNESS,
                use_camera_wb=True,
            )
            pixels = _center_crop_pixels(pixels, height, width)
        else:
            pixels = np.empty((0,), dtype=np.uint16)
    return (
        ImageAsset(
            path=str(path),
            width=width,
            height=height,
            frames=1,
            dtype="uint16",
            color_model="rgb",
            metadata=metadata,
        ),
        pixels,
    )


def _rawpy_metadata(raw: object, width: int, height: int) -> dict[str, Any]:
    metadata = {
        "raw_type": type(raw).__name__,
        "raw_pipeline_available": True,
        "raw_import_backend": "rawpy",
        "raw_import_brightness": RAW_STACK_BRIGHTNESS,
        "raw_import_use_camera_wb": True,
        "raw_active_crop": (width, height),
        "raw_visible_shape": _raw_visible_shape(raw),
        "black_level_per_channel": tuple(getattr(raw, "black_level_per_channel", ())),
        "camera_whitebalance": tuple(getattr(raw, "camera_whitebalance", ())),
        "daylight_whitebalance": tuple(getattr(raw, "daylight_whitebalance", ())),
        "white_level": getattr(raw, "white_level", None),
        "raw_color_description": _bytes_or_text(getattr(raw, "color_desc", None)),
        "raw_num_colors": getattr(raw, "num_colors", None),
        "raw_color_filter_pattern": _metadata_array(getattr(raw, "raw_pattern", None)),
        "raw_color_matrix": _metadata_array(getattr(raw, "color_matrix", None)),
        "raw_rgb_xyz_matrix": _metadata_array(getattr(raw, "rgb_xyz_matrix", None)),
        "raw_camera_white_level_per_channel": tuple(
            getattr(raw, "camera_white_level_per_channel", ())
        ),
    }
    return _clean_metadata(metadata)


def _raw_visible_shape(raw: object) -> tuple[int, ...] | None:
    visible = getattr(raw, "raw_image_visible", None)
    shape = getattr(visible, "shape", None)
    if shape is None:
        return None
    try:
        return tuple(int(part) for part in shape)
    except (TypeError, ValueError):
        return None


def _metadata_array(value: object) -> list[Any] | None:
    if value is None:
        return None
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return None
    if array.size == 0:
        return None
    return array.tolist()


def _bytes_or_text(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace")
    return value


def _read_raw_wic_display(path: Path, load_pixels: bool) -> tuple[ImageAsset, np.ndarray]:
    if sys.platform != "win32":
        raise ValueError("Windows WIC RAW import is only available on Windows.")

    io_module = sys.modules.get("biopic.imaging.io")
    decoder = (
        getattr(io_module, "_decode_wic_32bpp_bgra", _decode_wic_32bpp_bgra)
        if io_module is not None
        else _decode_wic_32bpp_bgra
    )
    pixels = decoder(path) if load_pixels else None
    if pixels is None:
        asset, _empty = _read_rawpy_metadata(path, load_pixels=False)
        asset.metadata["raw_import_backend"] = "windows_wic_32bpp_bgra_metadata_fallback"
        asset.dtype = "uint8"
        return asset, np.empty((0,), dtype=np.uint8)

    asset = ImageAsset(
        path=str(path),
        width=int(pixels.shape[1]),
        height=int(pixels.shape[0]),
        frames=1,
        dtype="uint8",
        color_model="rgb",
        metadata={
            "raw_import_backend": "windows_wic_32bpp_bgra",
            "raw_import_note": "Decoded through Windows Imaging Component display bitmap path.",
        },
    )
    return asset, pixels


def _decode_wic_32bpp_bgra(path: Path) -> np.ndarray:
    ole32 = ctypes.OleDLL("ole32")
    windows_codecs = ctypes.OleDLL("WindowsCodecs")

    coinit_result = ole32.CoInitializeEx(None, 2)
    should_uninitialize = coinit_result in {_S_OK, 1}
    if coinit_result not in {_S_OK, 1, _RPC_E_CHANGED_MODE}:
        _raise_if_failed(coinit_result, "CoInitializeEx")

    factory = ctypes.c_void_p()
    decoder = ctypes.c_void_p()
    frame = ctypes.c_void_p()
    converted = ctypes.c_void_p()
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(_CLSID_WIC_IMAGING_FACTORY),
            None,
            _CLSCTX_INPROC_SERVER,
            ctypes.byref(_IID_IWIC_IMAGING_FACTORY),
            ctypes.byref(factory),
        )
        _raise_if_failed(hr, "CoCreateInstance(IWICImagingFactory)")

        _call_com(
            factory,
            3,
            [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ],
            ctypes.c_wchar_p(str(path)),
            None,
            ctypes.c_uint32(_GENERIC_READ),
            ctypes.c_uint32(_WIC_DECODE_METADATA_CACHE_ON_DEMAND),
            ctypes.byref(decoder),
        )
        _call_com(
            decoder,
            13,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)],
            ctypes.c_uint32(0),
            ctypes.byref(frame),
        )

        windows_codecs.WICConvertBitmapSource.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        windows_codecs.WICConvertBitmapSource.restype = ctypes.c_long
        hr = windows_codecs.WICConvertBitmapSource(
            ctypes.byref(_GUID_WIC_PIXEL_FORMAT_32BPP_BGRA),
            frame,
            ctypes.byref(converted),
        )
        _raise_if_failed(hr, "WICConvertBitmapSource")

        width = ctypes.c_uint32()
        height = ctypes.c_uint32()
        _call_com(
            converted,
            3,
            [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_uint32),
            ],
            ctypes.byref(width),
            ctypes.byref(height),
        )
        if width.value <= 0 or height.value <= 0:
            raise ValueError("WIC decoded RAW image has no pixels.")

        stride = int(width.value) * 4
        buffer_size = stride * int(height.value)
        buffer = (ctypes.c_ubyte * buffer_size)()
        _call_com(
            converted,
            7,
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
            ],
            None,
            ctypes.c_uint32(stride),
            ctypes.c_uint32(buffer_size),
            ctypes.cast(buffer, ctypes.c_void_p),
        )
        bgra = np.frombuffer(buffer, dtype=np.uint8).reshape(
            int(height.value),
            int(width.value),
            4,
        )
        return np.ascontiguousarray(bgra[:, :, [2, 1, 0]])
    finally:
        for pointer in (converted, frame, decoder, factory):
            _com_release(pointer)
        if should_uninitialize:
            ole32.CoUninitialize()


def _call_com(
    pointer: ctypes.c_void_p,
    index: int,
    argtypes: list[object],
    *args: object,
) -> int:
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    func = ctypes.WINFUNCTYPE(ctypes.c_long, *argtypes)(vtable[index])
    hr = int(func(pointer, *args))
    _raise_if_failed(hr, f"COM vtable call {index}")
    return hr


def _com_release(pointer: ctypes.c_void_p) -> None:
    if not pointer:
        return
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
    release(pointer)


def _raise_if_failed(hr: int, operation: str) -> None:
    if hr & 0x80000000:
        raise OSError(f"{operation} failed with HRESULT 0x{hr & 0xffffffff:08x}")


def _raw_active_size(sizes: object) -> tuple[int, int]:
    crop_width = int(getattr(sizes, "crop_width", getattr(sizes, "width", 0)))
    crop_height = int(getattr(sizes, "crop_height", getattr(sizes, "height", 0)))
    width = int(getattr(sizes, "width", crop_width))
    height = int(getattr(sizes, "height", crop_height))
    flip = int(getattr(sizes, "flip", 0) or 0)
    if flip in {5, 6, 7, 8} and width >= crop_width and height >= crop_height:
        return crop_width, crop_height
    return crop_height, crop_width


def _center_crop_pixels(pixels: np.ndarray, height: int, width: int) -> np.ndarray:
    if pixels.ndim < 2:
        return pixels
    source_height, source_width = pixels.shape[:2]
    if source_height == height and source_width == width:
        return pixels
    if source_height < height or source_width < width:
        return pixels
    y = (source_height - height) // 2
    x = (source_width - width) // 2
    return pixels[y : y + height, x : x + width]

