"""Reusable widgets for the Stack from Video workspace."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from biopic.models.video_edit import VideoEditModel
from biopic.resources import resource_path


class VideoPreviewPane(QWidget):
    """Video preview with a branded empty state and poster frame."""

    def __init__(self) -> None:
        super().__init__()
        self.video = QVideoWidget()
        self.empty = VideoEmptyState()
        self.poster = QLabel()
        self._poster_source = QPixmap()
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setStyleSheet("background: palette(window);")
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.poster)
        self.stack.addWidget(self.video)

    def set_video_loaded(self, loaded: bool) -> None:
        self.stack.setCurrentWidget(self.video if loaded else self.empty)

    def set_poster(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.set_video_loaded(True)
            return
        self._poster_source = pixmap
        self._update_poster_pixmap()
        self.stack.setCurrentWidget(self.poster)

    def show_live_video(self) -> None:
        self.stack.setCurrentWidget(self.video)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._update_poster_pixmap()

    def _update_poster_pixmap(self) -> None:
        if self._poster_source.isNull():
            return
        target_size = self.poster.size()
        if target_size.width() <= 1 or target_size.height() <= 1:
            target_size = QSize(960, 540)
        self.poster.setPixmap(
            self._poster_source.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class VideoEmptyState(QWidget):
    """Branded empty video preview."""

    def __init__(self) -> None:
        super().__init__()
        self._watermark_pixmap = QPixmap(str(resource_path("icons", "biopic_logo.png")))

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        if self._watermark_pixmap.isNull():
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video selected")
            return
        target_size = min(self.width(), self.height()) * 1.15
        target = QRectF(
            (self.width() - target_size) / 2.0,
            (self.height() - target_size) / 2.0,
            target_size,
            target_size,
        )
        painter.save()
        painter.setOpacity(0.055)
        painter.drawPixmap(target, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))
        painter.restore()


class VideoTimeline(QWidget):
    """Simple non-destructive segment timeline."""

    playheadChanged = Signal(float)
    segmentSelected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.model: VideoEditModel | None = None
        self.playhead = 0.0
        self._thumbnails: list[QPixmap] = []
        self.setMinimumHeight(230)

    def set_model(self, model: VideoEditModel | None) -> None:
        self.model = model
        self.playhead = 0.0
        self.update()

    def set_thumbnails(self, thumbnails: list[QPixmap]) -> None:
        self._thumbnails = list(thumbnails)
        self.update()

    def set_playhead(self, seconds: float) -> None:
        if self.model is None:
            return
        self.playhead = max(0.0, min(float(seconds), self.model.duration))
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        track = self._track_rect()
        painter.setPen(QPen(self.palette().color(self.foregroundRole()), 1))
        painter.drawText(16, 26, "Video track")
        painter.drawText(
            track.left(),
            track.bottom() + 48,
            "Scissors: split at playhead. Trash: remove selected segment from playback/export.",
        )
        painter.drawRect(track)
        if self.model is None or self.model.duration <= 0:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a video")
            return
        effective_duration = max(1e-6, self.model.effective_duration())
        thumbnail_rect = QRectF(track.left(), track.top() + 6, track.width(), track.height() - 12)
        if self._thumbnails:
            thumb_width = track.width() / len(self._thumbnails)
            for index, pixmap in enumerate(self._thumbnails):
                slot = QRectF(
                    track.left() + index * thumb_width,
                    thumbnail_rect.top(),
                    thumb_width,
                    thumbnail_rect.height(),
                )
                scaled = pixmap.scaled(
                    slot.size().toSize(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.FastTransformation,
                )
                painter.drawPixmap(slot.toRect(), scaled)
        elapsed = 0.0
        for index, segment in enumerate(self.model.segments or []):
            if not segment.retained:
                continue
            left = track.left() + track.width() * elapsed / effective_duration
            right = track.left() + track.width() * (elapsed + segment.duration) / effective_duration
            rect = QRectF(left, track.top(), max(1.0, right - left), track.height())
            color = self.palette().color(self.foregroundRole())
            color.setAlpha(44)
            painter.fillRect(rect, color)
            if index == self.model.selected_index:
                painter.setPen(QPen(self.palette().highlight().color(), 3))
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
            elapsed += segment.duration
        for segment in self.model.segments or []:
            if segment.retained:
                continue
            compact_time = self.model.source_to_effective_time(segment.start)
            marker_x = track.left() + track.width() * compact_time / effective_duration
            painter.setPen(QPen(self.palette().mid().color(), 2))
            painter.drawLine(int(marker_x), int(track.top()), int(marker_x), int(track.bottom()))
        tick_pen = QPen(self.palette().mid().color(), 1)
        painter.setPen(tick_pen)
        tick_count = min(12, max(2, int(effective_duration // 5) + 1))
        for tick in range(tick_count + 1):
            fraction = tick / max(1, tick_count)
            x = track.left() + track.width() * fraction
            painter.drawLine(int(x), int(track.bottom() + 2), int(x), int(track.bottom() + 10))
            label = f"{int(round(effective_duration * fraction))}s"
            painter.drawText(int(x) - 12, int(track.bottom() + 26), label)
        playhead_effective = self.model.source_to_effective_time(self.playhead)
        x = track.left() + track.width() * playhead_effective / effective_duration
        painter.setPen(QPen(QColor(self.palette().highlight().color()), 2))
        painter.drawLine(int(x), int(track.top() - 12), int(x), int(track.bottom() + 18))

    def mousePressEvent(self, event: object) -> None:
        self._update_from_position(event.position().x())

    def mouseMoveEvent(self, event: object) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_position(event.position().x())

    def _update_from_position(self, x: float) -> None:
        if self.model is None or self.model.duration <= 0:
            return
        track = self._track_rect()
        fraction = max(0.0, min(1.0, (float(x) - track.left()) / max(1.0, track.width())))
        effective_seconds = fraction * self.model.effective_duration()
        seconds = self.model.effective_to_source_time(effective_seconds)
        self.playhead = seconds
        selected = self.model.select_at(seconds)
        if selected is not None:
            self.segmentSelected.emit(selected)
        self.playheadChanged.emit(seconds)
        self.update()

    def _track_rect(self) -> QRectF:
        return QRectF(16, 44, max(1, self.width() - 32), 120)
