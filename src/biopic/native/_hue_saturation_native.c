#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#define NPY_NO_DEPRECATED_API NPY_1_20_API_VERSION
#include <numpy/arrayobject.h>

static double clamp01(double value) {
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

static double wrap01(double value) {
    value = fmod(value, 1.0);
    if (value < 0.0) {
        value += 1.0;
    }
    return value;
}

static double read_channel(const char *ptr, int typenum) {
    switch (typenum) {
        case NPY_UINT8:
            return ((const uint8_t *)ptr)[0] / 255.0;
        case NPY_UINT16:
            return ((const uint16_t *)ptr)[0] / 65535.0;
        case NPY_INT16:
            return (((const int16_t *)ptr)[0] + 32768.0) / 65535.0;
        case NPY_FLOAT32:
            return clamp01((double)((const float *)ptr)[0]);
        case NPY_FLOAT64:
            return clamp01(((const double *)ptr)[0]);
        default:
            return 0.0;
    }
}

static void write_channel(char *ptr, int typenum, double value) {
    value = clamp01(value);
    switch (typenum) {
        case NPY_UINT8:
            ((uint8_t *)ptr)[0] = (uint8_t)lrint(value * 255.0);
            break;
        case NPY_UINT16:
            ((uint16_t *)ptr)[0] = (uint16_t)lrint(value * 65535.0);
            break;
        case NPY_INT16:
            ((int16_t *)ptr)[0] = (int16_t)lrint(value * 65535.0 - 32768.0);
            break;
        case NPY_FLOAT32:
            ((float *)ptr)[0] = (float)value;
            break;
        case NPY_FLOAT64:
            ((double *)ptr)[0] = value;
            break;
    }
}

static void rgb_to_hsl(double r, double g, double b, double *h, double *s, double *l) {
    double maxv = fmax(r, fmax(g, b));
    double minv = fmin(r, fmin(g, b));
    double delta = maxv - minv;
    *l = (maxv + minv) * 0.5;
    if (delta <= 1e-12) {
        *h = 0.0;
        *s = 0.0;
        return;
    }
    *s = (*l <= 0.5) ? delta / (maxv + minv) : delta / (2.0 - maxv - minv);
    if (maxv == r) {
        *h = (g - b) / delta + (g < b ? 6.0 : 0.0);
    } else if (maxv == g) {
        *h = (b - r) / delta + 2.0;
    } else {
        *h = (r - g) / delta + 4.0;
    }
    *h /= 6.0;
}

static double hue_to_rgb(double p, double q, double t) {
    t = wrap01(t);
    if (t < 1.0 / 6.0) {
        return p + (q - p) * 6.0 * t;
    }
    if (t < 0.5) {
        return q;
    }
    if (t < 2.0 / 3.0) {
        return p + (q - p) * (2.0 / 3.0 - t) * 6.0;
    }
    return p;
}

static void hsl_to_rgb(double h, double s, double l, double *r, double *g, double *b) {
    if (s <= 1e-12) {
        *r = l;
        *g = l;
        *b = l;
        return;
    }
    double q = (l < 0.5) ? l * (1.0 + s) : l + s - l * s;
    double p = 2.0 * l - q;
    *r = hue_to_rgb(p, q, h + 1.0 / 3.0);
    *g = hue_to_rgb(p, q, h);
    *b = hue_to_rgb(p, q, h - 1.0 / 3.0);
}

static double map_lightness(double l, const double *lightness, int range) {
    double adjustment = lightness[0] + lightness[range];
    if (adjustment < 0.0) {
        return clamp01(l * (adjustment + 1.0));
    }
    return clamp01(l + adjustment * (1.0 - l));
}

static int is_master_saturation_only(
    const double *hue,
    const double *lightness,
    const double *saturation,
    double overlap_percent,
    double *scale_out) {
    if (fabs(overlap_percent) > 1e-12) {
        return 0;
    }
    for (int i = 0; i < 7; ++i) {
        if (fabs(hue[i]) > 1e-12 || fabs(lightness[i]) > 1e-12) {
            return 0;
        }
        if (i > 0 && fabs(saturation[i]) > 1e-12) {
            return 0;
        }
    }
    *scale_out = saturation[0] + 1.0;
    return 1;
}

static void apply_master_saturation_only(
    PyArrayObject *output,
    int typenum,
    double saturation_scale) {
    const npy_intp height = PyArray_DIM(output, 0);
    const npy_intp width = PyArray_DIM(output, 1);
    const npy_intp channels = PyArray_DIM(output, 2);
    const npy_intp itemsize = PyArray_ITEMSIZE(output);
    char *data = (char *)PyArray_DATA(output);
    for (npy_intp y = 0; y < height; ++y) {
        for (npy_intp x = 0; x < width; ++x) {
            char *pixel = data + ((y * width + x) * channels * itemsize);
            double r = read_channel(pixel, typenum);
            double g = read_channel(pixel + itemsize, typenum);
            double b = read_channel(pixel + itemsize * 2, typenum);
            double maxv = fmax(r, fmax(g, b));
            double minv = fmin(r, fmin(g, b));
            double delta = maxv - minv;
            double l = (maxv + minv) * 0.5;
            if (delta <= 1e-12) {
                continue;
            }
            double s = (l <= 0.5) ? delta / (maxv + minv) : delta / (2.0 - maxv - minv);
            double effective_scale = saturation_scale;
            if (s * saturation_scale > 1.0) {
                effective_scale = 1.0 / s;
            }
            r = l + (r - l) * effective_scale;
            g = l + (g - l) * effective_scale;
            b = l + (b - l) * effective_scale;
            write_channel(pixel, typenum, r);
            write_channel(pixel + itemsize, typenum, g);
            write_channel(pixel + itemsize * 2, typenum, b);
        }
    }
}

static PyObject *apply_hue_saturation(PyObject *self, PyObject *args) {
    PyObject *image_arg = NULL;
    PyObject *hue_arg = NULL;
    PyObject *lightness_arg = NULL;
    PyObject *saturation_arg = NULL;
    double overlap_percent = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "OOOOd",
            &image_arg,
            &hue_arg,
            &lightness_arg,
            &saturation_arg,
            &overlap_percent)) {
        return NULL;
    }
    PyArrayObject *image = (PyArrayObject *)PyArray_FROM_OTF(
        image_arg, NPY_NOTYPE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *hue = (PyArrayObject *)PyArray_FROM_OTF(
        hue_arg, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *lightness = (PyArrayObject *)PyArray_FROM_OTF(
        lightness_arg, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *saturation = (PyArrayObject *)PyArray_FROM_OTF(
        saturation_arg, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    if (image == NULL || hue == NULL || lightness == NULL || saturation == NULL) {
        Py_XDECREF(image);
        Py_XDECREF(hue);
        Py_XDECREF(lightness);
        Py_XDECREF(saturation);
        return NULL;
    }
    if (
        PyArray_NDIM(image) != 3 ||
        PyArray_DIM(image, 2) < 3 ||
        PyArray_SIZE(hue) < 7 ||
        PyArray_SIZE(lightness) < 7 ||
        PyArray_SIZE(saturation) < 7) {
        PyErr_SetString(PyExc_ValueError, "expected HxWxC image and three arrays of length 7");
        Py_DECREF(image);
        Py_DECREF(hue);
        Py_DECREF(lightness);
        Py_DECREF(saturation);
        return NULL;
    }
    int typenum = PyArray_TYPE(image);
    if (
        typenum != NPY_UINT8 &&
        typenum != NPY_UINT16 &&
        typenum != NPY_INT16 &&
        typenum != NPY_FLOAT32 &&
        typenum != NPY_FLOAT64) {
        PyErr_SetString(PyExc_TypeError, "unsupported dtype");
        Py_DECREF(image);
        Py_DECREF(hue);
        Py_DECREF(lightness);
        Py_DECREF(saturation);
        return NULL;
    }
    PyArrayObject *output = (PyArrayObject *)PyArray_NewLikeArray(image, NPY_ANYORDER, NULL, 0);
    if (output == NULL) {
        Py_DECREF(image);
        Py_DECREF(hue);
        Py_DECREF(lightness);
        Py_DECREF(saturation);
        return NULL;
    }
    memcpy(PyArray_DATA(output), PyArray_DATA(image), (size_t)PyArray_NBYTES(image));
    const double *hue_values = (const double *)PyArray_DATA(hue);
    const double *lightness_values = (const double *)PyArray_DATA(lightness);
    const double *saturation_values = (const double *)PyArray_DATA(saturation);
    const npy_intp height = PyArray_DIM(image, 0);
    const npy_intp width = PyArray_DIM(image, 1);
    const npy_intp channels = PyArray_DIM(image, 2);
    const npy_intp itemsize = PyArray_ITEMSIZE(image);
    char *data = (char *)PyArray_DATA(output);
    double overlap = fmin(fmax(overlap_percent, 0.0), 100.0) / 100.0 / 2.0;
    double master_saturation_scale = 1.0;

    Py_BEGIN_ALLOW_THREADS
    if (is_master_saturation_only(
            hue_values,
            lightness_values,
            saturation_values,
            overlap_percent,
            &master_saturation_scale)) {
        apply_master_saturation_only(output, typenum, master_saturation_scale);
        goto done;
    }
    for (npy_intp y = 0; y < height; ++y) {
        for (npy_intp x = 0; x < width; ++x) {
            char *pixel = data + ((y * width + x) * channels * itemsize);
            double r = read_channel(pixel, typenum);
            double g = read_channel(pixel + itemsize, typenum);
            double b = read_channel(pixel + itemsize * 2, typenum);
            double h, s, l;
            rgb_to_hsl(r, g, b, &h, &s, &l);
            if (s <= 0.0) {
                l = map_lightness(l, lightness_values, 0);
                hsl_to_rgb(h, s, l, &r, &g, &b);
                write_channel(pixel, typenum, r);
                write_channel(pixel + itemsize, typenum, g);
                write_channel(pixel + itemsize * 2, typenum, b);
                continue;
            }
            double h6 = h * 6.0;
            int primary = 0;
            int secondary = 0;
            int use_secondary = 0;
            double primary_weight = 1.0;
            double secondary_weight = 0.0;
            for (int hue_counter = 0; hue_counter < 7; ++hue_counter) {
                double threshold = (double)hue_counter + 0.5;
                if (h6 < threshold + overlap) {
                    primary = hue_counter;
                    if (overlap > 0.0 && h6 > threshold - overlap) {
                        use_secondary = 1;
                        secondary = hue_counter + 1;
                        secondary_weight = (h6 - threshold + overlap) / (2.0 * overlap);
                        primary_weight = 1.0 - secondary_weight;
                    }
                    break;
                }
            }
            if (primary >= 6) {
                primary = 0;
            }
            if (secondary >= 6) {
                secondary = 0;
            }
            int primary_range = primary + 1;
            if (use_secondary) {
                int secondary_range = secondary + 1;
                double mixed_hue =
                    hue_values[primary_range] * primary_weight +
                    hue_values[secondary_range] * secondary_weight;
                h = wrap01(h + (hue_values[0] + mixed_hue) / 2.0);
                double s_primary = clamp01(s * (saturation_values[0] + saturation_values[primary_range] + 1.0));
                double s_secondary = clamp01(s * (saturation_values[0] + saturation_values[secondary_range] + 1.0));
                double l_primary = map_lightness(l, lightness_values, primary_range);
                double l_secondary = map_lightness(l, lightness_values, secondary_range);
                s = clamp01(s_primary * primary_weight + s_secondary * secondary_weight);
                l = clamp01(l_primary * primary_weight + l_secondary * secondary_weight);
            } else {
                h = wrap01(h + (hue_values[0] + hue_values[primary_range]) / 2.0);
                s = clamp01(s * (saturation_values[0] + saturation_values[primary_range] + 1.0));
                l = map_lightness(l, lightness_values, primary_range);
            }
            hsl_to_rgb(h, s, l, &r, &g, &b);
            write_channel(pixel, typenum, r);
            write_channel(pixel + itemsize, typenum, g);
            write_channel(pixel + itemsize * 2, typenum, b);
        }
    }
done:
    Py_END_ALLOW_THREADS
    Py_DECREF(image);
    Py_DECREF(hue);
    Py_DECREF(lightness);
    Py_DECREF(saturation);
    return (PyObject *)output;
}

static PyMethodDef HueSaturationMethods[] = {
    {"apply_hue_saturation", apply_hue_saturation, METH_VARARGS, "Apply GIMP-style hue/saturation."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_hue_saturation_native",
    NULL,
    -1,
    HueSaturationMethods,
};

PyMODINIT_FUNC PyInit__hue_saturation_native(void) {
    import_array();
    return PyModule_Create(&moduledef);
}
