"""Shape annotation creation helpers for arrows, lines, and wedges."""

from __future__ import annotations

from biopic.models.annotations import AnnotationKind, AnnotationObject, fit_points_inside_unit_square, normalize_wedge_points


class AnnotationShapeActionsMixin:
    """Create non-text annotation shapes and configure their drag preview."""

    def _annotation_shape_kind_for_tool(self, tool_id: str) -> AnnotationKind:
        return {
            "arrow": AnnotationKind.ARROW,
            "line": AnnotationKind.LINE,
            "wedge": AnnotationKind.WEDGE,
        }.get(tool_id, AnnotationKind.LINE)

    def _configure_annotation_shape_preview(self) -> None:
        self.canvas.set_annotation_shape_preview_style(
            self._annotation_shape_kind_for_tool(self._annotation_tool),
            self._annotation_color,
            float(self.annotation_width.value()),
        )

    def _annotation_point_clicked(self, x: int, y: int) -> None:
        if self._annotation_tool == "label":
            self._annotation_label_point_clicked(x, y)
            return
        if self._annotation_tool != "wedge":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        self._store_annotation(
            AnnotationObject(
                image_node_id=node_id,
                kind=AnnotationKind.WEDGE,
                points=self._default_wedge_points(x, y),
                color=self._annotation_color,
                line_width=self.annotation_width.value(),
                fill=self._annotation_color,
                include_in_legend=False,
            )
        )

    def _annotation_rectangle_selected(
        self, x: int, y: int, width: int, height: int
    ) -> None:
        self._annotation_shape_selected(x, y, x + width, y + height)

    def _annotation_shape_selected(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        if self._annotation_tool not in {"arrow", "line", "wedge"}:
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        kind = self._annotation_shape_kind_for_tool(self._annotation_tool)
        if kind is AnnotationKind.WEDGE:
            points = self._wedge_points_from_axis(start_x, start_y, end_x, end_y)
        else:
            points = [
                self._normalized_annotation_point(start_x, start_y),
                self._normalized_annotation_point(end_x, end_y),
            ]
        annotation = AnnotationObject(
            image_node_id=node_id,
            kind=kind,
            points=points,
            color=self._annotation_color,
            line_width=self.annotation_width.value(),
            fill=self._annotation_color if kind is AnnotationKind.WEDGE else None,
            include_in_legend=False,
        )
        self._store_annotation(annotation)

    def _default_wedge_points(self, x: int, y: int) -> list[tuple[float, float]]:
        size = self.canvas.image_size()
        if size is None:
            return [(0.0, 0.0), (0.06, 0.03), (0.0, 0.06)]
        width, height = size
        default_length = max(5.0, min(float(width), float(height)) * 0.035)
        return self._wedge_points_from_axis(
            int(round(x - default_length * 0.5)),
            y,
            int(round(x + default_length * 0.5)),
            y,
        )

    def _wedge_points_from_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> list[tuple[float, float]]:
        x0 = float(x)
        x1 = float(x + width)
        y0 = float(y)
        y1 = float(y + height)
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        mid_y = (y0 + y1) / 2.0
        return self._normalized_annotation_shape_points(
            [
                (x1, mid_y),
                (x0, y0),
                (x0, y1),
            ]
        )

    def _wedge_points_from_axis(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> list[tuple[float, float]]:
        dx = float(end_x - start_x)
        dy = float(end_y - start_y)
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux
        half_width = max(5.0, length * 0.22, float(self.annotation_width.value()) * 3.0)
        points = self._normalized_annotation_shape_points(
            [
                (float(end_x), float(end_y)),
                (float(start_x) + nx * half_width, float(start_y) + ny * half_width),
                (float(start_x) - nx * half_width, float(start_y) - ny * half_width),
            ],
        )
        return normalize_wedge_points(points)

    def _normalized_annotation_shape_points(
        self,
        points: list[tuple[float, float]],
        *,
        fit_inside: bool = True,
        clamp: bool = True,
    ) -> list[tuple[float, float]]:
        size = self.canvas.image_size()
        if size is None:
            return [(0.0, 0.0) for _point in points]
        width, height = size
        fitted = _fit_points_inside_rect(points, float(width), float(height)) if fit_inside else points
        normalized = [
            (
                _normalized_coordinate(x, max(1.0, float(width)), clamp),
                _normalized_coordinate(y, max(1.0, float(height)), clamp),
            )
            for x, y in fitted
        ]
        return fit_points_inside_unit_square(normalized) if fit_inside else normalized


def _normalized_coordinate(value: float, extent: float, clamp: bool) -> float:
    normalized = value / extent
    return max(0.0, min(1.0, normalized)) if clamp else normalized


def _fit_points_inside_rect(
    points: list[tuple[float, float]],
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    if not points:
        return []
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    shape_width = max_x - min_x
    shape_height = max_y - min_y
    scale = 1.0
    if shape_width > width and shape_width > 0:
        scale = min(scale, width / shape_width)
    if shape_height > height and shape_height > 0:
        scale = min(scale, height / shape_height)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    scaled = [
        (
            center_x + (point[0] - center_x) * scale,
            center_y + (point[1] - center_y) * scale,
        )
        for point in points
    ]
    min_x = min(point[0] for point in scaled)
    max_x = max(point[0] for point in scaled)
    min_y = min(point[1] for point in scaled)
    max_y = max(point[1] for point in scaled)
    dx = 0.0
    dy = 0.0
    if min_x < 0.0:
        dx = -min_x
    elif max_x > width:
        dx = width - max_x
    if min_y < 0.0:
        dy = -min_y
    elif max_y > height:
        dy = height - max_y
    return [(point[0] + dx, point[1] + dy) for point in scaled]
