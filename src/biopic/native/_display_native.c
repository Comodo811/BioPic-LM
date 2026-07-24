#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include <math.h>

static double value_at(PyArrayObject *array, npy_intp index) {
    char *data = PyArray_BYTES(array) + index * PyArray_ITEMSIZE(array);
    switch (PyArray_TYPE(array)) {
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

static npy_uint8 scale_to_uint8(double value, double low, double high) {
    if (!isfinite(value)) {
        value = 0.0;
    }
    if (high <= low) {
        return 0;
    }
    double scaled = (value - low) / (high - low) * 255.0;
    if (scaled <= 0.0) {
        return 0;
    }
    if (scaled >= 255.0) {
        return 255;
    }
    return (npy_uint8)scaled;
}

static PyObject *to_display_uint8(PyObject *self, PyObject *args) {
    PyObject *pixels_obj;
    double low;
    double high;
    if (!PyArg_ParseTuple(args, "Odd", &pixels_obj, &low, &high)) {
        return NULL;
    }

    PyArrayObject *pixels = (PyArrayObject *)PyArray_FROM_OTF(
        pixels_obj,
        NPY_NOTYPE,
        NPY_ARRAY_IN_ARRAY
    );
    if (pixels == NULL) {
        return NULL;
    }
    int ndim = PyArray_NDIM(pixels);
    if (ndim != 2 && ndim != 3) {
        PyErr_SetString(PyExc_ValueError, "pixels must be 2D or 3D");
        Py_DECREF(pixels);
        return NULL;
    }
    int dtype = PyArray_TYPE(pixels);
    if (
        dtype != NPY_UINT8 &&
        dtype != NPY_UINT16 &&
        dtype != NPY_INT16 &&
        dtype != NPY_FLOAT32 &&
        dtype != NPY_FLOAT64
    ) {
        PyErr_SetString(PyExc_ValueError, "unsupported display dtype");
        Py_DECREF(pixels);
        return NULL;
    }

    npy_intp dims[3];
    dims[0] = PyArray_DIM(pixels, 0);
    dims[1] = PyArray_DIM(pixels, 1);
    if (ndim == 3) {
        dims[2] = PyArray_DIM(pixels, 2);
    }
    PyObject *out_obj = PyArray_SimpleNew(ndim, dims, NPY_UINT8);
    if (out_obj == NULL) {
        Py_DECREF(pixels);
        return NULL;
    }
    PyArrayObject *out = (PyArrayObject *)out_obj;
    npy_uint8 *out_data = (npy_uint8 *)PyArray_DATA(out);
    npy_intp count = PyArray_SIZE(pixels);

    Py_BEGIN_ALLOW_THREADS
    for (npy_intp index = 0; index < count; index++) {
        if (dtype == NPY_UINT8 && low == 0.0 && high == 255.0) {
            out_data[index] = (npy_uint8)value_at(pixels, index);
        } else {
            out_data[index] = scale_to_uint8(value_at(pixels, index), low, high);
        }
    }
    Py_END_ALLOW_THREADS

    Py_DECREF(pixels);
    return out_obj;
}

static PyMethodDef DisplayMethods[] = {
    {"to_display_uint8", to_display_uint8, METH_VARARGS, "Scale a scientific image tile to uint8 display pixels."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef displaymodule = {
    PyModuleDef_HEAD_INIT,
    "_display_native",
    "Native display conversion kernels for BioPic LM.",
    -1,
    DisplayMethods
};

PyMODINIT_FUNC PyInit__display_native(void) {
    import_array();
    return PyModule_Create(&displaymodule);
}
