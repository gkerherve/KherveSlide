"""Undo/redo via whole-document snapshots.

Rather than a bespoke command per action type, the document is
undoable by capturing a full serialised snapshot
(`document.scene_to_dict`) after every user change and swapping
between snapshots on undo/redo. Because the persistence layer already
records every item property, the raster layer and the grid, this makes
*every* document change undoable for free — and any future action is
undoable automatically as long as it emits `changed_by_user`.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PySide6.QtGui import QUndoCommand


class SnapshotCommand(QUndoCommand):
    """Swaps the document between a before and an after snapshot.

    The change has already been applied to the scene by the time the
    command is pushed, so the first `redo()` (fired by `QUndoStack.push`)
    is a no-op; later redo/undo restore the after/before snapshots.
    """

    def __init__(self, window, before: dict, after: dict, text="Edit"):
        super().__init__(text)
        self._window = window
        self._before = before
        self._after = after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return
        self._window._restore_snapshot(self._after)

    def undo(self):
        self._window._restore_snapshot(self._before)
