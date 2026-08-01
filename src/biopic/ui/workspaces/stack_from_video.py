"""Create image stacks by extracting frames from retained video sections."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.io import import_stack
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.models.video_edit import VideoEditModel, VideoSegment, frame_timestamps
from biopic.ui.workspace_helpers.common import stack_display_name
from biopic.ui.workspaces.stack_from_video_components import VideoPreviewPane, VideoTimeline
from biopic.ui.workspaces.stack_from_video_dialogs import FrameExtractionDialog
from biopic.ui.workspaces.stack_from_video_media import (
    MAX_EXTRACTED_FRAMES,
    format_time,
    is_video_url,
    safe_stem,
    validate_video,
    video_preview_frame,
    video_thumbnail,
    video_timeline_frames,
)
from biopic.workers.video_frame_extractor import VideoExtractionJob, VideoFrameExtractor


class StackFromVideoWorkspace(QWidget):
    """Lightweight video trimming and frame extraction workspace."""

    stackCreated = Signal(str)
    videoLoaded = Signal()

    def minimumSizeHint(self) -> QSize:
        """Allow video controls/timeline to shrink with the main window."""
        return QSize(320, 260)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._video_path: Path | None = None
        self._video_paths: list[Path] = []
        self._model: VideoEditModel | None = None
        self._undo_stack: list[tuple[list[VideoSegment], int | None]] = []
        self._redo_stack: list[tuple[list[VideoSegment], int | None]] = []
        self._worker: VideoFrameExtractor | None = None
        self._seeking_over_cut = False
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        self._build_controls()
        self._build_video_list(layout)
        self._build_preview(layout)
        self._build_transport(layout)
        self._build_timeline(layout)
        self._connect_signals()

    def _build_controls(self) -> None:
        self.load_button = self._tool_button("Import Video", "Import Video")
        self.play_button = self._tool_button("Play", None, QStyle.StandardPixmap.SP_MediaPlay)
        self.pause_button = self._tool_button("Pause", None, QStyle.StandardPixmap.SP_MediaPause)
        self.fast_back_button = self._tool_button(
            "Fast backward",
            None,
            QStyle.StandardPixmap.SP_MediaSeekBackward,
        )
        self.fast_forward_button = self._tool_button(
            "Fast forward",
            None,
            QStyle.StandardPixmap.SP_MediaSeekForward,
        )
        self.step_back_button = self._tool_button(
            "Step backward",
            None,
            QStyle.StandardPixmap.SP_MediaSkipBackward,
        )
        self.step_forward_button = self._tool_button(
            "Step forward",
            None,
            QStyle.StandardPixmap.SP_MediaSkipForward,
        )
        self.split_button = self._tool_button("Cut at playhead", None, icon_name="edit-cut")
        self.split_button.setStatusTip("Split the selected video track at the current playhead.")
        self.delete_button = self._tool_button(
            "Delete selected segment",
            None,
            QStyle.StandardPixmap.SP_TrashIcon,
        )
        self.delete_button.setStatusTip(
            "Remove the selected segment from playback and frame extraction."
        )
        self.undo_button = self._tool_button("Undo", None, QStyle.StandardPixmap.SP_ArrowBack)
        self.redo_button = self._tool_button("Redo", None, QStyle.StandardPixmap.SP_ArrowForward)
        self.create_button = self._tool_button("Create Stack from Video", "Create Stack")

    def _build_video_list(self, layout: QVBoxLayout) -> None:
        self.video_list = QListWidget()
        self.video_list.setIconSize(QSize(170, 120))
        self.video_list.setUniformItemSizes(True)
        self.video_list.setFlow(QListWidget.Flow.LeftToRight)
        self.video_list.setWrapping(False)
        self.video_list.setFixedHeight(150)
        layout.addWidget(self.video_list)

    def _build_preview(self, layout: QVBoxLayout) -> None:
        self.preview = VideoPreviewPane()
        self.preview.setMinimumHeight(360)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setMuted(True)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.preview.video)
        layout.addWidget(self.preview, 1)

    def _build_transport(self, layout: QVBoxLayout) -> None:
        transport = QHBoxLayout()
        transport.addStretch(1)
        for button in (
            self.step_back_button,
            self.fast_back_button,
            self.play_button,
            self.pause_button,
            self.fast_forward_button,
            self.step_forward_button,
        ):
            transport.addWidget(button)
        transport.addSpacing(16)
        for button in (
            self.split_button,
            self.delete_button,
            self.undo_button,
            self.redo_button,
        ):
            transport.addWidget(button)
        transport.addStretch(1)
        layout.addLayout(transport)

    def _build_timeline(self, layout: QVBoxLayout) -> None:
        timeline_row = QHBoxLayout()
        self.current_time = self._status_label("00:00.000")
        self.duration_time = self._status_label("00:00.000")
        self.timeline = VideoTimeline()
        timeline_row.addWidget(self.current_time)
        timeline_row.addWidget(self.timeline, 1)
        timeline_row.addWidget(self.duration_time)
        layout.addLayout(timeline_row)
        self.scroll_slider = QSlider(Qt.Orientation.Horizontal)
        self.scroll_slider.setRange(0, 0)
        self.scroll_slider.hide()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

    def _connect_signals(self) -> None:
        self.load_button.clicked.connect(self.open_video)
        self.play_button.clicked.connect(self._play_video)
        self.pause_button.clicked.connect(self.player.pause)
        self.step_back_button.clicked.connect(lambda: self._step_frame(-1))
        self.step_forward_button.clicked.connect(lambda: self._step_frame(1))
        self.fast_back_button.clicked.connect(lambda: self._jump_seconds(-5.0))
        self.fast_forward_button.clicked.connect(lambda: self._jump_seconds(5.0))
        self.split_button.clicked.connect(self.split_at_playhead)
        self.delete_button.clicked.connect(self.delete_selected_segment)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.create_button.clicked.connect(self.create_stack_from_video)
        self.video_list.currentRowChanged.connect(self._select_video_row)
        self.timeline.playheadChanged.connect(self._seek)
        self.player.positionChanged.connect(self._position_changed)

    def refresh(self) -> None:
        self._update_buttons()

    def open_video(self) -> None:
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            "Load Video",
            "",
            "Videos (*.mp4 *.mov *.avi *.mkv *.m4v *.wmv *.webm);;All Files (*)",
        )
        if filename:
            self.load_video(Path(filename))

    def load_video(self, path: Path) -> None:
        try:
            info = validate_video(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Load Video Failed", str(exc))
            return
        self._video_path = path
        self._add_video_to_list(path)
        self._model = VideoEditModel(duration=info.duration_seconds)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.timeline.set_model(self._model)
        self._refresh_timeline_thumbnails()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.preview.set_poster(video_preview_frame(path))
        self.duration_time.setText(format_time(info.duration_seconds))
        self.current_time.setText(format_time(0.0))
        self.progress.setValue(0)
        self._update_buttons()
        self.videoLoaded.emit()

    def _add_video_to_list(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved not in self._video_paths:
            self._video_paths.append(resolved)
            item = QListWidgetItem(
                QIcon(video_thumbnail(resolved, self.video_list.iconSize())),
                resolved.name,
            )
            item.setToolTip(str(resolved))
            self.video_list.addItem(item)
        row = self._video_paths.index(resolved)
        if self.video_list.currentRow() != row:
            self.video_list.blockSignals(True)
            self.video_list.setCurrentRow(row)
            self.video_list.blockSignals(False)

    def _select_video_row(self, row: int) -> None:
        if row < 0 or row >= len(self._video_paths):
            return
        path = self._video_paths[row]
        if path != self._video_path:
            self.load_video(path)

    def split_at_playhead(self) -> None:
        if self._model is None:
            return
        self._push_undo()
        if not self._model.split_at(self.timeline.playhead):
            self._undo_stack.pop()
        self._refresh_timeline_thumbnails()
        self.timeline.update()
        self._update_buttons()
        self.progress.setFormat("Segment split at playhead.")

    def delete_selected_segment(self) -> None:
        if self._model is None:
            return
        self._push_undo()
        if not self._model.delete_selected():
            self._undo_stack.pop()
        else:
            next_time = self._model.next_retained_time(self.timeline.playhead)
            if next_time is not None and next_time != self.timeline.playhead:
                self.timeline.set_playhead(next_time)
                self._seek(next_time)
            self.progress.setFormat("Selected segment removed from playback and export.")
        self._refresh_timeline_thumbnails()
        self.timeline.update()
        self._update_buttons()

    def undo(self) -> None:
        if self._model is None or not self._undo_stack:
            return
        self._redo_stack.append(self._model.snapshot())
        self._model.restore(self._undo_stack.pop())
        self._refresh_timeline_thumbnails()
        self.timeline.update()
        self._seek(self.timeline.playhead)
        self._update_buttons()

    def redo(self) -> None:
        if self._model is None or not self._redo_stack:
            return
        self._undo_stack.append(self._model.snapshot())
        self._model.restore(self._redo_stack.pop())
        self._refresh_timeline_thumbnails()
        self.timeline.update()
        self._seek(self.timeline.playhead)
        self._update_buttons()

    def create_stack_from_video(self) -> None:
        if self._video_path is None or self._model is None:
            return
        dialog = FrameExtractionDialog(self._model.retained_segments(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        interval = dialog.interval_seconds()
        timestamps = frame_timestamps(self._model.retained_segments(), interval)
        if not timestamps:
            QMessageBox.information(
                self,
                "Create Stack from Video",
                "No frames would be extracted.",
            )
            return
        if len(timestamps) > MAX_EXTRACTED_FRAMES:
            QMessageBox.warning(
                self,
                "Create Stack from Video",
                f"The interval would create {len(timestamps)} frames. Increase the interval.",
            )
            return
        output_dir = (
            Path.cwd()
            / ".biopic_cache"
            / self.project.id
            / "video_frames"
            / str(uuid4())
        ).resolve()
        job = VideoExtractionJob(
            video_path=self._video_path,
            output_dir=output_dir,
            interval_seconds=interval,
            retained_segments=self._model.retained_segments(),
            base_name=safe_stem(self._video_path.stem),
        )
        self._worker = VideoFrameExtractor(job)
        self._worker.progressChanged.connect(self._show_progress)
        self._worker.extractionFinished.connect(
            lambda result, interval=interval: self._import_extracted_frames(result, interval)
        )
        self._worker.extractionFailed.connect(self._extraction_failed)
        self._worker.finished.connect(self._worker_finished)
        self.create_button.setEnabled(False)
        self.progress.setValue(0)
        self._worker.start()

    def cancel_extraction(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(is_video_url(url) for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if is_video_url(url):
                self.load_video(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return

    def _import_extracted_frames(self, result: object, interval: float) -> None:
        if self._video_path is None or self._model is None:
            return
        frame_records = list(result) if isinstance(result, list) else []
        paths = [Path(item[0]) for item in frame_records]
        before_assets = set(self.project.assets)
        before_stacks = set(self.project.stacks)
        try:
            stack = import_stack(self.project, paths, StackKind.FOCAL)
        except (OSError, ValueError) as exc:
            for asset_id in set(self.project.assets) - before_assets:
                self.project.assets.pop(asset_id, None)
            for stack_id in set(self.project.stacks) - before_stacks:
                self.project.stacks.pop(stack_id, None)
            if paths:
                shutil.rmtree(paths[0].parent, ignore_errors=True)
            QMessageBox.critical(self, "Import Extracted Frames Failed", str(exc))
            return
        stack.name = f"{self._video_path.stem} video stack"
        stack_metadata = {
            "source_video": str(self._video_path),
            "extraction_interval_seconds": interval,
            "retained_video_ranges": [
                [segment.start, segment.end] for segment in self._model.retained_segments()
            ],
        }
        for index, asset_id in enumerate(stack.asset_ids):
            asset = self.project.assets.get(asset_id)
            if asset is None:
                continue
            timestamp = float(frame_records[index][1]) if index < len(frame_records) else 0.0
            asset.metadata.update(stack_metadata)
            asset.metadata.update(
                {
                    "video_frame_index": index + 1,
                    "video_timestamp_seconds": timestamp,
                }
            )
        self.project.touch()
        self.stackCreated.emit(stack.id)
        self.progress.setFormat(f"Created stack: {stack_display_name(stack, self.project.assets)}")

    def _extraction_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Create Stack from Video", message)
        self.progress.setFormat(message)

    def _worker_finished(self) -> None:
        self.create_button.setEnabled(True)
        self._worker = None

    def _show_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, float(fraction))) * 100.0))
        self.progress.setFormat(message)

    def _seek(self, seconds: float) -> None:
        self.preview.show_live_video()
        target = max(0.0, seconds)
        if self._model is not None:
            retained_target = self._model.next_retained_time(target)
            if retained_target is not None:
                target = retained_target
        self.player.setPosition(int(target * 1000.0))
        self.current_time.setText(format_time(target))
        self.timeline.set_playhead(target)

    def _position_changed(self, milliseconds: int) -> None:
        if self._seeking_over_cut:
            return
        seconds = milliseconds / 1000.0
        if self._model is not None:
            segment = self._model.segment_at_source_time(seconds)
            if segment is not None and not segment.retained:
                next_time = self._model.next_retained_time(segment.end + 0.001)
                if next_time is not None:
                    self._seeking_over_cut = True
                    self.player.setPosition(int(next_time * 1000.0))
                    self._seeking_over_cut = False
                    seconds = next_time
            elif segment is None:
                next_time = self._model.next_retained_time(seconds)
                if next_time is not None:
                    seconds = next_time
        self.current_time.setText(format_time(seconds))
        self.timeline.set_playhead(seconds)

    def _play_video(self) -> None:
        self.preview.show_live_video()
        self.player.play()

    def _step_frame(self, direction: int) -> None:
        fps = validate_video(self._video_path).fps if self._video_path is not None else 25.0
        next_time = self.timeline.playhead + float(direction) / max(1.0, fps)
        self.timeline.set_playhead(next_time)
        self._seek(self.timeline.playhead)

    def _jump_seconds(self, seconds: float) -> None:
        if self._model is None:
            return
        next_time = self.timeline.playhead + seconds
        self.timeline.set_playhead(next_time)
        self._seek(self.timeline.playhead)

    def _refresh_timeline_thumbnails(self) -> None:
        if self._video_path is None or self._model is None:
            self.timeline.set_thumbnails([])
            return
        self.timeline.set_thumbnails(
            video_timeline_frames(self._video_path, self._model.retained_segments())
        )

    def _push_undo(self) -> None:
        if self._model is None:
            return
        self._undo_stack.append(self._model.snapshot())
        self._redo_stack.clear()

    def _update_buttons(self) -> None:
        loaded = self._model is not None
        for button in (
            self.play_button,
            self.pause_button,
            self.step_back_button,
            self.step_forward_button,
            self.fast_back_button,
            self.fast_forward_button,
            self.split_button,
            self.delete_button,
            self.create_button,
        ):
            button.setEnabled(loaded)
        self.undo_button.setEnabled(bool(self._undo_stack))
        self.redo_button.setEnabled(bool(self._redo_stack))

    def _tool_button(
        self,
        tooltip: str,
        text: str | None,
        standard_icon: QStyle.StandardPixmap | None = None,
        *,
        icon_name: str | None = None,
    ) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setAutoRaise(False)
        button.setIconSize(QSize(22, 22))
        icon = QIcon.fromTheme(icon_name) if icon_name else QIcon()
        if icon.isNull() and standard_icon is not None:
            icon = self.style().standardIcon(standard_icon)
        if not icon.isNull():
            button.setIcon(icon)
        if text is not None:
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        elif icon.isNull():
            button.setText("Cut" if icon_name == "edit-cut" else tooltip)
        button.setMinimumSize(QSize(34, 32))
        return button

    def _status_label(self, text: str) -> QWidget:
        return QLabel(text)
