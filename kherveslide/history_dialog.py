"""Commit-browser dialog with branch graph and branch management.

A three-pane window:

  - Left:  commit list with a painted DAG rail (branch graph) showing
           how commits connect — merge points, branch forks, parallel
           lines. Branch labels are drawn inline next to the commits
           they point to.
  - Right: top  — full commit message and metadata.
           middle — unified diff with colour highlighting.
           bottom — restore button.
  - Top bar: branch selector (current branch indicator, switch, create,
             delete) so users can manage branches without leaving the
             dialog.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from . import git_backend


# ---- rail / graph colours ------------------------------------------------

_RAIL_COLOURS = [
    QColor("#1a6dd8"),   # blue
    QColor("#d96b00"),   # orange
    QColor("#2a8c4a"),   # green
    QColor("#a83070"),   # magenta
    QColor("#7b5ea7"),   # purple
    QColor("#b08800"),   # gold
    QColor("#00838f"),   # teal
    QColor("#c44040"),   # red
]


def _rail_colour(rail: int) -> QColor:
    return _RAIL_COLOURS[rail % len(_RAIL_COLOURS)]


# ---- diff highlighter ----------------------------------------------------

class _DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self._fmt_header = QTextCharFormat()
        self._fmt_header.setForeground(QColor("#7a7a7a"))
        self._fmt_header.setFontItalic(True)
        self._fmt_hunk = QTextCharFormat()
        self._fmt_hunk.setForeground(QColor("#1a4fa0"))
        self._fmt_hunk.setFontWeight(QFont.Bold)
        self._fmt_add = QTextCharFormat()
        self._fmt_add.setForeground(QColor("#0a6f00"))
        self._fmt_add.setBackground(QColor("#e6f7e6"))
        self._fmt_del = QTextCharFormat()
        self._fmt_del.setForeground(QColor("#a8001a"))
        self._fmt_del.setBackground(QColor("#fde0e0"))

    def highlightBlock(self, text: str) -> None:
        if not text:
            return
        if (text.startswith("+++") or text.startswith("---")
                or text.startswith("diff ") or text.startswith("index ")
                or text.startswith("new file")
                or text.startswith("deleted file")
                or text.startswith("similarity ")
                or text.startswith("rename ")):
            self.setFormat(0, len(text), self._fmt_header)
            return
        if text.startswith("@@"):
            self.setFormat(0, len(text), self._fmt_hunk)
            return
        if text.startswith("+"):
            self.setFormat(0, len(text), self._fmt_add)
            return
        if text.startswith("-"):
            self.setFormat(0, len(text), self._fmt_del)


# ---- graph delegate (paints the DAG rail in the first column) ------------

GRAPH_COL_W = 16   # pixels per rail column
DOT_R = 4          # commit-dot radius
GRAPH_PAD = 8      # left padding before the first rail


class _GraphDelegate(QStyledItemDelegate):
    """Paints the git DAG graph in column 0 of the commit table."""

    def __init__(self, commits: list[dict], parent=None):
        super().__init__(parent)
        self._commits = commits
        # Pre-compute max rail count for sizing.
        self._max_rails = 1
        for c in commits:
            self._max_rails = max(self._max_rails, c["rail"] + 1)
            for pair in c.get("rails_after", []):
                self._max_rails = max(self._max_rails, pair[0] + 1, pair[1] + 1)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index) -> None:
        # Let the base draw selection highlight, then draw the graph.
        super().paint(painter, option, index)
        row = index.row()
        if row < 0 or row >= len(self._commits):
            return
        c = self._commits[row]
        rail = c["rail"]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect
        y_mid = rect.y() + rect.height() / 2

        def x_of(r: int) -> float:
            return rect.x() + GRAPH_PAD + r * GRAPH_COL_W + GRAPH_COL_W / 2

        # Draw vertical continuation lines for all active rails.
        for ri, _ in c.get("rails_after", []):
            col = _rail_colour(ri)
            pen = QPen(col, 2.0)
            painter.setPen(pen)
            x = x_of(ri)
            if ri == rail:
                # This rail has the commit dot — draw line from top to
                # dot and from dot to bottom, the dot itself drawn later.
                painter.drawLine(int(x), rect.y(), int(x), int(y_mid) - DOT_R)
                painter.drawLine(int(x), int(y_mid) + DOT_R,
                                 int(x), rect.y() + rect.height())
            else:
                painter.drawLine(int(x), rect.y(), int(x),
                                 rect.y() + rect.height())

        # Draw merge lines: extra parents come from other rails into
        # this commit's dot.
        parent_oids = c.get("parents", [])
        if len(parent_oids) > 1:
            # Find which rails the extra parents are on (in the NEXT row).
            next_row = row + 1
            if next_row < len(self._commits):
                # Look at rails_after to figure out where parent rails are.
                for extra_p in parent_oids[1:]:
                    # Find the rail of this parent in the next few rows.
                    for future in range(next_row,
                                        min(next_row + 5, len(self._commits))):
                        fc = self._commits[future]
                        if fc["oid"] == extra_p:
                            pr = fc["rail"]
                            col = _rail_colour(pr)
                            painter.setPen(QPen(col, 2.0))
                            painter.drawLine(
                                int(x_of(rail)), int(y_mid),
                                int(x_of(pr)),
                                rect.y() + rect.height())
                            break

        # Draw the commit dot.
        dot_col = _rail_colour(rail)
        painter.setPen(Qt.NoPen)
        if c.get("is_merge"):
            painter.setBrush(QBrush(dot_col))
            painter.drawEllipse(
                QRectF(x_of(rail) - DOT_R - 1, y_mid - DOT_R - 1,
                       (DOT_R + 1) * 2, (DOT_R + 1) * 2))
        else:
            painter.setBrush(QBrush(dot_col))
            painter.drawEllipse(
                QRectF(x_of(rail) - DOT_R, y_mid - DOT_R,
                       DOT_R * 2, DOT_R * 2))

        # Draw branch labels next to the dot.
        branches = c.get("branches", [])
        if branches:
            label_x = x_of(self._max_rails) + 4
            for i, bname in enumerate(branches):
                tag_y = y_mid - 8 + i * 18
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(bname) + 10
                th = 16
                is_remote = "/" in bname
                bg = QColor("#e8e0f0") if is_remote else QColor("#d0e8ff")
                fg = QColor("#5a4080") if is_remote else QColor("#0a5090")
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(bg))
                painter.drawRoundedRect(
                    QRectF(label_x, tag_y, tw, th), 3, 3)
                painter.setPen(fg)
                f = QFont(); f.setPointSize(8); f.setBold(True)
                painter.setFont(f)
                painter.drawText(
                    QRectF(label_x + 5, tag_y, tw - 10, th),
                    Qt.AlignVCenter, bname)

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        row = index.row()
        base = super().sizeHint(option, index)
        if row < 0 or row >= len(self._commits):
            return base
        c = self._commits[row]
        graph_w = GRAPH_PAD + self._max_rails * GRAPH_COL_W
        branches = c.get("branches", [])
        if branches:
            # Add room for the widest branch label.
            longest = max(len(b) for b in branches) * 8 + 20
            graph_w += longest
        return QSize(max(base.width(), graph_w + 10),
                     max(base.height(), 28))


# ---- main dialog ---------------------------------------------------------

class HistoryDialog(QDialog):
    """Browse the commits behind the current document, visualise the
    branch graph, create / switch / delete branches."""

    def __init__(self, repo_dir: Path, parent: QWidget | None = None,
                 file_stem: str | None = None) -> None:
        super().__init__(parent)
        title = file_stem or repo_dir.name
        self.setWindowTitle(f"Version history — {title}")
        self.resize(1200, 750)
        self._repo_dir = repo_dir
        self._file_stem = file_stem
        self._parent_window = parent

        # ---- branch toolbar ------------------------------------------------
        branch_bar = QHBoxLayout()
        branch_bar.setContentsMargins(0, 0, 0, 4)

        self._branch_label = QLabel()
        self._branch_label.setStyleSheet("font-weight: bold;")
        branch_bar.addWidget(self._branch_label)

        self._branch_combo = QComboBox()
        self._branch_combo.setMinimumWidth(150)
        self._branch_combo.setToolTip("Switch to another branch")
        branch_bar.addWidget(self._branch_combo)

        self._btn_switch = QPushButton("Switch")
        self._btn_switch.setToolTip("Switch working tree to the selected branch")
        self._btn_switch.clicked.connect(self._on_switch_branch)
        branch_bar.addWidget(self._btn_switch)

        self._btn_new = QPushButton("+ New branch")
        self._btn_new.setToolTip("Create a new branch from HEAD")
        self._btn_new.clicked.connect(self._on_create_branch)
        branch_bar.addWidget(self._btn_new)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setToolTip("Delete the selected branch")
        self._btn_delete.clicked.connect(self._on_delete_branch)
        branch_bar.addWidget(self._btn_delete)

        branch_bar.addStretch()

        self._refresh_branch_bar()

        # ---- commit graph + table ------------------------------------------
        self._commits = git_backend.history_graph(repo_dir, limit=300)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Graph", "When", "Message", "Author"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(True)

        # Graph delegate for column 0.
        self._graph_delegate = _GraphDelegate(self._commits, self._table)
        self._table.setItemDelegateForColumn(0, self._graph_delegate)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        hdr.resizeSection(0, self._graph_col_width())
        hdr.resizeSection(1, 140)
        hdr.resizeSection(3, 90)

        for row, c in enumerate(self._commits):
            self._table.insertRow(row)
            # Column 0: empty text — the delegate paints the graph.
            item0 = QTableWidgetItem("")
            self._table.setItem(row, 0, item0)
            for col, key in enumerate(("timestamp", "subject", "author"), 1):
                item = QTableWidgetItem(c[key])
                item.setToolTip(c[key])
                if key == "timestamp":
                    f = item.font(); f.setPointSize(9); item.setFont(f)
                self._table.setItem(row, col, item)
        self._table.resizeRowsToContents()
        self._table.currentCellChanged.connect(self._on_row_changed)

        # ---- Right: details + diff -----------------------------------------
        self._meta_label = QLabel("Select a commit to see its diff.")
        self._meta_label.setWordWrap(True)
        self._meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._meta_label.setStyleSheet(
            "padding: 8px; background: palette(alternate-base);")

        self._diff = QPlainTextEdit()
        self._diff.setReadOnly(True)
        f = QFont("Consolas"); f.setStyleHint(QFont.Monospace); f.setPointSize(10)
        self._diff.setFont(f)
        self._diff.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._highlighter = _DiffHighlighter(self._diff.document())

        self._restore_btn = QPushButton("↩ Restore this version")
        self._restore_btn.setToolTip(
            "Roll the document files back to the selected commit. "
            "Your current state stays in the history — restoring just "
            "creates a new commit on top with the older contents.")
        self._restore_btn.clicked.connect(self._on_restore_clicked)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(self._meta_label)
        rlay.addWidget(self._diff, 1)
        rlay.addWidget(self._restore_btn)

        # ---- Splitter -------------------------------------------------------
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._table)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([480, 720])

        outer = QVBoxLayout(self)
        outer.addLayout(branch_bar)
        outer.addWidget(split, 1)

        if self._commits:
            self._table.setCurrentCell(0, 0)

    # ---- helpers -----------------------------------------------------------

    def _graph_col_width(self) -> int:
        """Compute how wide column 0 needs to be for the DAG + labels."""
        max_rail = 1
        max_label_w = 0
        for c in self._commits:
            max_rail = max(max_rail, c["rail"] + 1)
            for pair in c.get("rails_after", []):
                max_rail = max(max_rail, pair[0] + 1, pair[1] + 1)
            for bname in c.get("branches", []):
                max_label_w = max(max_label_w, len(bname) * 8 + 20)
        return GRAPH_PAD + max_rail * GRAPH_COL_W + max_label_w + 20

    # ---- branch management -------------------------------------------------

    def _refresh_branch_bar(self) -> None:
        cur = git_backend.current_branch(self._repo_dir)
        self._branch_label.setText(
            f"Branch: <code>{_html_escape(cur or '(detached)')}</code>")
        branches = git_backend.list_branches(self._repo_dir)
        self._branch_combo.clear()
        local = [b for b in branches if b["remote"] is None]
        for b in local:
            label = b["name"]
            if b["current"]:
                label += "  ← current"
            self._branch_combo.addItem(label, b["name"])

    def _on_switch_branch(self) -> None:
        name = self._branch_combo.currentData()
        if not name:
            return
        cur = git_backend.current_branch(self._repo_dir)
        if name == cur:
            QMessageBox.information(self, "Already there",
                                    f"You are already on branch '{name}'.")
            return
        reply = QMessageBox.question(
            self, "Switch branch",
            f"Switch to branch <b>{_html_escape(name)}</b>?<br><br>"
            f"<span style='color:#666;'>Unsaved changes in the editor "
            f"will be lost. Save first if needed.</span>",
            QMessageBox.Yes | QMessageBox.Cancel)
        if reply != QMessageBox.Yes:
            return
        ok, msg = git_backend.switch_branch(self._repo_dir, name)
        if not ok:
            QMessageBox.warning(self, "Switch failed", msg)
            return
        self._refresh_after_branch_change()
        QMessageBox.information(self, "Switched", msg)

    def _on_create_branch(self) -> None:
        name, ok = QInputDialog.getText(
            self, "New branch", "Branch name:")
        if not ok or not name.strip():
            return
        name = name.strip().replace(" ", "-")
        ok, msg = git_backend.create_branch(self._repo_dir, name)
        if not ok:
            QMessageBox.warning(self, "Create failed", msg)
            return
        # Ask if the user wants to switch to it.
        reply = QMessageBox.question(
            self, "Branch created",
            f"Branch <b>{_html_escape(name)}</b> created.<br>"
            f"Switch to it now?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            ok2, msg2 = git_backend.switch_branch(self._repo_dir, name)
            if not ok2:
                QMessageBox.warning(self, "Switch failed", msg2)
                return
        self._refresh_after_branch_change()

    def _on_delete_branch(self) -> None:
        name = self._branch_combo.currentData()
        if not name:
            return
        cur = git_backend.current_branch(self._repo_dir)
        if name == cur:
            QMessageBox.warning(
                self, "Cannot delete",
                "Cannot delete the branch you are currently on.<br>"
                "Switch to another branch first.")
            return
        reply = QMessageBox.question(
            self, "Delete branch",
            f"Permanently delete branch <b>{_html_escape(name)}</b>?<br><br>"
            f"<span style='color:#666;'>The commits themselves are not "
            f"deleted — they remain reachable from other branches. Only the "
            f"branch pointer is removed.</span>",
            QMessageBox.Yes | QMessageBox.Cancel)
        if reply != QMessageBox.Yes:
            return
        ok, msg = git_backend.delete_branch(self._repo_dir, name)
        if not ok:
            QMessageBox.warning(self, "Delete failed", msg)
            return
        self._refresh_after_branch_change()

    def _refresh_after_branch_change(self) -> None:
        """Reload the graph and branch bar after a branch operation."""
        self._refresh_branch_bar()
        self._commits = git_backend.history_graph(self._repo_dir, limit=300)
        self._graph_delegate = _GraphDelegate(self._commits, self._table)
        self._table.setItemDelegateForColumn(0, self._graph_delegate)
        # Resize the graph column for the new data.
        self._table.horizontalHeader().resizeSection(
            0, self._graph_col_width())
        # Rebuild table rows.
        self._table.setRowCount(0)
        for row, c in enumerate(self._commits):
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(""))
            for col, key in enumerate(("timestamp", "subject", "author"), 1):
                item = QTableWidgetItem(c[key])
                item.setToolTip(c[key])
                self._table.setItem(row, col, item)
        self._table.resizeRowsToContents()
        if self._commits:
            self._table.setCurrentCell(0, 0)
        # Reload the document in the editor if branch changed.
        reload_method = getattr(self._parent_window, "_reload_current", None)
        if callable(reload_method):
            reload_method()

    # ---- commit selection --------------------------------------------------

    def _on_row_changed(self, row: int, *_) -> None:
        if row < 0 or row >= len(self._commits):
            self._meta_label.setText("")
            self._diff.setPlainText("")
            return
        c = self._commits[row]
        body_html = ("<br><pre style='margin:6px 0 0 0;white-space:pre-wrap;'>"
                     f"{_html_escape(c['body'])}</pre>") if c["body"] else ""
        branches_html = ""
        if c.get("branches"):
            tags = " ".join(
                f"<span style='background:#d0e8ff;color:#0a5090;"
                f"padding:1px 5px;border-radius:3px;font-size:9pt;"
                f"font-weight:bold;'>{_html_escape(b)}</span>"
                for b in c["branches"])
            branches_html = f"<br>{tags}"
        self._meta_label.setText(
            f"<b style='font-size: 12pt;'>{_html_escape(c['subject'])}</b>"
            f"{branches_html}"
            f"<br><span style='color:#666;'>"
            f"{_html_escape(c['short_oid'])} &middot; "
            f"{_html_escape(c['author'])} &middot; "
            f"{_html_escape(c['timestamp'])}</span>"
            f"{body_html}"
        )
        diff = git_backend.diff_for_commit(self._repo_dir, c["oid"])
        if not diff:
            diff = "(no diff — empty commit or root commit with no tree)"
        self._diff.setPlainText(diff)

    # ---- restore -----------------------------------------------------------

    def _on_restore_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._commits):
            return
        c = self._commits[row]
        confirm = QMessageBox.question(
            self, "Restore this version",
            f"<b>Roll the document back to this version?</b><br><br>"
            f"<code>{_html_escape(c['short_oid'])}</code> &middot; "
            f"{_html_escape(c['timestamp'])}<br>"
            f"<i>{_html_escape(c['subject'])}</i><br><br>"
            f"<span style='color:#666;'>"
            f"Your current document state isn't lost — every saved "
            f"version is still in the history. The next Ctrl+S will "
            f"record the restored contents as a new commit on top."
            f"</span>",
            QMessageBox.Yes | QMessageBox.Cancel)
        if confirm != QMessageBox.Yes:
            return
        ok, msg = git_backend.restore_to_commit(self._repo_dir, c["oid"])
        if not ok:
            QMessageBox.critical(self, "Restore failed", msg)
            return
        reload_method = getattr(self._parent_window, "_reload_current", None)
        if callable(reload_method):
            reload_method()
        QMessageBox.information(
            self, "Restored",
            f"The document was rolled back to commit "
            f"<code>{_html_escape(c['short_oid'])}</code>.<br><br>"
            f"Save (Ctrl+S) when you're ready — that records the "
            f"restored contents as a new commit on top.")


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))
