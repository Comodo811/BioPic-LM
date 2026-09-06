#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
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

static int supported_type(int typenum) {
    return typenum == NPY_UINT8 || typenum == NPY_UINT16 || typenum == NPY_INT16 ||
           typenum == NPY_FLOAT32 || typenum == NPY_FLOAT64;
}

static void reflect_index(int *index, int length) {
    if (length <= 1) {
        *index = 0;
        return;
    }
    while (*index < 0 || *index >= length) {
        if (*index < 0) {
            *index = -*index - 1;
        } else {
            *index = 2 * length - *index - 1;
        }
    }
}

static double *gaussian_kernel(double sigma, int *radius_out) {
    int radius = (int)ceil(fmax(0.1, sigma) * 3.0);
    int size = radius * 2 + 1;
    double *kernel = (double *)malloc((size_t)size * sizeof(double));
    if (kernel == NULL) {
        return NULL;
    }
    double sum = 0.0;
    double denom = 2.0 * sigma * sigma;
    for (int i = -radius; i <= radius; ++i) {
        double value = exp(-(double)(i * i) / denom);
        kernel[i + radius] = value;
        sum += value;
    }
    for (int i = 0; i < size; ++i) {
        kernel[i] /= sum;
    }
    *radius_out = radius;
    return kernel;
}

static int gaussian_blur_plane(
    const double *src,
    double *tmp,
    double *dst,
    int width,
    int height,
    double sigma) {
    int radius = 0;
    double *kernel = gaussian_kernel(sigma, &radius);
    if (kernel == NULL) {
        return 0;
    }
    Py_BEGIN_ALLOW_THREADS
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            double sum = 0.0;
            for (int k = -radius; k <= radius; ++k) {
                int sx = x + k;
                reflect_index(&sx, width);
                sum += src[(size_t)y * width + sx] * kernel[k + radius];
            }
            tmp[(size_t)y * width + x] = sum;
        }
    }
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            double sum = 0.0;
            for (int k = -radius; k <= radius; ++k) {
                int sy = y + k;
                reflect_index(&sy, height);
                sum += tmp[(size_t)sy * width + x] * kernel[k + radius];
            }
            dst[(size_t)y * width + x] = sum;
        }
    }
    Py_END_ALLOW_THREADS
    free(kernel);
    return 1;
}

static PyObject *high_pass(PyObject *self, PyObject *args) {
    PyObject *image_arg = NULL;
    double sigma = 2.0;
    double amount = 1.0;
    double threshold = 0.0;
    double halo_suppression = 0.0;
    int luminance_only = 0;
    if (!PyArg_ParseTuple(
            args,
            "Oddddi",
            &image_arg,
            &sigma,
            &amount,
            &threshold,
            &halo_suppression,
            &luminance_only)) {
        return NULL;
    }
    if (sigma <= 0.0) {
        PyErr_SetString(PyExc_ValueError, "sigma must be greater than zero");
        return NULL;
    }
    threshold = 0.0;
    halo_suppression = 0.0;
    luminance_only = 0;
    PyArrayObject *image = (PyArrayObject *)PyArray_FROM_OTF(
        image_arg, NPY_NOTYPE, NPY_ARRAY_IN_ARRAY);
    if (image == NULL) {
        return NULL;
    }
    int ndim = PyArray_NDIM(image);
    int typenum = PyArray_TYPE(image);
    if ((ndim != 2 && ndim != 3) || !supported_type(typenum)) {
        PyErr_SetString(PyExc_TypeError, "unsupported image shape or dtype");
        Py_DECREF(image);
        return NULL;
    }
    int height = (int)PyArray_DIM(image, 0);
    int width = (int)PyArray_DIM(image, 1);
    int channels = ndim == 3 ? (int)PyArray_DIM(image, 2) : 1;
    npy_intp itemsize = PyArray_ITEMSIZE(image);
    size_t plane_count = (size_t)height * width;
    double *plane = (double *)malloc(plane_count * sizeof(double));
    double *tmp = (double *)malloc(plane_count * sizeof(double));
    double *blur = (double *)malloc(plane_count * sizeof(double));
    double *sharp_luma = NULL;
    if (plane == NULL || tmp == NULL || blur == NULL) {
        free(plane);
        free(tmp);
        free(blur);
        Py_DECREF(image);
        return PyErr_NoMemory();
    }
    PyArrayObject *output = (PyArrayObject *)PyArray_NewLikeArray(image, NPY_ANYORDER, NULL, 0);
    if (output == NULL) {
        free(plane);
        free(tmp);
        free(blur);
        Py_DECREF(image);
        return NULL;
    }
    memcpy(PyArray_DATA(output), PyArray_DATA(image), (size_t)PyArray_NBYTES(image));
    const char *src = (const char *)PyArray_DATA(image);
    char *dst = (char *)PyArray_DATA(output);

    if (luminance_only && channels >= 3) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                size_t pixel_index = ((size_t)y * width + x) * channels;
                const char *pixel = src + pixel_index * itemsize;
                double r = read_channel(pixel, typenum);
                double g = read_channel(pixel + itemsize, typenum);
                double b = read_channel(pixel + itemsize * 2, typenum);
                plane[(size_t)y * width + x] = r * 0.2126 + g * 0.7152 + b * 0.0722;
            }
        }
        if (!gaussian_blur_plane(plane, tmp, blur, width, height, sigma)) {
            free(plane);
            free(tmp);
            free(blur);
            Py_DECREF(output);
            Py_DECREF(image);
            return PyErr_NoMemory();
        }
        sharp_luma = plane;
        for (size_t i = 0; i < plane_count; ++i) {
            double detail = plane[i] - blur[i];
            if (threshold > 0.0 && fabs(detail) < threshold) {
                detail = 0.0;
            }
            sharp_luma[i] = clamp01(plane[i] + detail * amount);
        }
        if (halo_suppression > 0.0) {
            if (!gaussian_blur_plane(sharp_luma, tmp, blur, width, height, halo_suppression)) {
                free(plane);
                free(tmp);
                free(blur);
                Py_DECREF(output);
                Py_DECREF(image);
                return PyErr_NoMemory();
            }
            for (size_t i = 0; i < plane_count; ++i) {
                sharp_luma[i] = sharp_luma[i] * 0.75 + blur[i] * 0.25;
            }
        }
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                size_t idx = (size_t)y * width + x;
                size_t pixel_index = idx * channels;
                const char *in_pixel = src + pixel_index * itemsize;
                char *out_pixel = dst + pixel_index * itemsize;
                double delta = sharp_luma[idx] - (
                    read_channel(in_pixel, typenum) * 0.2126 +
                    read_channel(in_pixel + itemsize, typenum) * 0.7152 +
                    read_channel(in_pixel + itemsize * 2, typenum) * 0.0722);
                for (int c = 0; c < 3; ++c) {
                    write_channel(
                        out_pixel + c * itemsize,
                        typenum,
                        read_channel(in_pixel + c * itemsize, typenum) + delta);
                }
            }
        }
    } else {
        int process_channels = channels;
        if (channels >= 4) {
            process_channels = 3;
        }
        for (int c = 0; c < process_channels; ++c) {
            for (int y = 0; y < height; ++y) {
                for (int x = 0; x < width; ++x) {
                    size_t pixel_index = ((size_t)y * width + x) * channels + c;
                    plane[(size_t)y * width + x] = read_channel(src + pixel_index * itemsize, typenum);
                }
            }
            if (!gaussian_blur_plane(plane, tmp, blur, width, height, sigma)) {
                free(plane);
                free(tmp);
                free(blur);
                Py_DECREF(output);
                Py_DECREF(image);
                return PyErr_NoMemory();
            }
            for (size_t i = 0; i < plane_count; ++i) {
                double detail = plane[i] - blur[i];
                double over = clamp01(0.5 + 0.5 * detail);
                double inverse_gamma = 1.0 / 2.2;
                double perceptual = pow(over, inverse_gamma);
                double neutral = pow(0.5, inverse_gamma);
                double contrasted = (perceptual - neutral) * amount + neutral;
                double high_pass_layer = pow(clamp01(contrasted), 2.2);
                tmp[i] = clamp01(plane[i] + 2.0 * (high_pass_layer - 0.5));
            }
            for (int y = 0; y < height; ++y) {
                for (int x = 0; x < width; ++x) {
                    size_t pixel_index = ((size_t)y * width + x) * channels + c;
                    write_channel(dst + pixel_index * itemsize, typenum, tmp[(size_t)y * width + x]);
                }
            }
        }
    }
    free(plane);
    free(tmp);
    free(blur);
    Py_DECREF(image);
    return (PyObject *)output;
}

static PyObject *uniform_background(PyObject *self, PyObject *args) {
    PyObject *image_arg = NULL;
    PyObject *mask_arg = NULL;
    int transition_px = 0;
    if (!PyArg_ParseTuple(args, "OOi", &image_arg, &mask_arg, &transition_px)) {
        return NULL;
    }
    PyArrayObject *image = (PyArrayObject *)PyArray_FROM_OTF(
        image_arg, NPY_NOTYPE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *mask = (PyArrayObject *)PyArray_FROM_OTF(
        mask_arg, NPY_UINT8, NPY_ARRAY_IN_ARRAY);
    if (image == NULL || mask == NULL) {
        Py_XDECREF(image);
        Py_XDECREF(mask);
        return NULL;
    }
    int ndim = PyArray_NDIM(image);
    int typenum = PyArray_TYPE(image);
    if (
        (ndim != 2 && ndim != 3) ||
        PyArray_NDIM(mask) != 2 ||
        PyArray_DIM(mask, 0) != PyArray_DIM(image, 0) ||
        PyArray_DIM(mask, 1) != PyArray_DIM(image, 1) ||
        !supported_type(typenum)) {
        PyErr_SetString(PyExc_TypeError, "unsupported image or mask");
        Py_DECREF(image);
        Py_DECREF(mask);
        return NULL;
    }
    int height = (int)PyArray_DIM(image, 0);
    int width = (int)PyArray_DIM(image, 1);
    int channels = ndim == 3 ? (int)PyArray_DIM(image, 2) : 1;
    npy_intp itemsize = PyArray_ITEMSIZE(image);
    PyArrayObject *background = (PyArrayObject *)PyArray_NewLikeArray(image, NPY_ANYORDER, NULL, 0);
    npy_intp alpha_dims[2] = {height, width};
    PyArrayObject *alpha = (PyArrayObject *)PyArray_SimpleNew(2, alpha_dims, NPY_FLOAT32);
    npy_intp color_dims[1] = {channels};
    PyArrayObject *color = (PyArrayObject *)PyArray_SimpleNew(1, color_dims, NPY_FLOAT64);
    if (background == NULL || alpha == NULL || color == NULL) {
        Py_XDECREF(background);
        Py_XDECREF(alpha);
        Py_XDECREF(color);
        Py_DECREF(image);
        Py_DECREF(mask);
        return NULL;
    }
    const char *src = (const char *)PyArray_DATA(image);
    const uint8_t *mask_data = (const uint8_t *)PyArray_DATA(mask);
    char *bg = (char *)PyArray_DATA(background);
    float *alpha_data = (float *)PyArray_DATA(alpha);
    double *color_data = (double *)PyArray_DATA(color);
    for (int c = 0; c < channels; ++c) {
        color_data[c] = 0.0;
    }
    int radius = transition_px > 0 ? transition_px : 0;
    if (radius == 0 && typenum == NPY_UINT16 && channels == 1) {
        const uint16_t *src16 = (const uint16_t *)src;
        const uint8_t *mask8 = mask_data;
        uint16_t *bg16 = (uint16_t *)bg;
        uint64_t sum = 0;
        size_t outside_count = 0;
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                size_t idx = (size_t)y * width + x;
                if (mask8[idx] == 0) {
                    sum += (uint64_t)src16[idx];
                    ++outside_count;
                }
            }
        }
        uint16_t bg_value = 0;
        if (outside_count > 0) {
            bg_value = (uint16_t)((sum + outside_count / 2) / outside_count);
            color_data[0] = (double)bg_value / 65535.0;
        }
        Py_BEGIN_ALLOW_THREADS
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                size_t idx = (size_t)y * width + x;
                bg16[idx] = bg_value;
                alpha_data[idx] = mask8[idx] == 0 ? 1.0f : 0.0f;
            }
        }
        Py_END_ALLOW_THREADS
        Py_DECREF(image);
        Py_DECREF(mask);
        return Py_BuildValue("NNN", background, alpha, color);
    }
    size_t outside_count = 0;
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            size_t idx = (size_t)y * width + x;
            if (mask_data[idx] == 0) {
                ++outside_count;
                for (int c = 0; c < channels; ++c) {
                    color_data[c] += read_channel(src + (idx * channels + c) * itemsize, typenum);
                }
            }
        }
    }
    if (outside_count == 0) {
        outside_count = 1;
    }
    for (int c = 0; c < channels; ++c) {
        color_data[c] /= (double)outside_count;
    }
    int radius2 = radius * radius;
    int min_x = width;
    int min_y = height;
    int max_x = -1;
    int max_y = -1;
    if (radius > 0) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                size_t idx = (size_t)y * width + x;
                if (mask_data[idx] != 0) {
                    if (x < min_x) {
                        min_x = x;
                    }
                    if (x > max_x) {
                        max_x = x;
                    }
                    if (y < min_y) {
                        min_y = y;
                    }
                    if (y > max_y) {
                        max_y = y;
                    }
                }
            }
        }
        min_x -= radius;
        min_y -= radius;
        max_x += radius;
        max_y += radius;
    }
    Py_BEGIN_ALLOW_THREADS
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            size_t idx = (size_t)y * width + x;
            char *out_pixel = bg + idx * channels * itemsize;
            for (int c = 0; c < channels; ++c) {
                write_channel(out_pixel + c * itemsize, typenum, color_data[c]);
            }
            alpha_data[idx] = mask_data[idx] == 0 ? 1.0f : 0.0f;
            if (mask_data[idx] != 0 || radius <= 0) {
                continue;
            }
            if (x < min_x || x > max_x || y < min_y || y > max_y) {
                continue;
            }
            int best_d2 = radius2 + 1;
            int best_x = -1;
            int best_y = -1;
            for (int dy = -radius; dy <= radius; ++dy) {
                int sy = y + dy;
                if (sy < 0 || sy >= height) {
                    continue;
                }
                for (int dx = -radius; dx <= radius; ++dx) {
                    int sx = x + dx;
                    if (sx < 0 || sx >= width) {
                        continue;
                    }
                    int d2 = dx * dx + dy * dy;
                    if (d2 < best_d2 && d2 <= radius2 && mask_data[(size_t)sy * width + sx] != 0) {
                        best_d2 = d2;
                        best_x = sx;
                        best_y = sy;
                    }
                }
            }
            if (best_x >= 0) {
                double t = sqrt((double)best_d2) / (double)radius;
                t = t * t * (3.0 - 2.0 * t);
                size_t ref_idx = (size_t)best_y * width + best_x;
                for (int c = 0; c < channels; ++c) {
                    double ref = read_channel(src + (ref_idx * channels + c) * itemsize, typenum);
                    double value = ref * (1.0 - t) + color_data[c] * t;
                    write_channel(out_pixel + c * itemsize, typenum, value);
                }
            }
        }
    }
    Py_END_ALLOW_THREADS
    Py_DECREF(image);
    Py_DECREF(mask);
    return Py_BuildValue("NNN", background, alpha, color);
}

static int compare_double(const void *a, const void *b) {
    const double da = *(const double *)a;
    const double db = *(const double *)b;
    return (da > db) - (da < db);
}

static double local_median_channel(
    const char *src,
    int typenum,
    npy_intp itemsize,
    int width,
    int height,
    int channels,
    int x,
    int y,
    int c,
    int radius) {
    int max_count = (radius * 2 + 1) * (radius * 2 + 1);
    double values[25];
    if (max_count > 25) {
        max_count = 25;
        radius = 2;
    }
    int count = 0;
    for (int dy = -radius; dy <= radius; ++dy) {
        int sy = y + dy;
        reflect_index(&sy, height);
        for (int dx = -radius; dx <= radius; ++dx) {
            int sx = x + dx;
            reflect_index(&sx, width);
            size_t pixel_index = ((size_t)sy * width + sx) * channels + c;
            values[count++] = read_channel(src + pixel_index * itemsize, typenum);
        }
    }
    for (int i = 1; i < count; ++i) {
        double value = values[i];
        int j = i - 1;
        while (j >= 0 && values[j] > value) {
            values[j + 1] = values[j];
            --j;
        }
        values[j + 1] = value;
    }
    double result = values[count / 2];
    return result;
}

static PyObject *noise_reduction(PyObject *self, PyObject *args) {
    PyObject *image_arg = NULL;
    double luminance_strength = 0.08;
    double chroma_strength = 0.04;
    int impulse_radius = 1;
    int preserve_edges = 1;
    if (!PyArg_ParseTuple(
            args,
            "Oddii",
            &image_arg,
            &luminance_strength,
            &chroma_strength,
            &impulse_radius,
            &preserve_edges)) {
        return NULL;
    }
    PyArrayObject *image = (PyArrayObject *)PyArray_FROM_OTF(
        image_arg, NPY_NOTYPE, NPY_ARRAY_IN_ARRAY);
    if (image == NULL) {
        return NULL;
    }
    int ndim = PyArray_NDIM(image);
    int typenum = PyArray_TYPE(image);
    if ((ndim != 2 && ndim != 3) || !supported_type(typenum)) {
        PyErr_SetString(PyExc_TypeError, "unsupported image shape or dtype");
        Py_DECREF(image);
        return NULL;
    }
    int height = (int)PyArray_DIM(image, 0);
    int width = (int)PyArray_DIM(image, 1);
    int channels = ndim == 3 ? (int)PyArray_DIM(image, 2) : 1;
    npy_intp itemsize = PyArray_ITEMSIZE(image);
    PyArrayObject *output = (PyArrayObject *)PyArray_NewLikeArray(image, NPY_ANYORDER, NULL, 0);
    if (output == NULL) {
        Py_DECREF(image);
        return NULL;
    }
    memcpy(PyArray_DATA(output), PyArray_DATA(image), (size_t)PyArray_NBYTES(image));
    const char *src = (const char *)PyArray_DATA(image);
    char *dst = (char *)PyArray_DATA(output);
    int radius_luma = 1;
    int radius_chroma = preserve_edges ? 1 : 2;
    double sigma_luma = fmax(0.002, luminance_strength);
    double sigma_chroma = fmax(0.002, chroma_strength);
    double range_luma = 2.0 * sigma_luma * sigma_luma;
    double range_chroma = 2.0 * sigma_chroma * sigma_chroma;
    int impulse_r = impulse_radius > 0 ? impulse_radius : 0;
    if (impulse_r > 2) {
        impulse_r = 2;
    }

    Py_BEGIN_ALLOW_THREADS
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            size_t idx = (size_t)y * width + x;
            const char *center = src + idx * channels * itemsize;
            char *out = dst + idx * channels * itemsize;
            if (channels >= 3) {
                double r0 = read_channel(center, typenum);
                double g0 = read_channel(center + itemsize, typenum);
                double b0 = read_channel(center + itemsize * 2, typenum);
                if (impulse_r > 0) {
                    double mr = local_median_channel(src, typenum, itemsize, width, height, channels, x, y, 0, impulse_r);
                    double mg = local_median_channel(src, typenum, itemsize, width, height, channels, x, y, 1, impulse_r);
                    double mb = local_median_channel(src, typenum, itemsize, width, height, channels, x, y, 2, impulse_r);
                    double deviation = fmax(fabs(r0 - mr), fmax(fabs(g0 - mg), fabs(b0 - mb)));
                    if (deviation > fmax(0.08, sigma_luma * 2.5)) {
                        r0 = mr;
                        g0 = mg;
                        b0 = mb;
                    }
                }
                double l0 = r0 * 0.2126 + g0 * 0.7152 + b0 * 0.0722;
                double cr0 = r0 - l0;
                double cg0 = g0 - l0;
                double cb0 = b0 - l0;
                double lsum = 0.0;
                double lweight = 0.0;
                double crsum = 0.0;
                double cgsum = 0.0;
                double cbsum = 0.0;
                double cweight = 0.0;
                for (int dy = -radius_chroma; dy <= radius_chroma; ++dy) {
                    int sy = y + dy;
                    reflect_index(&sy, height);
                    for (int dx = -radius_chroma; dx <= radius_chroma; ++dx) {
                        int sx = x + dx;
                        reflect_index(&sx, width);
                        double spatial = (double)(dx * dx + dy * dy);
                        size_t nidx = (size_t)sy * width + sx;
                        const char *neighbor = src + nidx * channels * itemsize;
                        double rn = read_channel(neighbor, typenum);
                        double gn = read_channel(neighbor + itemsize, typenum);
                        double bn = read_channel(neighbor + itemsize * 2, typenum);
                        double ln = rn * 0.2126 + gn * 0.7152 + bn * 0.0722;
                        if (abs(dx) <= radius_luma && abs(dy) <= radius_luma) {
                            double wd = exp(-spatial / 8.0);
                            double wr = preserve_edges ? exp(-((ln - l0) * (ln - l0)) / range_luma) : 1.0;
                            double w = wd * wr;
                            lsum += ln * w;
                            lweight += w;
                        }
                        double crn = rn - ln;
                        double cgn = gn - ln;
                        double cbn = bn - ln;
                        double cdiff =
                            (crn - cr0) * (crn - cr0) +
                            (cgn - cg0) * (cgn - cg0) +
                            (cbn - cb0) * (cbn - cb0);
                        double cw = exp(-spatial / 8.0) * exp(-cdiff / range_chroma);
                        crsum += crn * cw;
                        cgsum += cgn * cw;
                        cbsum += cbn * cw;
                        cweight += cw;
                    }
                }
                double l = lweight > 0.0 ? lsum / lweight : l0;
                double cr = cweight > 0.0 ? crsum / cweight : cr0;
                double cg = cweight > 0.0 ? cgsum / cweight : cg0;
                double cb = cweight > 0.0 ? cbsum / cweight : cb0;
                double lmix = fmin(fmax(luminance_strength * 8.0, 0.0), 1.0);
                double cmix = fmin(fmax(chroma_strength * 10.0, 0.0), 1.0);
                l = l0 * (1.0 - lmix) + l * lmix;
                cr = cr0 * (1.0 - cmix) + cr * cmix;
                cg = cg0 * (1.0 - cmix) + cg * cmix;
                cb = cb0 * (1.0 - cmix) + cb * cmix;
                write_channel(out, typenum, l + cr);
                write_channel(out + itemsize, typenum, l + cg);
                write_channel(out + itemsize * 2, typenum, l + cb);
            } else {
                if (typenum == NPY_UINT16) {
                    const uint16_t *src16 = (const uint16_t *)src;
                    uint16_t *dst16 = (uint16_t *)dst;
                    double center_value = src16[idx] / 65535.0;
                    double working_center = center_value;
                    if (impulse_r > 0) {
                        int left = x - 1;
                        int right = x + 1;
                        int up = y - 1;
                        int down = y + 1;
                        reflect_index(&left, width);
                        reflect_index(&right, width);
                        reflect_index(&up, height);
                        reflect_index(&down, height);
                        double neighbor_mean = (
                            src16[(size_t)y * width + left] +
                            src16[(size_t)y * width + right] +
                            src16[(size_t)up * width + x] +
                            src16[(size_t)down * width + x]) /
                            262140.0;
                        if (fabs(center_value - neighbor_mean) > fmax(0.12, sigma_luma * 3.5)) {
                            working_center = neighbor_mean;
                        }
                    }
                    double sum = 0.0;
                    double weight = 0.0;
                    double edge_threshold = fmax(0.015, sigma_luma * 3.0);
                    for (int dy = -radius_luma; dy <= radius_luma; ++dy) {
                        int sy = y + dy;
                        reflect_index(&sy, height);
                        for (int dx = -radius_luma; dx <= radius_luma; ++dx) {
                            int sx = x + dx;
                            reflect_index(&sx, width);
                            double spatial = (double)(dx * dx + dy * dy);
                            double value = src16[(size_t)sy * width + sx] / 65535.0;
                            if (preserve_edges && fabs(value - working_center) > edge_threshold) {
                                continue;
                            }
                            double w = spatial > 1.5 ? 0.7788007830714049 : 0.8824969025845955;
                            if (spatial == 0.0) {
                                w = 1.0;
                            }
                            sum += value * w;
                            weight += w;
                        }
                    }
                    double filtered = weight > 0.0 ? sum / weight : working_center;
                    double mix = fmin(fmax(luminance_strength * 8.0, 0.0), 1.0);
                    double out_value = clamp01(working_center * (1.0 - mix) + filtered * mix);
                    dst16[idx] = (uint16_t)lrint(out_value * 65535.0);
                } else {
                    double center_value = read_channel(center, typenum);
                    double working_center = center_value;
                    if (impulse_r > 0) {
                        int left = x - 1;
                        int right = x + 1;
                        int up = y - 1;
                        int down = y + 1;
                        reflect_index(&left, width);
                        reflect_index(&right, width);
                        reflect_index(&up, height);
                        reflect_index(&down, height);
                        double neighbor_mean = (
                            read_channel(src + ((size_t)y * width + left) * itemsize, typenum) +
                            read_channel(src + ((size_t)y * width + right) * itemsize, typenum) +
                            read_channel(src + ((size_t)up * width + x) * itemsize, typenum) +
                            read_channel(src + ((size_t)down * width + x) * itemsize, typenum)) *
                            0.25;
                        if (fabs(center_value - neighbor_mean) > fmax(0.12, sigma_luma * 3.5)) {
                            working_center = neighbor_mean;
                        }
                    }
                    double sum = 0.0;
                    double weight = 0.0;
                    double edge_threshold = fmax(0.015, sigma_luma * 3.0);
                    for (int dy = -radius_luma; dy <= radius_luma; ++dy) {
                        int sy = y + dy;
                        reflect_index(&sy, height);
                        for (int dx = -radius_luma; dx <= radius_luma; ++dx) {
                            int sx = x + dx;
                            reflect_index(&sx, width);
                            double spatial = (double)(dx * dx + dy * dy);
                            double value = read_channel(src + ((size_t)sy * width + sx) * itemsize, typenum);
                            if (preserve_edges && fabs(value - working_center) > edge_threshold) {
                                continue;
                            }
                            double w = spatial > 1.5 ? 0.7788007830714049 : 0.8824969025845955;
                            if (spatial == 0.0) {
                                w = 1.0;
                            }
                            sum += value * w;
                            weight += w;
                        }
                    }
                    double filtered = weight > 0.0 ? sum / weight : working_center;
                    double mix = fmin(fmax(luminance_strength * 8.0, 0.0), 1.0);
                    write_channel(out, typenum, working_center * (1.0 - mix) + filtered * mix);
                }
            }
        }
    }
    Py_END_ALLOW_THREADS
    Py_DECREF(image);
    return (PyObject *)output;
}

static PyMethodDef Methods[] = {
    {"high_pass", high_pass, METH_VARARGS, "Apply high-pass sharpening."},
    {"noise_reduction", noise_reduction, METH_VARARGS, "Apply RawTherapee-inspired luma/chroma noise reduction."},
    {"uniform_background", uniform_background, METH_VARARGS, "Create uniform background layer outside a selection."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_adjustments_native",
    NULL,
    -1,
    Methods,
};

PyMODINIT_FUNC PyInit__adjustments_native(void) {
    import_array();
    return PyModule_Create(&moduledef);
}
