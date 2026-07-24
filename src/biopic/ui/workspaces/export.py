"""Export and preflight workspace."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from biopic.export import preflight_project
from biopic.models.project import Project


class ExportWorkspace(QWidget):
    """Export and preflight workspace foundation."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.preflight_button = QPushButton("Run Preflight")
        controls.addWidget(self.preflight_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        layout.addWidget(self.records)
        self.preflight_button.clicked.connect(self.run_preflight)

    def refresh(self) -> None:
        """Refresh export status."""
        self.run_preflight()

    def run_preflight(self) -> None:
        """Run preflight checks and show report."""
        board = next(iter(self.project.figure_boards.values()), None)
        issues = preflight_project(self.project, board)
        if not issues:
            self.records.setPlainText("Preflight passed.")
            return
        self.records.setPlainText(
            "\n".join(f"{issue.severity.value}: {issue.code}: {issue.message}" for issue in issues)
        )
