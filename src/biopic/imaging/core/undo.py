"""Core undo manager.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CoreUndoRecord:
    """Constant-size metadata or tile-snapshot undo record."""

    label: str
    payload: dict[str, Any]


@dataclass(slots=True)
class CoreUndoManager:
    """Undo/redo transaction stack for core image edits."""

    undo_stack: list[CoreUndoRecord] = field(default_factory=list)
    redo_stack: list[CoreUndoRecord] = field(default_factory=list)
    _transaction: list[CoreUndoRecord] | None = None

    def begin(self) -> None:
        """Begin a grouped transaction."""
        self._transaction = []

    def push(self, record: CoreUndoRecord) -> None:
        """Push a record or add it to the active transaction."""
        if self._transaction is not None:
            self._transaction.append(record)
        else:
            self.undo_stack.append(record)
            self.redo_stack.clear()

    def commit(self, label: str) -> None:
        """Commit the active transaction as one undo item."""
        if self._transaction is None:
            return
        self.undo_stack.append(
            CoreUndoRecord(label, {"records": [record.payload for record in self._transaction]})
        )
        self.redo_stack.clear()
        self._transaction = None
