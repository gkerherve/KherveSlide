# KherveSlide — MCP server dialog
# Copyright (C) 2024-2026  Gwilherm Kerherve
# SPDX-License-Identifier: GPL-3.0-or-later

"""Control panel for the assistant connection.

Shows whether the connection is open and wires Claude Desktop, Claude
Code and their relatives up to it.

Nothing here says "MCP" unless the user has to type it somewhere: the
protocol is our problem, not theirs.  What a person needs to know is
which application to connect, that it must be restarted afterwards, and
that they then say "KherveSlide" in the chat -- that last step is
invisible, and skipping it makes a correctly connected assistant look
broken.

Editing ``claude_desktop_config.json`` by hand is the step that stops
people connecting at all, so the dialog detects the applications on
this machine and writes the entry itself (see ``mcp_hosts``).  The
snippet and its Copy button stay for the ones we refuse to rewrite and
for anyone configuring a machine by hand.
"""

from __future__ import annotations

import json
import sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from .mcp_bridge import ACCESS_LEVELS
from .mcp_hosts import HOSTS, Host, cli_command, host_config
from .mcp_server import endpoint_path

#: A literal double quote cannot appear inside an f-string before
#: Python 3.12, and the messages below quote what to type in the chat.
DQ = '"'

#: Access level → (label, what it means).  Order matches ACCESS_LEVELS.
_ACCESS_LABELS = [
    ("Read only", "Read the presentation, its LaTeX and the compiled "
                  "slides."),
    ("Edit",
     "Also add and change slides, boxes and the theme, compile, save in "
     "place."),
    ("Full (recommended)",
     "Also open, save-as, export and use logo / template files Claude "
     "chooses."),
]


class McpServerDialog(QDialog):
    """Enable/disable the bridge and copy the host configuration."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self.setWindowTitle("Connect to Claude")
        self.setMinimumWidth(620)
        self._build_ui()
        self._refresh()
        # Bound methods, not lambdas: PyQt drops the connection when
        # this dialog is destroyed (it is WA_DeleteOnClose), whereas a
        # lambda would outlive it and fire on a deleted widget.
        bridge.started.connect(self._on_bridge_started)
        bridge.stopped.connect(self._refresh)
        bridge.tool_invoked.connect(self._on_tool_invoked)

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)

        blurb = QLabel(
            "Let Claude read and edit this presentation directly — no API "
            "key, it uses the login you already have. Works with "
            "<b>Claude Desktop</b> and <b>Claude Code</b>, and with "
            "Cursor, Cline, VS Code and LM Studio.<br><br>"
            "It can build slides and themes — even recreate your "
            "university's template — and every change it makes is "
            "undoable with Ctrl+Z.")
        blurb.setWordWrap(True)
        lay.addWidget(blurb)

        self._enable = QCheckBox("Let assistants connect to this presentation")
        self._enable.toggled.connect(self._on_toggled)
        lay.addWidget(self._enable)

        self._status = QLabel()
        self._status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._status)

        acc_row = QHBoxLayout()
        acc_row.addWidget(QLabel("The assistant may:"))
        self._access = QComboBox()
        for label, tip in _ACCESS_LABELS:
            self._access.addItem(label)
            self._access.setItemData(self._access.count() - 1, tip,
                                     Qt.ToolTipRole)
        self._access.currentIndexChanged.connect(self._on_access_changed)
        acc_row.addWidget(self._access, 1)
        lay.addLayout(acc_row)

        self._access_hint = QLabel()
        self._access_hint.setWordWrap(True)
        lay.addWidget(self._access_hint)

        host_box = QGroupBox("Connect an application")
        host_lay = QVBoxLayout(host_box)
        host_lay.addWidget(QLabel(
            "Pick yours and press Connect — KherveSlide writes "
            "itself into that application's own settings, so there is "
            "no config file to edit by hand."))
        self._hosts = QListWidget()
        self._hosts.setMaximumHeight(120)
        self._hosts.currentRowChanged.connect(self._refresh_host_buttons)
        host_lay.addWidget(self._hosts)
        hrow = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        hrow.addWidget(self._connect_btn)
        hrow.addWidget(self._disconnect_btn)
        other = QPushButton("Other application\u2026")
        other.setToolTip(
            "Pick any MCP client's JSON config file and add KherveSlide "
            "to it.")
        other.clicked.connect(self._on_other_host)
        hrow.addWidget(other)
        hrow.addStretch(1)
        host_lay.addLayout(hrow)
        self._host_hint = QLabel()
        self._host_hint.setWordWrap(True)
        self._host_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        host_lay.addWidget(self._host_hint)
        lay.addWidget(host_box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Or set it up by hand:"))
        self._flavour = QComboBox()
        self._flavour.addItems([
            "Claude Desktop / Cursor / Zed (JSON)",
            "Claude Code (command line)",
        ])
        self._flavour.currentIndexChanged.connect(self._refresh_snippet)
        row.addWidget(self._flavour, 1)
        lay.addLayout(row)

        self._snippet = QPlainTextEdit()
        self._snippet.setReadOnly(True)
        mono = QFont("Consolas" if sys.platform.startswith("win")
                     else "Monospace")
        mono.setStyleHint(QFont.TypeWriter)
        mono.setPointSize(9)
        self._snippet.setFont(mono)
        self._snippet.setMinimumHeight(150)
        lay.addWidget(self._snippet)

        hint = QLabel(
            "<b>Then say &quot;KherveSlide&quot; in the chat.</b> Claude "
            "only reaches for this presentation when you point it here "
            "&mdash; <i>&quot;in KherveSlide, make an Imperial-style theme "
            "with my logo and add a results slide&quot;</i>. After that "
            "it carries "
            "on in the open presentation.<br><br>"
            "Restart the application after connecting &mdash; it reads "
            "its tool list once at startup &mdash; and leave KherveSlide "
            "running with the box above ticked.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        act_box = QGroupBox("Recent activity")
        act_lay = QVBoxLayout(act_box)
        self._activity = QListWidget()
        self._activity.setMaximumHeight(110)
        act_lay.addWidget(self._activity)
        lay.addWidget(act_box)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        btns.addButton(copy, QDialogButtonBox.ActionRole)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    # ── Behaviour ────────────────────────────────────────────────────

    def _on_bridge_started(self, _port: int):
        self._refresh()

    def _on_tool_invoked(self, name: str, outcome: str):
        self._activity.insertItem(0, f"{name} — {outcome}")
        while self._activity.count() > 50:
            self._activity.takeItem(self._activity.count() - 1)

    def _on_access_changed(self, index: int):
        level = ACCESS_LEVELS[index]
        self._bridge.set_access(level)
        QSettings("kherveDOC", "KherveSlide").setValue(
            "mcp/access", level)
        self._refresh_access_hint()

    def _on_toggled(self, on: bool):
        if on:
            if not self._bridge.start():
                self._enable.setChecked(False)
                self._status.setText(
                    "<b>Could not open a local port.</b> Another "
                    "process may be holding it.")
                return
        else:
            self._bridge.stop()
        self._save_pref(on)
        self._refresh()

    def _save_pref(self, on: bool):
        QSettings("kherveDOC", "KherveSlide").setValue(
            "mcp/enabled", bool(on))

    def _refresh_access_hint(self):
        idx = self._access.currentIndex()
        text = _ACCESS_LABELS[idx][1]
        if ACCESS_LEVELS[idx] == "full":
            text += (" It can read and write files with your "
                     "permissions, so connect only applications you "
                     "trust. Drop to Edit on a shared machine.")
        self._access_hint.setText(text)

    def _refresh(self):
        running = self._bridge.is_running()
        self._enable.blockSignals(True)
        self._enable.setChecked(running)
        self._enable.blockSignals(False)
        self._access.blockSignals(True)
        self._access.setCurrentIndex(
            ACCESS_LEVELS.index(self._bridge.access()))
        self._access.blockSignals(False)
        self._refresh_access_hint()
        self._activity.clear()
        for entry in reversed(self._bridge.log):
            self._activity.addItem(
                f"{entry['time']}  {entry['tool']} — {entry['outcome']}")
        if running:
            extra = ""
            self._status.setText(
                f"<b style='color:#2e7d32'>Listening</b> on "
                f"127.0.0.1:{self._bridge.port()}{extra}<br>"
                f"endpoint file: {endpoint_path()}")
        else:
            self._status.setText(
                "<b style='color:#b71c1c'>Stopped</b> — no assistant "
                "can reach this presentation.")
        self._refresh_snippet()
        self._refresh_hosts()

    # ── Host wiring ──────────────────────────────────────────────────

    def _selected_host(self):
        row = self._hosts.currentRow()
        return HOSTS[row] if 0 <= row < len(HOSTS) else None

    def _refresh_hosts(self):
        """Rebuild the host list, keeping the current selection."""
        row = max(self._hosts.currentRow(), 0)
        self._hosts.blockSignals(True)
        self._hosts.clear()
        for host in HOSTS:
            status = host.status()
            item = QListWidgetItem(f"{host.label} — {status}")
            if status.startswith("connected"):
                item.setForeground(Qt.darkGreen)
            elif status == "not installed":
                item.setForeground(Qt.gray)
            self._hosts.addItem(item)
        self._hosts.setCurrentRow(min(row, len(HOSTS) - 1))
        self._hosts.blockSignals(False)
        self._refresh_host_buttons()

    def _refresh_host_buttons(self):
        host = self._selected_host()
        if host is None:
            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(False)
            self._host_hint.clear()
            return
        connected = host.connected()
        self._connect_btn.setEnabled(not host.manual)
        self._connect_btn.setText(
            "Update entry" if connected and not host.up_to_date()
            else "Connect")
        self._disconnect_btn.setEnabled(connected and not host.manual)
        bits = []
        if host.manual:
            bits.append("Cannot be edited automatically.")
        bits.append(host.note)
        path = host.path()
        if path:
            bits.append(f"<i>{path}</i>")
        self._host_hint.setText("  ".join(b for b in bits if b))

    def _report(self, result: dict):
        """Show what a connect/disconnect actually did."""
        host = result.get("host", "host")
        if not result.get("ok"):
            QMessageBox.warning(self, "Connect to Claude", result.get(
                "error", f"Could not configure {host}."))
            self._refresh_hosts()
            return
        lines = [f"{host}: KherveSlide {result.get('action', 'updated')}.",
                 f"File: {result.get('path', '')}"]
        if result.get("backup"):
            lines.append(f"Previous version saved as "
                         f"{result['backup']}")
        if result.get("restart"):
            lines.append(f"\nRestart {host} for it to take effect.")
        if result.get("action") != "removed":
            # The step with no visible cue: a correctly connected
            # assistant sits there doing nothing until a chat names
            # this application.
            lines.append(
                f"\nThen mention KherveSlide in your chat with {host} "
                f"— say {DQ}in KherveSlide, proofread section 2{DQ} — "
                f"and it will work in the open presentation.")
        QMessageBox.information(self, "Connect to Claude",
                                "\n".join(lines))
        self._refresh_hosts()

    def _nudge_to_enable(self):
        QMessageBox.information(
            self, "Connect to Claude",
            "Tick 'Let assistants connect to this presentation' first — "
            "the entry is only useful while KherveSlide is listening.")

    def _on_connect(self):
        host = self._selected_host()
        if host is None:
            return
        if not self._bridge.is_running():
            self._nudge_to_enable()
            return
        self._report(host.connect())

    def _on_other_host(self):
        """Add KherveSlide to a config file the user points us at.

        The named entries cannot cover every MCP client, and guessing a
        path wrongly is worse than asking.
        """
        if not self._bridge.is_running():
            self._nudge_to_enable()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the client's MCP config file", "",
            "JSON config (*.json);;All files (*)")
        if not path:
            return
        # Match the file's own convention rather than imposing ours:
        # most clients copied Claude Desktop's "mcpServers", VS Code
        # and its relatives use "servers".
        shape = "mcpServers"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            if isinstance(doc, dict) and "servers" in doc \
                    and "mcpServers" not in doc:
                shape = "servers"
        except Exception:
            pass          # empty or unreadable: connect() reports it
        host = Host.for_file(path, shape=shape)
        if shape == "servers":
            host.entry_extra = {"type": "stdio"}
        self._report(host.connect())

    def _on_disconnect(self):
        host = self._selected_host()
        if host is None:
            return
        if QMessageBox.question(
                self, "Connect to Claude",
                f"Remove KherveSlide from {host.label}'s configuration?\n"
                "Other servers are left untouched.",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._report(host.disconnect())

    def _refresh_snippet(self):
        idx = self._flavour.currentIndex()
        if idx == 0:
            self._snippet.setPlainText(host_config())
        elif idx == 1:
            self._snippet.setPlainText(cli_command())

    def _copy(self):
        QApplication.clipboard().setText(self._snippet.toPlainText())
