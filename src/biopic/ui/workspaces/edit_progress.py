"""Progress helpers for the edit workspace."""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Queue

from PySide6.QtCore import QEventLoop, QObject, Signal, Qt, QThread, QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog


class _ProgressComputationWorker(QObject):
    """Run a pure computation in a thread and return its result to the UI."""

    resultReady = Signal(object)
    finished = Signal()

    def __init__(
        self,
        action: Callable[..., object],
        *,
        accepts_progress: bool = False,
        progress_sink: Callable[[str, float], None] | None = None,
    ) -> None:
        super().__init__()
        self._action = action
        self._accepts_progress = accepts_progress
        self._progress_sink = progress_sink

    def run(self) -> None:
        try:
            if self._accepts_progress:
                result = self._action(self._emit_progress)
            else:
                result = self._action()
        except Exception as exc:  # pragma: no cover - surfaced by caller
            result = exc
        self.resultReady.emit(result)
        self.finished.emit()

    def _emit_progress(self, message: str, fraction: float) -> None:
        if self._progress_sink is not None:
            self._progress_sink(str(message), float(fraction))


class EditProgressMixin:
    """Progress-dialog helpers shared by edit operations."""

    def _run_with_progress(self, message: str, action: Callable[[], object]) -> object:
        """Run a blocking UI operation with immediate indeterminate progress feedback."""
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle("Processing")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        try:
            return action()
        finally:
            progress.close()
            progress.deleteLater()
            QApplication.processEvents()

    def _run_computation_with_progress(
        self,
        message: str,
        action: Callable[..., object],
        *,
        accepts_progress: bool = False,
    ) -> object:
        """Run a pure computation on a worker thread while keeping progress responsive."""
        progress = QProgressDialog(message, "", 0, 100, self)
        progress.setWindowTitle("Processing")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.setLabelText(f"{message} 0%")
        progress.show()
        QApplication.processEvents()

        result_box: dict[str, object] = {}
        progress_events: Queue[tuple[str, float]] = Queue()
        loop = QEventLoop(self)
        thread = QThread(self)
        worker = _ProgressComputationWorker(
            action,
            accepts_progress=accepts_progress,
            progress_sink=lambda stage, fraction: progress_events.put((stage, fraction)),
        )
        worker.moveToThread(thread)

        def store_result(result: object) -> None:
            result_box["result"] = result

        def update_progress(stage: str, fraction: float) -> None:
            bounded = max(0.0, min(1.0, float(fraction)))
            percent = int(round(bounded * 100.0))
            progress.setLabelText(f"{stage} {percent}%")
            progress.setValue(percent)

        def drain_progress_events() -> None:
            while True:
                try:
                    stage, fraction = progress_events.get_nowait()
                except Empty:
                    return
                update_progress(stage, fraction)

        progress_timer = QTimer(self)
        progress_timer.setInterval(50)
        progress_timer.timeout.connect(drain_progress_events)
        progress_timer.start()
        worker.resultReady.connect(store_result, Qt.ConnectionType.DirectConnection)
        worker.finished.connect(thread.quit)
        thread.finished.connect(loop.quit)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run)
        thread.start()
        try:
            loop.exec()
        finally:
            progress_timer.stop()
            drain_progress_events()
            if thread.isRunning():
                thread.quit()
                thread.wait()
            progress.close()
            progress.deleteLater()
            thread.deleteLater()
            QApplication.processEvents()
        result = result_box.get("result")
        if isinstance(result, Exception):
            raise result
        return result
