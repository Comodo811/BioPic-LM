#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>

static double value_at(PyArrayObject *array, npy_intp index) {
    char *data = PyArray_BYTES(array) + index * PyArray_ITEMSIZE(array);
    switch (PyArray_TYPE(array)) {
    case NPY_BOOL:
        return (double)(*(npy_bool *)data);
    case NPY_UINT8:
        return (double)(*(npy_uint8 *)data);
    case NPY_UINT16:
        return (double)(*(npy_uint16 *)data);
    case NPY_INT16:
        return (double)(*(npy_int16 *)data);
    case NPY_FLOAT32:
        return (double)(*(float *)data);
    case NPY_FLOAT64:
        return *(double *)data;
    default:
        return 0.0;
    }
}

static double dtype_max(PyArrayObject *array) {
    switch (PyArray_TYPE(array)) {
    case NPY_BOOL:
        return 1.0;
    case NPY_UINT8:
        return 255.0;
    case NPY_UINT16:
        return 65535.0;
    case NPY_INT16:
        return 32767.0;
    case NPY_FLOAT32:
    case NPY_FLOAT64:
        return 1.0;
    default:
        return 1.0;
    }
}

static double normalized_mask_at(PyArrayObject *mask, npy_intp pixel) {
    int ndim = PyArray_NDIM(mask);
    int channels = ndim == 3 ? (int)PyArray_DIM(mask, 2) : 1;
    npy_intp index = channels == 1 ? pixel : pixel * channels;
    double value = value_at(mask, index);
    if (PyArray_TYPE(mask) == NPY_FLOAT32 || PyArray_TYPE(mask) == NPY_FLOAT64) {
        if (value < 0.0) {
            return 0.0;
        }
        if (value > 1.0) {
            return 1.0;
        }
        return value;
    }
    double max_value = dtype_max(mask);
    if (max_value <= 0.0) {
        return 0.0;
    }
    value /= max_value;
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

static PyObject *blend_normal_in_place(PyObject *self, PyObject *args) {
    PyObject *background_obj;
    PyObject *foreground_obj;
    PyObject *alpha_obj;
    double opacity;
    if (!PyArg_ParseTuple(
            args,
            "OOOd",
            &background_obj,
            &foreground_obj,
            &alpha_obj,
            &opacity
        )) {
        return NULL;
    }

    PyArrayObject *background = (PyArrayObject *)PyArray_FROM_OTF(
        background_obj,
        NPY_FLOAT32,
        NPY_ARRAY_INOUT_ARRAY
    );
    PyArrayObject *foreground = (PyArrayObject *)PyArray_FROM_OTF(
        foreground_obj,
        NPY_NOTYPE,
        NPY_ARRAY_IN_ARRAY
    );
    PyArrayObject *alpha = (PyArrayObject *)PyArray_FROM_OTF(
        alpha_obj,
        NPY_FLOAT32,
        NPY_ARRAY_IN_ARRAY
    );
    if (background == NULL || foreground == NULL || alpha == NULL) {
        Py_XDECREF(background);
        Py_XDECREF(foreground);
        Py_XDECREF(alpha);
        return NULL;
    }

    int bg_ndim = PyArray_NDIM(background);
    int fg_ndim = PyArray_NDIM(foreground);
    int alpha_ndim = PyArray_NDIM(alpha);
    if ((bg_ndim != 2 && bg_ndim != 3) || (fg_ndim != 2 && fg_ndim != 3) ||
        alpha_ndim != 2) {
        PyErr_SetString(PyExc_ValueError, "background/foreground must be 2D or 3D and alpha must be 2D");
        goto fail;
    }
    npy_intp height = PyArray_DIM(background, 0);
    npy_intp width = PyArray_DIM(background, 1);
    if (PyArray_DIM(foreground, 0) != height ||
        PyArray_DIM(foreground, 1) != width ||
        PyArray_DIM(alpha, 0) != height ||
        PyArray_DIM(alpha, 1) != width) {
        PyErr_SetString(PyExc_ValueError, "foreground and alpha must match background shape");
        goto fail;
    }
    int bg_channels = bg_ndim == 3 ? (int)PyArray_DIM(background, 2) : 1;
    int fg_channels = fg_ndim == 3 ? (int)PyArray_DIM(foreground, 2) : 1;
    if (bg_channels != 1 && bg_channels != 3 && bg_channels != 4) {
        PyErr_SetString(PyExc_ValueError, "unsupported background channel count");
        goto fail;
    }
    if (fg_channels != 1 && fg_channels != 3 && fg_channels != 4) {
        PyErr_SetString(PyExc_ValueError, "unsupported foreground channel count");
        goto fail;
    }

    if (opacity < 0.0) {
        opacity = 0.0;
    } else if (opacity > 1.0) {
        opacity = 1.0;
    }

    float *bg_data = (float *)PyArray_DATA(background);
    float *alpha_data = (float *)PyArray_DATA(alpha);
    npy_intp pixel_count = height * width;
    Py_BEGIN_ALLOW_THREADS
    for (npy_intp pixel = 0; pixel < pixel_count; pixel++) {
        double a = (double)alpha_data[pixel] * opacity;
        if (a <= 0.0) {
            continue;
        }
        if (a > 1.0) {
            a = 1.0;
        }
        if (bg_channels == 1) {
            double fg = value_at(foreground, fg_channels == 1 ? pixel : pixel * fg_channels);
            bg_data[pixel] = (float)(a * fg + (1.0 - a) * (double)bg_data[pixel]);
            continue;
        }
        for (int channel = 0; channel < bg_channels; channel++) {
            npy_intp bg_index = pixel * bg_channels + channel;
            npy_intp fg_index = fg_channels == 1 ? pixel : pixel * fg_channels + (channel < fg_channels ? channel : fg_channels - 1);
            double fg = value_at(foreground, fg_index);
            bg_data[bg_index] = (float)(a * fg + (1.0 - a) * (double)bg_data[bg_index]);
        }
    }
    Py_END_ALLOW_THREADS

    if (PyArray_ResolveWritebackIfCopy(background) < 0) {
        goto fail_no_writeback;
    }
    Py_DECREF(background);
    Py_DECREF(foreground);
    Py_DECREF(alpha);
    Py_RETURN_NONE;

fail:
    PyArray_DiscardWritebackIfCopy(background);
fail_no_writeback:
    Py_DECREF(background);
    Py_DECREF(foreground);
    Py_DECREF(alpha);
    return NULL;
}

static PyObject *blend_normal_offset_in_place(PyObject *self, PyObject *args) {
    PyObject *background_obj;
    PyObject *foreground_obj;
    PyObject *alpha_obj;
    PyObject *mask_obj;
    int rect_x;
    int rect_y;
    int offset_x;
    int offset_y;
    double opacity;
    if (!PyArg_ParseTuple(
            args,
            "OOOOiiiid",
            &background_obj,
            &foreground_obj,
            &alpha_obj,
            &mask_obj,
            &rect_x,
            &rect_y,
            &offset_x,
            &offset_y,
            &opacity
        )) {
        return NULL;
    }

    PyArrayObject *background = (PyArrayObject *)PyArray_FROM_OTF(
        background_obj,
        NPY_FLOAT32,
        NPY_ARRAY_INOUT_ARRAY
    );
    PyArrayObject *foreground = (PyArrayObject *)PyArray_FROM_OTF(
        foreground_obj,
        NPY_NOTYPE,
        NPY_ARRAY_IN_ARRAY
    );
    PyArrayObject *alpha = NULL;
    PyArrayObject *mask = NULL;
    if (alpha_obj != Py_None) {
        alpha = (PyArrayObject *)PyArray_FROM_OTF(
            alpha_obj,
            NPY_FLOAT32,
            NPY_ARRAY_IN_ARRAY
        );
    }
    if (mask_obj != Py_None) {
        mask = (PyArrayObject *)PyArray_FROM_OTF(
            mask_obj,
            NPY_NOTYPE,
            NPY_ARRAY_IN_ARRAY
        );
    }
    if (
        background == NULL ||
        foreground == NULL ||
        (alpha_obj != Py_None && alpha == NULL) ||
        (mask_obj != Py_None && mask == NULL)
    ) {
        Py_XDECREF(background);
        Py_XDECREF(foreground);
        Py_XDECREF(alpha);
        Py_XDECREF(mask);
        return NULL;
    }

    int bg_ndim = PyArray_NDIM(background);
    int fg_ndim = PyArray_NDIM(foreground);
    if ((bg_ndim != 2 && bg_ndim != 3) || (fg_ndim != 2 && fg_ndim != 3)) {
        PyErr_SetString(PyExc_ValueError, "background and foreground must be 2D or 3D");
        goto offset_fail;
    }
    if (alpha != NULL && PyArray_NDIM(alpha) != 2) {
        PyErr_SetString(PyExc_ValueError, "alpha must be 2D");
        goto offset_fail;
    }
    if (mask != NULL && PyArray_NDIM(mask) != 2 && PyArray_NDIM(mask) != 3) {
        PyErr_SetString(PyExc_ValueError, "mask must be 2D or 3D");
        goto offset_fail;
    }

    npy_intp bg_height = PyArray_DIM(background, 0);
    npy_intp bg_width = PyArray_DIM(background, 1);
    npy_intp fg_height = PyArray_DIM(foreground, 0);
    npy_intp fg_width = PyArray_DIM(foreground, 1);
    if (alpha != NULL && (PyArray_DIM(alpha, 0) != fg_height || PyArray_DIM(alpha, 1) != fg_width)) {
        PyErr_SetString(PyExc_ValueError, "alpha must match foreground size");
        goto offset_fail;
    }
    if (mask != NULL && (PyArray_DIM(mask, 0) != fg_height || PyArray_DIM(mask, 1) != fg_width)) {
        PyErr_SetString(PyExc_ValueError, "mask must match foreground size");
        goto offset_fail;
    }

    int bg_channels = bg_ndim == 3 ? (int)PyArray_DIM(background, 2) : 1;
    int fg_channels = fg_ndim == 3 ? (int)PyArray_DIM(foreground, 2) : 1;
    if (bg_channels != 1 && bg_channels != 3 && bg_channels != 4) {
        PyErr_SetString(PyExc_ValueError, "unsupported background channel count");
        goto offset_fail;
    }
    if (fg_channels != 1 && fg_channels != 3 && fg_channels != 4) {
        PyErr_SetString(PyExc_ValueError, "unsupported foreground channel count");
        goto offset_fail;
    }

    if (opacity < 0.0) {
        opacity = 0.0;
    } else if (opacity > 1.0) {
        opacity = 1.0;
    }

    float *bg_data = (float *)PyArray_DATA(background);
    float *alpha_data = alpha == NULL ? NULL : (float *)PyArray_DATA(alpha);

    Py_BEGIN_ALLOW_THREADS
    for (npy_intp y = 0; y < bg_height; y++) {
        npy_intp image_y = (npy_intp)rect_y + y;
        npy_intp src_y = image_y - (npy_intp)offset_y;
        if (src_y < 0 || src_y >= fg_height) {
            continue;
        }
        for (npy_intp x = 0; x < bg_width; x++) {
            npy_intp image_x = (npy_intp)rect_x + x;
            npy_intp src_x = image_x - (npy_intp)offset_x;
            if (src_x < 0 || src_x >= fg_width) {
                continue;
            }
            npy_intp bg_pixel = y * bg_width + x;
            npy_intp fg_pixel = src_y * fg_width + src_x;
            double a = alpha_data == NULL ? 1.0 : (double)alpha_data[fg_pixel];
            if (mask != NULL) {
                a *= normalized_mask_at(mask, fg_pixel);
            }
            a *= opacity;
            if (a <= 0.0) {
                continue;
            }
            if (a > 1.0) {
                a = 1.0;
            }
            if (bg_channels == 1) {
                double fg = value_at(
                    foreground,
                    fg_channels == 1 ? fg_pixel : fg_pixel * fg_channels
                );
                bg_data[bg_pixel] = (float)(a * fg + (1.0 - a) * (double)bg_data[bg_pixel]);
                continue;
            }
            for (int channel = 0; channel < bg_channels; channel++) {
                npy_intp bg_index = bg_pixel * bg_channels + channel;
                npy_intp fg_index = fg_channels == 1
                    ? fg_pixel
                    : fg_pixel * fg_channels + (channel < fg_channels ? channel : fg_channels - 1);
                double fg = value_at(foreground, fg_index);
                bg_data[bg_index] = (float)(a * fg + (1.0 - a) * (double)bg_data[bg_index]);
            }
        }
    }
    Py_END_ALLOW_THREADS

    if (PyArray_ResolveWritebackIfCopy(background) < 0) {
        goto offset_fail_no_writeback;
    }
    Py_DECREF(background);
    Py_DECREF(foreground);
    Py_XDECREF(alpha);
    Py_XDECREF(mask);
    Py_RETURN_NONE;

offset_fail:
    PyArray_DiscardWritebackIfCopy(background);
offset_fail_no_writeback:
    Py_DECREF(background);
    Py_DECREF(foreground);
    Py_XDECREF(alpha);
    Py_XDECREF(mask);
    return NULL;
}

static PyMethodDef CompositeMethods[] = {
    {"blend_normal_in_place", blend_normal_in_place, METH_VARARGS, "Blend a normal layer into a float32 projection in place."},
    {"blend_normal_offset_in_place", blend_normal_offset_in_place, METH_VARARGS, "Blend an offset normal layer into a float32 projection in place."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef compositemodule = {
    PyModuleDef_HEAD_INIT,
    "_composite_native",
    "Native compositing kernels for BioPic LM.",
    -1,
    CompositeMethods
};

PyMODINIT_FUNC PyInit__composite_native(void) {
    import_array();
    return PyModule_Create(&compositemodule);
}
