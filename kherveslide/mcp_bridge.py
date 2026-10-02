"""In-app half of KherveSlide's MCP support.

``McpBridge`` listens on a loopback TCP port and answers newline-
delimited JSON requests by running the tools in ``mcp_tools.py``
against the live document. ``mcp_server.py`` (the stdio process Claude
launches) is the only intended client.

Why a socket rather than serving MCP from inside the app: MCP hosts
launch their servers as stdio subprocesses they own and restart at
will, while document tools must run on the Qt GUI thread of an
already-running window. The socket is the seam between the two.

Security posture: the listener binds to 127.0.0.1 only, and every
request must carry the random token from the endpoint file, which is
written user-readable only. The bridge is off unless the user turns it
on in AI ▸ Connect to Claude.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from collections import deque
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from . import __version__
from .mcp_server import endpoint_path, state_dir
from .mcp_tools import (
    NO_UNDO_BLOCK_TOOLS, PATH_TOOLS, READ_ONLY_TOOLS, TOOLS, ToolExecutor,
)

#: 0 lets the OS pick a free port; the endpoint file carries the choice.
DEFAULT_PORT = 0

#: Refuse absurd payloads rather than buffering without bound.
_MAX_LINE = 8 * 1024 * 1024

#: What a connected client may do, weakest first. "read" inspects only;
#: "edit" changes the open document and may save it in place; "full"
#: may also open, save-as and export to paths the client chooses.
ACCESS_LEVELS = ("read", "edit", "full")
DEFAULT_ACCESS = "full"

#: How many recent calls the dialog's activity log shows.
_LOG_LEN = 200


def tool_allowed(name: str, access: str) -> bool:
    """Is *name* callable at this access level?"""
    if access == "full":
        return True
    if name in PATH_TOOLS:
        return False
    if access == "edit":
        return True
    return name in READ_ONLY_TOOLS


def _names_a_path(name: str, tool_input: dict) -> bool:
    """Below Full, a client may not pick filesystem paths (a save-as
    path, or a logo file for the theme)."""
    return name in PATH_TOOLS or bool(tool_input.get("path")) \
        or bool(tool_input.get("logo"))


class McpBridge(QObject):
    """Loopback JSON server exposing the AI tool set to MCP clients."""

    started = Signal(int)              # port
    stopped = Signal()
    tool_invoked = Signal(str, str)    # tool name, summary

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self._mw = mainwindow
        self._server: Optional[QTcpServer] = None
        self._buffers: Dict[QTcpSocket, bytes] = {}
        self._token = ""
        self._executor = None
        self._access = DEFAULT_ACCESS
        self._busy = False
        self.log: deque = deque(maxlen=_LOG_LEN)

    # ── Lifecycle ───────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._server is not None and self._server.isListening()

    def port(self) -> int:
        return self._server.serverPort() if self.is_running() else 0

    def token(self) -> str:
        return self._token

    def access(self) -> str:
        return self._access

    def set_access(self, level: str):
        """Change what connected clients may do, effective immediately.

        Hosts cache ``tools/list`` from their startup, so tightening
        this mid-session shows up as a refusal rather than a shorter
        tool list until they reconnect.
        """
        if level not in ACCESS_LEVELS:
            raise ValueError(f"Unknown access level {level!r}")
        self._access = level

    def visible_tools(self) -> list:
        """The tool table as this access level sees it."""
        return [t for t in TOOLS
                if tool_allowed(t["name"], self._access)]

    def start(self, port: int = DEFAULT_PORT) -> bool:
        """Begin listening.  Returns False (with no side effects) if
        the port could not be bound."""
        if self.is_running():
            return True
        server = QTcpServer(self)
        if not server.listen(QHostAddress.LocalHost, port):
            server.deleteLater()
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        self._token = secrets.token_urlsafe(32)
        self._write_endpoint()
        self.started.emit(server.serverPort())
        return True

    def stop(self):
        if self._server is not None:
            for sock in list(self._buffers):
                sock.disconnectFromHost()
            self._buffers.clear()
            self._server.close()
            self._server.deleteLater()
            self._server = None
        self._token = ""
        self._clear_endpoint()
        self.stopped.emit()

    # ── Endpoint file ───────────────────────────────────────────

    def _write_endpoint(self):
        """Publish host/port/token so the stdio server can find us."""
        try:
            os.makedirs(state_dir(), exist_ok=True)
            path = endpoint_path()
            payload = {
                "host": "127.0.0.1",
                "port": self.port(),
                "token": self._token,
                "pid": os.getpid(),
                "version": __version__,
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            try:
                os.chmod(path, 0o600)   # best effort; a no-op on Windows
            except OSError:
                pass
        except Exception:
            pass

    def _clear_endpoint(self):
        try:
            os.remove(endpoint_path())
        except OSError:
            pass

    # ── Socket plumbing ─────────────────────────────────────────

    def _on_new_connection(self):
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_closed(s))

    def _on_closed(self, sock: QTcpSocket):
        self._buffers.pop(sock, None)
        sock.deleteLater()

    def _on_ready_read(self, sock: QTcpSocket):
        buf = self._buffers.get(sock, b"") + bytes(sock.readAll())
        if len(buf) > _MAX_LINE:
            sock.disconnectFromHost()
            self._buffers.pop(sock, None)
            return
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            if line.strip():
                self._handle_line(sock, line)
        self._buffers[sock] = buf

    def _handle_line(self, sock: QTcpSocket, line: bytes):
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception:
            self._reply(sock, None, error="Malformed JSON request.")
            return
        req_id = req.get("id")
        if not secrets.compare_digest(str(req.get("token", "")),
                                      self._token):
            self._reply(sock, req_id, error="Invalid bridge token.")
            return
        method = req.get("method")
        params = req.get("params") or {}
        try:
            if method == "get_status":
                self._reply(sock, req_id, result=self._status())
            elif method == "list_tools":
                self._reply(sock, req_id, result=self.visible_tools())
            elif method == "call_tool":
                self._reply(sock, req_id,
                            result=self._call_tool(params))
            else:
                self._reply(sock, req_id,
                            error=f"Unknown bridge method: {method!r}")
        except Exception as exc:
            self._reply(sock, req_id, error=str(exc))

    def _reply(self, sock: QTcpSocket, req_id, *, result=None, error=None):
        payload = {"id": req_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result
        try:
            data = json.dumps(payload, default=str) + "\n"
        except Exception as exc:
            data = json.dumps(
                {"id": req_id,
                 "error": f"Unserialisable result: {exc}"}) + "\n"
        sock.write(data.encode("utf-8"))
        sock.flush()

    # ── Tool execution (main/GUI thread) ────────────────────────

    def _status(self) -> dict:
        path = self._mw.path
        return {
            "app": "KherveSlide",
            "version": __version__,
            "pid": os.getpid(),
            "access": self._access,
            "presentation": str(path) if path else "Untitled",
        }

    def _record(self, name: str, outcome: str):
        self.log.append({"time": time.strftime("%H:%M:%S"),
                         "tool": name, "outcome": outcome})
        self.tool_invoked.emit(name, outcome)

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        if not name:
            return {"error": "Missing tool name."}
        tool_input = params.get("input") or {}
        if not tool_allowed(name, self._access) or (
                self._access != "full" and _names_a_path(name, tool_input)):
            reason = (
                f"{name} reads or writes a file path you chose, which "
                f"needs MCP access set to 'Full'."
                if _names_a_path(name, tool_input) else
                f"{name} would change the presentation, and MCP access is "
                f"set to 'Read only'.")
            self._record(str(name), "refused")
            return {"error": f"Refused: {reason} The user can change "
                             f"this in AI \u25b8 Connect to Claude."}
        # A compile pumps the Qt event loop while it waits, which can
        # deliver a second request into this handler. Two tool calls
        # interleaving on one document would corrupt both.
        if self._busy:
            self._record(str(name), "busy")
            return {"error": "KherveSlide is still running the previous "
                             "tool call. Retry when it finishes."}
        if self._executor is None:
            self._executor = ToolExecutor(self._mw)
        # Undo is a debounced snapshot history of the whole presentation:
        # flush it right after a mutating call, so a single Ctrl+Z reverts
        # exactly what the remote agent just did.
        self._busy = True
        try:
            result = self._executor.execute(name, tool_input)
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._busy = False
            if name not in NO_UNDO_BLOCK_TOOLS:
                self._mw._flush_pending_capture()
        summary = (result.get("error") if isinstance(result, dict)
                   and "error" in result else "ok")
        self._record(str(name), str(summary))
        return result
