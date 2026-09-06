"""Reusable widgets and helpers for tonal correction dialogs."""

from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class _LevelsHistogramWidget(QWidget):
    """Compact 256-bin histogram preview for the Levels dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(132)
        self._histogram = np.zeros(256, dtype=np.float32)
        self._logarithmic = False

    def set_logarithmic(self, logarithmic: bool) -> None:
        self._logarithmic = bool(logarithmic)
        self.update()

    def set_pixels(self, pixels: np.ndarray, channel: str) -> None:
        values = _levels_channel_values(pixels, channel)
        if values.size == 0:
            self._histogram = np.zeros(256, dtype=np.float32)
        else:
            self._histogram = np.histogram(
                np.clip(values, 0.0, 1.0),
                bins=256,
                range=(0.0, 1.0),
            )[0].astype(np.float32)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 24))
        painter.setPen(QColor(78, 78, 78))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        hist = np.log1p(self._histogram) if self._logarithmic else self._histogram
        maximum = float(hist.max()) if hist.size else 0.0
        if maximum <= 0.0:
            painter.end()
            return
        width = max(1, self.width() - 2)
        height = max(1, self.height() - 2)
        painter.setPen(QColor(190, 190, 190))
        for index, count in enumerate(hist):
            x = 1 + int(round(index * (width - 1) / 255.0))
            bar_height = int(round(float(count) / maximum * height))
            painter.drawLine(x, self.height() - 2, x, self.height() - 2 - bar_height)
        painter.end()


class _LevelsInputWidget(QWidget):
    """Histogram with GIMP-style input black, gamma, and white markers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(176)
        self._histogram = np.zeros(256, dtype=np.float32)
        self._logarithmic = False
        self._black = 0
        self._white = 255
        self._gamma = 1.0
        self._dragging: str | None = None
        self.on_values_changed: object = None

    def values(self) -> tuple[int, float, int]:
        return self._black, self._gamma, self._white

    def set_values(self, black: int, gamma: float, white: int, *, emit: bool = True) -> None:
        black = int(np.clip(black, 0, 254))
        white = int(np.clip(white, 1, 255))
        if black >= white:
            if black >= 254:
                black = white - 1
            else:
                white = black + 1
        self._black = black
        self._white = white
        self._gamma = float(np.clip(gamma, 0.1, 10.0))
        if emit:
            self._emit_values_changed()
        self.update()

    def set_logarithmic(self, logarithmic: bool) -> None:
        self._logarithmic = bool(logarithmic)
        self.update()

    def set_pixels(self, pixels: np.ndarray, channel: str) -> None:
        values = _levels_channel_values(pixels, channel)
        if values.size == 0:
            self._histogram = np.zeros(256, dtype=np.float32)
        else:
            self._histogram = np.histogram(
                np.clip(values, 0.0, 1.0),
                bins=256,
                range=(0.0, 1.0),
            )[0].astype(np.float32)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 24))
        hist_rect = self._histogram_rect()
        painter.setPen(QColor(78, 78, 78))
        painter.drawRect(hist_rect)
        self._draw_histogram(painter, hist_rect)
        self._draw_input_gradient(painter, hist_rect)
        self._draw_marker(painter, self._x_for_value(self._black, hist_rect), "black")
        self._draw_marker(painter, self._x_for_gamma(hist_rect), "gamma")
        self._draw_marker(painter, self._x_for_value(self._white, hist_rect), "white")
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hist_rect = self._histogram_rect()
        x = float(event.position().x())
        candidates = {
            "black": abs(x - self._x_for_value(self._black, hist_rect)),
            "gamma": abs(x - self._x_for_gamma(hist_rect)),
            "white": abs(x - self._x_for_value(self._white, hist_rect)),
        }
        self._dragging = min(candidates, key=candidates.get)
        self._set_marker_from_x(self._dragging, x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        self._set_marker_from_x(self._dragging, float(event.position().x()))

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._dragging = None

    def _histogram_rect(self) -> QRectF:
        return QRectF(12.0, 8.0, max(1.0, self.width() - 24.0), max(1.0, self.height() - 46.0))

    def _draw_histogram(self, painter: QPainter, rect: QRectF) -> None:
        hist = np.log1p(self._histogram) if self._logarithmic else self._histogram
        maximum = float(hist.max()) if hist.size else 0.0
        if maximum <= 0.0:
            return
        painter.setPen(QColor(188, 188, 188))
        for index, count in enumerate(hist):
            x = rect.left() + index * rect.width() / 255.0
            height = float(count) / maximum * rect.height()
            painter.drawLine(QPointF(x, rect.bottom()), QPointF(x, rect.bottom() - height))

    def _draw_input_gradient(self, painter: QPainter, rect: QRectF) -> None:
        top = rect.bottom() + 6.0
        height = 10.0
        for index in range(int(rect.width())):
            value = int(round(index / max(1.0, rect.width() - 1.0) * 255.0))
            painter.setPen(QColor(value, value, value))
            x = rect.left() + index
            painter.drawLine(QPointF(x, top), QPointF(x, top + height))
        painter.setPen(QColor(75, 75, 75))
        painter.drawRect(QRectF(rect.left(), top, rect.width(), height))

    def _draw_marker(self, painter: QPainter, x: float, marker: str) -> None:
        y = self._histogram_rect().bottom() + 22.0
        color = {
            "black": QColor(15, 15, 15),
            "gamma": QColor(145, 145, 145),
            "white": QColor(235, 235, 235),
        }[marker]
        outline = QColor(245, 245, 245) if marker == "black" else QColor(20, 20, 20)
        painter.setBrush(color)
        painter.setPen(QPen(outline, 1.5))
        points = [
            QPointF(x, y),
            QPointF(x - 7.0, y + 12.0),
            QPointF(x + 7.0, y + 12.0),
        ]
        painter.drawPolygon(points)

    def _x_for_value(self, value: int, rect: QRectF) -> float:
        return rect.left() + int(value) / 255.0 * rect.width()

    def _x_for_gamma(self, rect: QRectF) -> float:
        mid = float(np.clip(0.5 ** self._gamma, 0.0, 1.0))
        return self._x_for_value(self._black, rect) + mid * (
            self._x_for_value(self._white, rect) - self._x_for_value(self._black, rect)
        )

    def _set_marker_from_x(self, marker: str, x: float) -> None:
        rect = self._histogram_rect()
        value = int(round((x - rect.left()) / max(1.0, rect.width()) * 255.0))
        if marker == "black":
            self.set_values(min(value, self._white - 1), self._gamma, self._white)
        elif marker == "white":
            self.set_values(self._black, self._gamma, max(value, self._black + 1))
        else:
            low = self._x_for_value(self._black, rect)
            high = self._x_for_value(self._white, rect)
            midpoint = float(np.clip((x - low) / max(1.0, high - low), 1e-4, 0.9999))
            gamma = np.log(midpoint) / np.log(0.5)
            self.set_values(self._black, float(gamma), self._white)

    def _emit_values_changed(self) -> None:
        callback = self.on_values_changed
        if callable(callback):
            callback(self._black, self._gamma, self._white)


class _CurveEditorWidget(QWidget):
    """Interactive GIMP-style tone curve editor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(QSize(300, 260))
        self._histogram = np.zeros(256, dtype=np.float32)
        self._points: list[tuple[float, float]] = [(0.0, 0.0), (1.0, 1.0)]
        self._selected_index = 0
        self._curve_type = "smooth"
        self._logarithmic = False
        self.on_points_changed: object = None
        self.on_selected_point_changed: object = None

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def selected_point(self) -> tuple[float, float]:
        return self._points[self._selected_index]

    def set_points(self, points: list[tuple[float, float]]) -> None:
        cleaned = _sanitize_curve_points(points)
        self._points = cleaned
        self._selected_index = min(self._selected_index, len(cleaned) - 1)
        self.update()

    def set_selected_point(self, x: float, y: float) -> None:
        self._set_point(self._selected_index, x, y)

    def reset(self) -> None:
        self._points = [(0.0, 0.0), (1.0, 1.0)]
        self._selected_index = 0
        self._emit_points_changed()
        self._emit_selected_point_changed()
        self.update()

    def set_curve_type(self, curve_type: str) -> None:
        self._curve_type = curve_type
        self.update()

    def set_logarithmic(self, logarithmic: bool) -> None:
        self._logarithmic = bool(logarithmic)
        self.update()

    def set_pixels(self, pixels: np.ndarray, channel: str) -> None:
        values = _levels_channel_values(pixels, channel)
        if values.size == 0:
            self._histogram = np.zeros(256, dtype=np.float32)
        else:
            self._histogram = np.histogram(
                np.clip(values, 0.0, 1.0),
                bins=256,
                range=(0.0, 1.0),
            )[0].astype(np.float32)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(22, 22, 22))
        area = self._plot_rect()
        painter.setPen(QColor(78, 78, 78))
        painter.drawRect(area)
        self._draw_grid(painter, area)
        self._draw_histogram(painter, area)
        self._draw_curve(painter, area)
        self._draw_points(painter, area)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self._point_from_widget(event.position())
        nearest = self._nearest_point_index(event.position())
        if nearest is None:
            self._points.append((x, y))
            self._points = _sanitize_curve_points(self._points)
            self._selected_index = min(
                range(len(self._points)),
                key=lambda index: abs(self._points[index][0] - x),
            )
        else:
            self._selected_index = nearest
        self._set_point(self._selected_index, x, y)
        self._emit_selected_point_changed()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        x, y = self._point_from_widget(event.position())
        self._set_point(self._selected_index, x, y)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        nearest = self._nearest_point_index(event.position(), radius=10.0)
        if nearest is None or nearest in {0, len(self._points) - 1}:
            return
        del self._points[nearest]
        self._selected_index = max(0, min(nearest - 1, len(self._points) - 1))
        self._emit_points_changed()
        self._emit_selected_point_changed()
        self.update()

    def _plot_rect(self) -> QRectF:
        margin = 12.0
        return QRectF(
            margin,
            margin,
            max(1.0, self.width() - margin * 2.0),
            max(1.0, self.height() - margin * 2.0),
        )

    def _draw_grid(self, painter: QPainter, area: QRectF) -> None:
        painter.setPen(QColor(48, 48, 48))
        for index in range(1, 4):
            x = area.left() + area.width() * index / 4.0
            y = area.top() + area.height() * index / 4.0
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))

    def _draw_histogram(self, painter: QPainter, area: QRectF) -> None:
        hist = np.log1p(self._histogram) if self._logarithmic else self._histogram
        maximum = float(hist.max()) if hist.size else 0.0
        if maximum <= 0.0:
            return
        painter.setPen(QColor(95, 95, 95))
        for index, count in enumerate(hist):
            x = area.left() + index * area.width() / 255.0
            height = float(count) / maximum * area.height()
            painter.drawLine(QPointF(x, area.bottom()), QPointF(x, area.bottom() - height))

    def _draw_curve(self, painter: QPainter, area: QRectF) -> None:
        xs = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        ys = _evaluate_curve(self._points, xs, self._curve_type)
        painter.setPen(QPen(QColor(235, 235, 235), 2.0))
        previous = self._widget_from_point(float(xs[0]), float(ys[0]), area)
        for x, y in zip(xs[1:], ys[1:]):
            current = self._widget_from_point(float(x), float(y), area)
            painter.drawLine(previous, current)
            previous = current

    def _draw_points(self, painter: QPainter, area: QRectF) -> None:
        for index, (x, y) in enumerate(self._points):
            center = self._widget_from_point(x, y, area)
            radius = 5.0 if index == self._selected_index else 4.0
            painter.setBrush(QColor(255, 255, 255) if index == self._selected_index else QColor(170, 170, 170))
            painter.setPen(QColor(25, 25, 25))
            painter.drawEllipse(center, radius, radius)

    def _widget_from_point(self, x: float, y: float, area: QRectF) -> QPointF:
        return QPointF(area.left() + x * area.width(), area.bottom() - y * area.height())

    def _point_from_widget(self, point: QPointF) -> tuple[float, float]:
        area = self._plot_rect()
        x = (float(point.x()) - area.left()) / max(1.0, area.width())
        y = (area.bottom() - float(point.y())) / max(1.0, area.height())
        return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

    def _nearest_point_index(self, point: QPointF, radius: float = 8.0) -> int | None:
        area = self._plot_rect()
        best_index: int | None = None
        best_distance = radius
        for index, (x, y) in enumerate(self._points):
            center = self._widget_from_point(x, y, area)
            distance = ((center.x() - point.x()) ** 2 + (center.y() - point.y()) ** 2) ** 0.5
            if distance <= best_distance:
                best_index = index
                best_distance = float(distance)
        return best_index

    def _set_point(self, index: int, x: float, y: float) -> None:
        if index <= 0:
            x = 0.0
        elif index >= len(self._points) - 1:
            x = 1.0
        else:
            left = self._points[index - 1][0] + 1.0 / 255.0
            right = self._points[index + 1][0] - 1.0 / 255.0
            x = float(np.clip(x, left, right))
        self._points[index] = (float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0)))
        self._emit_points_changed()
        self._emit_selected_point_changed()
        self.update()

    def _emit_points_changed(self) -> None:
        callback = self.on_points_changed
        if callable(callback):
            callback(self.points())

    def _emit_selected_point_changed(self) -> None:
        callback = self.on_selected_point_changed
        if callable(callback):
            callback(self.selected_point())


def _levels_channel_values(pixels: np.ndarray, channel: str) -> np.ndarray:
    data = np.asarray(pixels, dtype=np.float32)
    if data.size == 0:
        return np.empty((0,), dtype=np.float32)
    if np.issubdtype(np.asarray(pixels).dtype, np.integer):
        info = np.iinfo(np.asarray(pixels).dtype)
        data = (data - float(info.min)) / max(1.0, float(info.max - info.min))
    elif data.max(initial=0.0) > 1.0 or data.min(initial=0.0) < 0.0:
        low = float(data.min(initial=0.0))
        high = float(data.max(initial=1.0))
        data = (data - low) / max(1e-6, high - low)
    if data.ndim < 3 or data.shape[-1] < 3 or channel == "rgb":
        return data.reshape(-1)
    channels = {"red": 0, "green": 1, "blue": 2, "alpha": 3}
    index = channels.get(channel)
    if index is None or index >= data.shape[-1]:
        return data.reshape(-1)
    return data[..., index].reshape(-1)


def _levels_auto_input_bounds(pixels: np.ndarray, channel: str) -> tuple[int, int]:
    values = _levels_channel_values(pixels, channel)
    if values.size == 0:
        return 0, 255
    low = int(np.clip(round(float(np.percentile(values, 0.5)) * 255.0), 0, 254))
    high = int(np.clip(round(float(np.percentile(values, 99.5)) * 255.0), 1, 255))
    if high <= low:
        return 0, 255
    return low, high


def _image_file_filter() -> str:
    extensions = sorted(f"*{extension}" for extension in SUPPORTED_EXTENSIONS)
    return f"Images ({' '.join(extensions)});;All Files (*)"


def _sanitize_curve_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cleaned = [
        (float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0)))
        for x, y in points
    ]
    cleaned.extend([(0.0, 0.0), (1.0, 1.0)])
    by_x: dict[int, tuple[float, float]] = {}
    for x, y in cleaned:
        key = int(round(x * 255.0))
        by_x[key] = (key / 255.0, y)
    result = [by_x[key] for key in sorted(by_x)]
    result[0] = (0.0, result[0][1])
    result[-1] = (1.0, result[-1][1])
    return result


def _evaluate_curve(
    points: list[tuple[float, float]],
    inputs: np.ndarray,
    curve_type: str,
) -> np.ndarray:
    sanitized = _sanitize_curve_points(points)
    xs = np.array([point[0] for point in sanitized], dtype=np.float32)
    ys = np.array([point[1] for point in sanitized], dtype=np.float32)
    if curve_type.lower() in {"free", "linear", "freehand", "free_hand"}:
        return np.interp(inputs, xs, ys)
    return np.clip(PchipInterpolator(xs, ys, extrapolate=True)(inputs), 0.0, 1.0)


