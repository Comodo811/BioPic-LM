#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include <math.h>

static int in_selection(
    npy_intp x,
    npy_intp y,
    long sx,
    long sy,
    long sw,
    long sh,
    int ellipse
) {
    double cx;
    double cy;
    double rx;
    double ry;
    double nx;
    double ny;

    if (sw < 0 || sh < 0) {
        return 1;
    }
    if (x < sx || y < sy || x >= sx + sw || y >= sy + sh) {
        return 0;
    }
    if (!ellipse) {
        return 1;
    }
    cx = sx + (sw - 1) / 2.0;
    cy = sy + (sh - 1) / 2.0;
    rx = fmax(sw / 2.0, 0.5);
    ry = fmax(sh / 2.0, 0.5);
    nx = (x - cx) / rx;
    ny = (y - cy) / ry;
    return nx * nx + ny * ny <= 1.0;
}

static int set_value(PyArrayObject *array, npy_intp index, double value) {
    int typenum = PyArray_TYPE(array);
    char *data = PyArray_BYTES(array) + index * PyArray_ITEMSIZE(array);
    switch (typenum) {
        case NPY_UINT8:
            if (value < 0.0) value = 0.0;
            if (value > 255.0) value = 255.0;
            *((npy_uint8 *)data) = (npy_uint8)llround(value);
            return 0;
        case NPY_UINT16:
            if (value < 0.0) value = 0.0;
            if (value > 65535.0) value = 65535.0;
            *((npy_uint16 *)data) = (npy_uint16)llround(value);
            return 0;
        case NPY_FLOAT32:
            *((npy_float32 *)data) = (npy_float32)value;
            return 0;
        case NPY_FLOAT64:
            *((npy_float64 *)data) = (npy_float64)value;
            return 0;
        default:
            PyErr_SetString(PyExc_TypeError, "Unsupported dtype for native stroke backend");
            return -1;
    }
}

static PyObject *paint_disks(PyObject *self, PyObject *args) {
    PyObject *array_obj;
    PyObject *points_obj;
    PyObject *rect_obj;
    PyArrayObject *array;
    PyObject *iterator;
    PyObject *point;
    int radius;
    int ellipse;
    double value;
    long sx = -1;
    long sy = -1;
    long sw = -1;
    long sh = -1;
    npy_intp height;
    npy_intp width;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOidOi", &array_obj, &points_obj, &radius, &value, &rect_obj, &ellipse)) {
        return NULL;
    }
    array = (PyArrayObject *)PyArray_FROM_OTF(
        array_obj,
        NPY_NOTYPE,
        NPY_ARRAY_INOUT_ARRAY2 | NPY_ARRAY_C_CONTIGUOUS
    );
    if (array == NULL) {
        return NULL;
    }
    if (PyArray_NDIM(array) != 2) {
        Py_DECREF(array);
        PyErr_SetString(PyExc_ValueError, "Native stroke backend expects a 2D array");
        return NULL;
    }
    if (!PyArg_ParseTuple(rect_obj, "llll", &sx, &sy, &sw, &sh)) {
        Py_DECREF(array);
        return NULL;
    }
    height = PyArray_DIM(array, 0);
    width = PyArray_DIM(array, 1);
    iterator = PyObject_GetIter(points_obj);
    if (iterator == NULL) {
        Py_DECREF(array);
        return NULL;
    }
    while ((point = PyIter_Next(iterator)) != NULL) {
        long cx;
        long cy;
        long y;
        long x;
        if (!PyArg_ParseTuple(point, "ll", &cx, &cy)) {
            Py_DECREF(point);
            Py_DECREF(iterator);
            Py_DECREF(array);
            return NULL;
        }
        Py_DECREF(point);
        for (y = cy - radius; y <= cy + radius; y++) {
            if (y < 0 || y >= height) {
                continue;
            }
            for (x = cx - radius; x <= cx + radius; x++) {
                long dx;
                long dy;
                if (x < 0 || x >= width) {
                    continue;
                }
                dx = x - cx;
                dy = y - cy;
                if (dx * dx + dy * dy > radius * radius) {
                    continue;
                }
                if (!in_selection(x, y, sx, sy, sw, sh, ellipse)) {
                    continue;
                }
                if (set_value(array, y * width + x, value) < 0) {
                    Py_DECREF(iterator);
                    Py_DECREF(array);
                    return NULL;
                }
            }
        }
    }
    Py_DECREF(iterator);
    if (PyErr_Occurred()) {
        Py_DECREF(array);
        return NULL;
    }
    PyArray_ResolveWritebackIfCopy(array);
    Py_DECREF(array);
    Py_RETURN_NONE;
}

static PyObject *paint_disks_pair(PyObject *self, PyObject *args) {
    PyObject *content_obj;
    PyObject *alpha_obj;
    PyObject *points_obj;
    PyObject *rect_obj;
    PyArrayObject *content;
    PyArrayObject *alpha;
    PyObject *iterator;
    PyObject *point;
    int radius;
    int ellipse;
    double value;
    double alpha_value;
    long sx = -1;
    long sy = -1;
    long sw = -1;
    long sh = -1;
    npy_intp height;
    npy_intp width;

    (void)self;
    if (!PyArg_ParseTuple(
            args,
            "OOOiddOi",
            &content_obj,
            &alpha_obj,
            &points_obj,
            &radius,
            &value,
            &alpha_value,
            &rect_obj,
            &ellipse
        )) {
        return NULL;
    }
    content = (PyArrayObject *)PyArray_FROM_OTF(
        content_obj,
        NPY_NOTYPE,
        NPY_ARRAY_INOUT_ARRAY2 | NPY_ARRAY_C_CONTIGUOUS
    );
    alpha = (PyArrayObject *)PyArray_FROM_OTF(
        alpha_obj,
        NPY_NOTYPE,
        NPY_ARRAY_INOUT_ARRAY2 | NPY_ARRAY_C_CONTIGUOUS
    );
    if (content == NULL || alpha == NULL) {
        Py_XDECREF(content);
        Py_XDECREF(alpha);
        return NULL;
    }
    if (PyArray_NDIM(content) != 2 || PyArray_NDIM(alpha) != 2) {
        Py_DECREF(content);
        Py_DECREF(alpha);
        PyErr_SetString(PyExc_ValueError, "Native paired stroke backend expects 2D arrays");
        return NULL;
    }
    if (
        PyArray_DIM(content, 0) != PyArray_DIM(alpha, 0) ||
        PyArray_DIM(content, 1) != PyArray_DIM(alpha, 1)
    ) {
        Py_DECREF(content);
        Py_DECREF(alpha);
        PyErr_SetString(PyExc_ValueError, "Content and alpha arrays must have matching shapes");
        return NULL;
    }
    if (!PyArg_ParseTuple(rect_obj, "llll", &sx, &sy, &sw, &sh)) {
        Py_DECREF(content);
        Py_DECREF(alpha);
        return NULL;
    }
    height = PyArray_DIM(content, 0);
    width = PyArray_DIM(content, 1);
    iterator = PyObject_GetIter(points_obj);
    if (iterator == NULL) {
        Py_DECREF(content);
        Py_DECREF(alpha);
        return NULL;
    }
    while ((point = PyIter_Next(iterator)) != NULL) {
        long cx;
        long cy;
        long y;
        long x;
        if (!PyArg_ParseTuple(point, "ll", &cx, &cy)) {
            Py_DECREF(point);
            Py_DECREF(iterator);
            Py_DECREF(content);
            Py_DECREF(alpha);
            return NULL;
        }
        Py_DECREF(point);
        for (y = cy - radius; y <= cy + radius; y++) {
            if (y < 0 || y >= height) {
                continue;
            }
            for (x = cx - radius; x <= cx + radius; x++) {
                long dx;
                long dy;
                npy_intp index;
                if (x < 0 || x >= width) {
                    continue;
                }
                dx = x - cx;
                dy = y - cy;
                if (dx * dx + dy * dy > radius * radius) {
                    continue;
                }
                if (!in_selection(x, y, sx, sy, sw, sh, ellipse)) {
                    continue;
                }
                index = y * width + x;
                if (set_value(content, index, value) < 0 ||
                    set_value(alpha, index, alpha_value) < 0) {
                    Py_DECREF(iterator);
                    Py_DECREF(content);
                    Py_DECREF(alpha);
                    return NULL;
                }
            }
        }
    }
    Py_DECREF(iterator);
    if (PyErr_Occurred()) {
        Py_DECREF(content);
        Py_DECREF(alpha);
        return NULL;
    }
    PyArray_ResolveWritebackIfCopy(content);
    PyArray_ResolveWritebackIfCopy(alpha);
    Py_DECREF(content);
    Py_DECREF(alpha);
    Py_RETURN_NONE;
}

static int paint_disk_native(
    PyArrayObject *array,
    long cx,
    long cy,
    int radius,
    double value,
    long sx,
    long sy,
    long sw,
    long sh,
    int ellipse
) {
    npy_intp height = PyArray_DIM(array, 0);
    npy_intp width = PyArray_DIM(array, 1);
    long y;
    long x;
    for (y = cy - radius; y <= cy + radius; y++) {
        if (y < 0 || y >= height) {
            continue;
        }
        for (x = cx - radius; x <= cx + radius; x++) {
            long dx;
            long dy;
            if (x < 0 || x >= width) {
                continue;
            }
            dx = x - cx;
            dy = y - cy;
            if (dx * dx + dy * dy > radius * radius) {
                continue;
            }
            if (!in_selection(x, y, sx, sy, sw, sh, ellipse)) {
                continue;
            }
            if (set_value(array, y * width + x, value) < 0) {
                return -1;
            }
        }
    }
    return 0;
}

static double avoid_exact_integer(double value) {
    const double epsilon = 1e-6;
    double integral = floor(value);
    double fractional = value - integral;
    if (fractional < epsilon) {
        return integral + epsilon;
    }
    if (fractional > 1.0 - epsilon) {
        return integral + 1.0 - epsilon;
    }
    return value;
}

static double brush_spacing_pixels(int radius) {
    double diameter = fmax(1.0, (double)radius * 2.0 + 1.0);
    return fmax(0.5, diameter * 0.15);
}

static PyObject *spacing_dabs(PyObject *self, PyObject *args) {
    double x0;
    double y0;
    double x1;
    double y1;
    double remainder;
    double spacing;
    double distance;
    double distance_to_next;
    double dx;
    double dy;
    int radius;
    PyObject *points;
    long last_x = 0;
    long last_y = 0;
    int has_last = 0;

    (void)self;
    if (!PyArg_ParseTuple(args, "ddddid", &x0, &y0, &x1, &y1, &radius, &remainder)) {
        return NULL;
    }

    x0 = avoid_exact_integer(x0);
    y0 = avoid_exact_integer(y0);
    x1 = avoid_exact_integer(x1);
    y1 = avoid_exact_integer(y1);
    dx = x1 - x0;
    dy = y1 - y0;
    distance = hypot(dx, dy);
    if (distance <= 1e-9) {
        return Py_BuildValue("dO", remainder, PyList_New(0));
    }

    spacing = brush_spacing_pixels(radius);
    if (remainder < 0.0 || remainder >= spacing) {
        remainder = fmod(fmax(0.0, remainder), spacing);
    }
    distance_to_next = spacing - remainder;
    points = PyList_New(0);
    if (points == NULL) {
        return NULL;
    }
    while (distance_to_next <= distance + 1e-9) {
        double t = distance_to_next / distance;
        long x = (long)llround(x0 + dx * t);
        long y = (long)llround(y0 + dy * t);
        if (has_last && x == last_x && y == last_y) {
            distance_to_next += spacing;
            continue;
        }
        PyObject *point = Py_BuildValue("(ll)", x, y);
        if (point == NULL) {
            Py_DECREF(points);
            return NULL;
        }
        if (PyList_Append(points, point) < 0) {
            Py_DECREF(point);
            Py_DECREF(points);
            return NULL;
        }
        Py_DECREF(point);
        last_x = x;
        last_y = y;
        has_last = 1;
        distance_to_next += spacing;
    }
    remainder = fmod(remainder + distance, spacing);
    return Py_BuildValue("dN", remainder, points);
}

static PyObject *paint_stroke(PyObject *self, PyObject *args) {
    PyObject *array_obj;
    PyObject *points_obj;
    PyObject *rect_obj;
    PyArrayObject *array;
    PyObject *sequence;
    Py_ssize_t count;
    int radius;
    int ellipse;
    double value;
    long sx = -1;
    long sy = -1;
    long sw = -1;
    long sh = -1;
    Py_ssize_t i;

    (void)self;
    if (!PyArg_ParseTuple(args, "OOidOi", &array_obj, &points_obj, &radius, &value, &rect_obj, &ellipse)) {
        return NULL;
    }
    array = (PyArrayObject *)PyArray_FROM_OTF(
        array_obj,
        NPY_NOTYPE,
        NPY_ARRAY_INOUT_ARRAY2 | NPY_ARRAY_C_CONTIGUOUS
    );
    if (array == NULL) {
        return NULL;
    }
    if (PyArray_NDIM(array) != 2) {
        Py_DECREF(array);
        PyErr_SetString(PyExc_ValueError, "Native stroke backend expects a 2D array");
        return NULL;
    }
    if (!PyArg_ParseTuple(rect_obj, "llll", &sx, &sy, &sw, &sh)) {
        Py_DECREF(array);
        return NULL;
    }
    sequence = PySequence_Fast(points_obj, "points must be a sequence");
    if (sequence == NULL) {
        Py_DECREF(array);
        return NULL;
    }
    count = PySequence_Fast_GET_SIZE(sequence);
    if (count <= 0) {
        Py_DECREF(sequence);
        PyArray_ResolveWritebackIfCopy(array);
        Py_DECREF(array);
        Py_RETURN_NONE;
    }
    for (i = 0; i < count; i++) {
        PyObject *item = PySequence_Fast_GET_ITEM(sequence, i);
        long x0;
        long y0;
        long x1;
        long y1;
        long steps;
        long step;
        if (!PyArg_ParseTuple(item, "ll", &x1, &y1)) {
            Py_DECREF(sequence);
            Py_DECREF(array);
            return NULL;
        }
        if (i == 0) {
            if (paint_disk_native(array, x1, y1, radius, value, sx, sy, sw, sh, ellipse) < 0) {
                Py_DECREF(sequence);
                Py_DECREF(array);
                return NULL;
            }
            continue;
        }
        item = PySequence_Fast_GET_ITEM(sequence, i - 1);
        if (!PyArg_ParseTuple(item, "ll", &x0, &y0)) {
            Py_DECREF(sequence);
            Py_DECREF(array);
            return NULL;
        }
        steps = (long)ceil(hypot((double)(x1 - x0), (double)(y1 - y0)) / fmax(0.25, radius / 6.0));
        if (steps < 1) {
            steps = 1;
        }
        for (step = 1; step <= steps; step++) {
            double t = (double)step / (double)steps;
            long x = (long)llround(x0 + (x1 - x0) * t);
            long y = (long)llround(y0 + (y1 - y0) * t);
            if (paint_disk_native(array, x, y, radius, value, sx, sy, sw, sh, ellipse) < 0) {
                Py_DECREF(sequence);
                Py_DECREF(array);
                return NULL;
            }
        }
    }
    Py_DECREF(sequence);
    PyArray_ResolveWritebackIfCopy(array);
    Py_DECREF(array);
    Py_RETURN_NONE;
}

static PyMethodDef StrokeMethods[] = {
    {"paint_disks", paint_disks, METH_VARARGS, "Paint sampled stroke disks into a 2D NumPy array."},
    {"paint_disks_pair", paint_disks_pair, METH_VARARGS, "Paint sampled stroke disks into paired content and alpha arrays."},
    {"paint_stroke", paint_stroke, METH_VARARGS, "Paint a linearly interpolated stroke into a 2D NumPy array."},
    {"spacing_dabs", spacing_dabs, METH_VARARGS, "Generate GIMP-style brush-spaced dab centers for one float stroke segment."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef stroke_module = {
    PyModuleDef_HEAD_INIT,
    "_stroke_native",
    "Native stroke rasterization backend.",
    -1,
    StrokeMethods
};

PyMODINIT_FUNC PyInit__stroke_native(void) {
    import_array();
    return PyModule_Create(&stroke_module);
}
