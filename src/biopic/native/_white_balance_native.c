#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include <math.h>
#include <string.h>

static double round_nearest(double value) {
    return floor(value + 0.5);
}

static double normalized_value(char *ptr, int dtype) {
    switch (dtype) {
    case NPY_UINT8:
        return (double)(*(npy_uint8 *)ptr) / 255.0;
    case NPY_UINT16:
        return (double)(*(npy_uint16 *)ptr) / 65535.0;
    case NPY_INT16:
        return ((double)(*(npy_int16 *)ptr) + 32768.0) / 65535.0;
    case NPY_FLOAT32:
        return (double)(*(float *)ptr);
    case NPY_FLOAT64:
        return *(double *)ptr;
    default:
        return 0.0;
    }
}

static void write_value(char *ptr, int dtype, double value) {
    if (!isfinite(value)) {
        value = 0.0;
    }
    if (value < 0.0) {
        value = 0.0;
    }
    if (value > 1.0) {
        value = 1.0;
    }
    switch (dtype) {
    case NPY_UINT8:
        *(npy_uint8 *)ptr = (npy_uint8)round_nearest(value * 255.0);
        break;
    case NPY_UINT16:
        *(npy_uint16 *)ptr = (npy_uint16)round_nearest(value * 65535.0);
        break;
    case NPY_INT16:
        *(npy_int16 *)ptr = (npy_int16)round_nearest(value * 65535.0 - 32768.0);
        break;
    case NPY_FLOAT32:
        *(float *)ptr = (float)value;
        break;
    case NPY_FLOAT64:
        *(double *)ptr = value;
        break;
    }
}

static PyObject *apply_rgb_gains(PyObject *self, PyObject *args) {
    PyObject *image_obj;
    double red;
    double green;
    double blue;
    if (!PyArg_ParseTuple(args, "Oddd", &image_obj, &red, &green, &blue)) {
        return NULL;
    }

    PyArrayObject *image = (PyArrayObject *)PyArray_FROM_OTF(
        image_obj,
        NPY_NOTYPE,
        NPY_ARRAY_IN_ARRAY
    );
    if (image == NULL) {
        return NULL;
    }
    int ndim = PyArray_NDIM(image);
    if (ndim != 2 && ndim != 3) {
        PyErr_SetString(PyExc_ValueError, "image must be 2D or 3D");
        Py_DECREF(image);
        return NULL;
    }
    int dtype = PyArray_TYPE(image);
    if (
        dtype != NPY_UINT8 &&
        dtype != NPY_UINT16 &&
        dtype != NPY_INT16 &&
        dtype != NPY_FLOAT32 &&
        dtype != NPY_FLOAT64
    ) {
        PyErr_SetString(PyExc_TypeError, "unsupported image dtype");
        Py_DECREF(image);
        return NULL;
    }

    PyObject *result_obj = PyArray_NewLikeArray(image, NPY_ANYORDER, NULL, 0);
    if (result_obj == NULL) {
        Py_DECREF(image);
        return NULL;
    }
    PyArrayObject *result = (PyArrayObject *)result_obj;
    npy_intp height = PyArray_DIM(image, 0);
    npy_intp width = PyArray_DIM(image, 1);
    npy_intp channels = ndim == 3 ? PyArray_DIM(image, 2) : 1;
    npy_intp item = PyArray_ITEMSIZE(image);
    npy_intp stride_y = PyArray_STRIDE(image, 0);
    npy_intp stride_x = PyArray_STRIDE(image, 1);
    npy_intp stride_c = ndim == 3 ? PyArray_STRIDE(image, 2) : 0;
    npy_intp out_stride_y = PyArray_STRIDE(result, 0);
    npy_intp out_stride_x = PyArray_STRIDE(result, 1);
    npy_intp out_stride_c = ndim == 3 ? PyArray_STRIDE(result, 2) : 0;

    double gray_gain = (red + green + blue) / 3.0;
    for (npy_intp y = 0; y < height; ++y) {
        for (npy_intp x = 0; x < width; ++x) {
            char *src = PyArray_BYTES(image) + y * stride_y + x * stride_x;
            char *dst = PyArray_BYTES(result) + y * out_stride_y + x * out_stride_x;
            if (channels >= 3) {
                write_value(dst + 0 * out_stride_c, dtype, normalized_value(src + 0 * stride_c, dtype) * red);
                write_value(dst + 1 * out_stride_c, dtype, normalized_value(src + 1 * stride_c, dtype) * green);
                write_value(dst + 2 * out_stride_c, dtype, normalized_value(src + 2 * stride_c, dtype) * blue);
                for (npy_intp c = 3; c < channels; ++c) {
                    memcpy(dst + c * out_stride_c, src + c * stride_c, (size_t)item);
                }
            } else {
                write_value(dst, dtype, normalized_value(src, dtype) * gray_gain);
            }
        }
    }

    Py_DECREF(image);
    return result_obj;
}

static PyMethodDef WhiteBalanceMethods[] = {
    {"apply_rgb_gains", apply_rgb_gains, METH_VARARGS, "Apply RGB white-balance gains."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_white_balance_native",
    "Native white-balance kernels.",
    -1,
    WhiteBalanceMethods
};

PyMODINIT_FUNC PyInit__white_balance_native(void) {
    import_array();
    return PyModule_Create(&moduledef);
}
