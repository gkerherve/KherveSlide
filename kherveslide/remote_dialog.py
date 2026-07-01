"""Connect your document to a cloud git service (GitHub, GitLab, etc.)
so it gets backed up online and can be shared with collaborators.

The dialog walks users through the setup step by step, using plain
language instead of git jargon. Experienced users can still add
multiple remotes or use SSH URLs — the full flexibility is there,
just not front-and-centre."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import git_backend


class RemoteDialog(QDialog):
    """Guide the user through connecting their document to a cloud
    git service, or manage existing connections."""

    def __init__(self, repo_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo_dir = repo_dir
        self.setWindowTitle("Connect to cloud")
        self.resize(660, 460)

        existing = git_backend.get_remotes(repo_dir)

        # ----- intro text (adapts to whether a remote already exists) -----
        if existing:
            intro_html = (
                "<b>Your document is connected to:</b>"
            )
        else:
            intro_html = (
                "<b>Connect your document to a cloud service</b><br><br>"
                "This lets you:<br>"
                "&nbsp;&nbsp;\u2022 <b>Back up</b> your work online automatically<br>"
                "&nbsp;&nbsp;\u2022 <b>Share</b> your document with collaborators<br>"
                "&nbsp;&nbsp;\u2022 <b>Download</b> changes others have made<br><br>"
                "<b>How to get started:</b><br>"
                "&nbsp;&nbsp;1. Create a repository on "
                "<a href='https://github.com/new'>GitHub</a>, "
                "<a href='https://gitlab.com/projects/new'>GitLab</a>, or similar<br>"
                "&nbsp;&nbsp;2. Copy the repository URL (it looks like "
                "<code>https://github.com/you/my-paper.git</code>)<br>"
                "&nbsp;&nbsp;3. Click <b>\"Add connection\"</b> below and paste the URL"
            )

        intro = QLabel(intro_html)
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        intro.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)

        # ----- connection table -----
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Name", "URL"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)

        btn_add = QPushButton("\u2795 &Add connection")
        btn_add.setToolTip(
            "Add a new cloud link (you'll need the repository URL)")
        btn_edit = QPushButton("\u270f &Edit URL")
        btn_edit.setToolTip("Change the URL of the selected connection")
        btn_del = QPushButton("\u2716 &Remove")
        btn_del.setToolTip(
            "Remove this connection (does NOT delete anything on the server)")

        btn_add.clicked.connect(self._add)
        btn_edit.clicked.connect(self._edit)
        btn_del.clicked.connect(self._remove)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)

        # ----- help text at the bottom -----
        help_label = QLabel(
            "<span style='color: #666;'>"
            "<b>Where do I find the URL?</b> "
            "On GitHub, go to your repository page and click the green "
            "<b>\"Code\"</b> button \u2014 copy the HTTPS link. "
            "It looks like: <code>https://github.com/username/repo.git</code>"
            "</span>")
        help_label.setWordWrap(True)
        help_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)

        outer = QVBoxLayout(self)
        outer.addWidget(intro)
        outer.addWidget(self._table, 1)
        outer.addLayout(btn_row)
        outer.addWidget(help_label)
        outer.addWidget(buttons)

        self._refresh()

    def _refresh(self) -> None:
        remotes = git_backend.get_remotes(self._repo_dir)
        self._table.setRowCount(0)
        for name, url in remotes:
            row = self._table.rowCount()
            self._table.insertRow(row)
            n_item = QTableWidgetItem(name)
            u_item = QTableWidgetItem(url)
            for it in (n_item, u_item):
                it.setToolTip(it.text())
            self._table.setItem(row, 0, n_item)
            self._table.setItem(row, 1, u_item)
        if self._table.rowCount():
            self._table.setCurrentCell(0, 0)

    def _current_row(self) -> tuple[str, str] | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        n_item = self._table.item(row, 0)
        u_item = self._table.item(row, 1)
        if n_item is None or u_item is None:
            return None
        return n_item.text(), u_item.text()

    def _add(self) -> None:
        existing = {n for n, _ in git_backend.get_remotes(self._repo_dir)}
        default_name = "origin" if "origin" not in existing else ""
        name, ok = QInputDialog.getText(
            self, "Add connection",
            "Connection name (most people use \"origin\"):",
            text=default_name)
        name = name.strip()
        if not ok or not name:
            return
        if name in existing:
            QMessageBox.warning(
                self, "Already exists",
                f"A connection called \"{name}\" already exists.\n\n"
                "Use \"Edit URL\" to change where it points.")
            return
        url, ok = QInputDialog.getText(
            self, "Add connection",
            "Paste the repository URL here:\n\n"
            "Examples:\n"
            "  https://github.com/username/my-paper.git\n"
            "  git@github.com:username/my-paper.git")
        url = url.strip()
        if not ok or not url:
            return
        if not git_backend.set_remote(self._repo_dir, name, url):
            QMessageBox.critical(
                self, "Could not add connection",
                "Something went wrong. Make sure the URL is valid "
                "and try again.")
            return
        self._refresh()
        QMessageBox.information(
            self, "Connected!",
            f"Your document is now linked to:\n\n  {url}\n\n"
            "From now on, every time you save your document it will "
            "automatically be uploaded there.\n\n"
            "You can also use Git \u2192 Download latest "
            "to get changes from collaborators.")

    def _edit(self) -> None:
        current = self._current_row()
        if current is None:
            QMessageBox.information(
                self, "Edit URL",
                "Select a connection in the list first.")
            return
        name, old_url = current
        new_url, ok = QInputDialog.getText(
            self, f"Edit \"{name}\"",
            f"New URL for \"{name}\":", text=old_url)
        new_url = new_url.strip()
        if not ok or not new_url or new_url == old_url:
            return
        if not git_backend.set_remote(self._repo_dir, name, new_url):
            QMessageBox.critical(
                self, "Could not update",
                "Failed to update the URL. Make sure it is valid.")
            return
        self._refresh()

    def _remove(self) -> None:
        current = self._current_row()
        if current is None:
            QMessageBox.information(
                self, "Remove connection",
                "Select a connection in the list first.")
            return
        name, _ = current
        confirm = QMessageBox.question(
            self, "Remove connection",
            f"Remove the connection \"{name}\"?\n\n"
            "This only removes the link from this computer \u2014 nothing "
            "is deleted on the server. You can always re-add it later.")
        if confirm != QMessageBox.Yes:
            return
        if not git_backend.remove_remote(self._repo_dir, name):
            QMessageBox.critical(
                self, "Could not remove",
                f"Failed to remove \"{name}\". Try again or restart the app.")
            return
        self._refresh()
