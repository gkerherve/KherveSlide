"""MCP (Model Context Protocol) stdio server for KherveSlide.

The client-facing half of KherveSlide's MCP support. It speaks JSON-RPC
2.0 over stdin/stdout — the transport Claude Desktop and Claude Code
launch — and forwards each ``tools/call`` to a running KherveSlide window
over a loopback socket (see ``mcp_bridge.py``).

Document tools touch live Qt widgets, so they must run inside the
application's GUI thread; the host instead wants a short-lived
subprocess it owns. This file is that subprocess and imports no Qt and
no third-party package, so it starts in milliseconds from any Python::

    python -m kherveslide.mcp_server        # from a checkout
    KherveSlide --mcp-server                # frozen build
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any, List, Optional


# ── Protocol constants ─────────────────────────────────────────────

#: Spec revisions we know how to speak.  We echo the client's choice
#: when it is one of these, otherwise we answer with our newest.
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL = SUPPORTED_PROTOCOLS[0]

SERVER_NAME = "kherveslide"

#: Endpoint file written by the in-app bridge; names host, port, token.
ENDPOINT_FILENAME = "mcp-bridge.json"

_CONNECT_TIMEOUT = 5.0    # seconds to establish the bridge socket
_CALL_TIMEOUT = 330.0     # a first compile can download packages


# ── Endpoint discovery ─────────────────────────────────────────────

def state_dir() -> str:
    """Directory holding KherveSlide's per-user runtime state.

    Kept free of Qt so both halves of the MCP stack agree on the path
    without the stdio server having to import PySide6.
    """
    if sys.platform.startswith("win"):
        base = (os.environ.get("LOCALAPPDATA")
                or os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(base, "KherveSlide")
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/KherveSlide")
    base = (os.environ.get("XDG_CONFIG_HOME")
            or os.path.expanduser("~/.config"))
    return os.path.join(base, "KherveSlide")


def endpoint_path() -> str:
    """Full path of the bridge endpoint description file."""
    return os.path.join(state_dir(), ENDPOINT_FILENAME)


def read_endpoint(path: Optional[str] = None) -> Optional[dict]:
    """Load the endpoint file, or None when the app is not serving."""
    try:
        with open(path or endpoint_path(), "r", encoding="utf-8") as fh:
            info = json.load(fh)
    except Exception:
        return None
    if not isinstance(info, dict) or "port" not in info:
        return None
    return info


_NOT_RUNNING = (
    "KherveSlide is not reachable.\n\n"
    "The MCP server drives a live KherveSlide window, so the "
    "application must be running with its bridge enabled:\n"
    "  1. Start KherveSlide.\n"
    "  2. Enable AI ▸ Connect to Claude.\n"
    "Then retry — no need to restart this MCP connection."
)


class BridgeError(RuntimeError):
    """Raised when the running application cannot be reached."""


#: Sent to the client on initialize.  The host writes its own system
#: prompt, so anything a model must know before touching someone's
#: open document has to travel with the connection.
_INSTRUCTIONS = """\
These tools drive a LIVE KherveSlide window — a PowerPoint-style slide \
designer whose presentation is compiled to PDF with LaTeX beamer. \
Everything you do lands in the presentation the user has open in front \
of them, immediately.

Working rules:
- Call get_presentation_info, then list_slides, before changing \
anything. Slides are 0-based; objects on a slide are 0-based in \
stacking order (0 = bottom). Indices shift after inserts and deletes, \
so re-read rather than reusing stale numbers.
- Geometry is x, y, w, h as FRACTIONS of the slide (0..1), (x, y) the \
top-left corner. Leave ~0.05 margins; the frame title bar takes about \
the top 0.15 when the theme has one.
- Text is LaTeX: $maths$, \\textbf{}, and bullets as \\begin{itemize} \
/ \\item on separate lines. Equations: add_equation takes the maths \
alone. A slide's title goes in set_slide(title=…), not a text box.
- Check your work: render_slide shows the compiled slide as an image.
- Themes: to recreate a university or company template (Imperial, \
UCL, Oxford…), prefer import_theme on the template file the user has \
(.potx/.pptx, a beamer .sty/.zip, or a picture/PDF of a slide). Without \
a file, use apply_theme_kit: main colour, accent, title_style \
(bar | plain | underline), footer_style (bar | line | none), a logo \
image the user supplies, its corner and size, typeface and bullets — \
then render_slide and adjust. Do not invent institutional logos. \
export_theme_sty writes the theme as a standard beamer .sty.
- Every tool call is one step on the undo stack, so the user can \
Ctrl+Z it — but their unsaved work is real. open_presentation and \
new_presentation refuse to discard it unless you pass \
discard_unsaved_changes; save instead of discarding.
- The user controls what you may do (AI ▸ Connect to Claude). A \
refusal naming an access level is their setting, not a bug — tell \
them what you needed rather than working around it.
"""


# ── Bridge client ──────────────────────────────────────────────────

class BridgeClient:
    """Line-delimited JSON client for the in-app bridge.

    Connects lazily and reconnects on demand so that the MCP host may
    start this process before (or after) KherveSlide itself, and so a
    restart of the application does not require a restart of the host.
    """

    def __init__(self, endpoint_file: Optional[str] = None):
        self._endpoint_file = endpoint_file
        self._sock: Optional[socket.socket] = None
        self._buf = b""
        self._token = ""
        self._next_id = 0

    # ── Connection handling ─────────────────────────────────────

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._buf = b""

    def _connect(self):
        info = read_endpoint(self._endpoint_file)
        if info is None:
            raise BridgeError(_NOT_RUNNING)
        self._token = str(info.get("token", ""))
        host = str(info.get("host", "127.0.0.1"))
        port = int(info["port"])
        try:
            sock = socket.create_connection(
                (host, port), timeout=_CONNECT_TIMEOUT)
        except OSError as exc:
            # A stale endpoint file (app killed without cleanup) looks
            # exactly like "not running" from here — say so plainly
            # rather than leaking a connection-refused traceback.
            raise BridgeError(f"{_NOT_RUNNING}\n\n(socket error: {exc})")
        sock.settimeout(_CALL_TIMEOUT)
        self._sock = sock
        self._buf = b""

    def _readline(self) -> bytes:
        assert self._sock is not None
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise BridgeError(
                    "KherveSlide closed the connection mid-request. "
                    "The application may have quit.")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line

    def request(self, method: str, params: Optional[dict] = None) -> Any:
        """Send one request, returning its ``result`` payload."""
        for attempt in (0, 1):
            if self._sock is None:
                self._connect()
            self._next_id += 1
            payload = {
                "id": self._next_id,
                "token": self._token,
                "method": method,
                "params": params or {},
            }
            try:
                assert self._sock is not None
                self._sock.sendall(
                    (json.dumps(payload) + "\n").encode("utf-8"))
                line = self._readline()
            except BridgeError:
                self.close()
                if attempt == 0:
                    continue          # app restarted: reconnect once
                raise
            except OSError as exc:
                self.close()
                if attempt == 0:
                    continue
                raise BridgeError(f"Bridge I/O error: {exc}")
            try:
                reply = json.loads(line.decode("utf-8"))
            except Exception:
                self.close()
                raise BridgeError("Malformed reply from KherveSlide.")
            if reply.get("error"):
                raise BridgeError(str(reply["error"]))
            return reply.get("result")
        raise BridgeError(_NOT_RUNNING)


# ── MCP server ─────────────────────────────────────────────────────

def _log(msg: str):
    """Diagnostics go to stderr — stdout carries the protocol."""
    sys.stderr.write(f"[kherveslide-mcp] {msg}\n")
    sys.stderr.flush()


class McpServer:
    """Minimal, dependency-free MCP server over stdio."""

    def __init__(self, bridge: BridgeClient):
        self._bridge = bridge
        self._tools_cache: Optional[List[dict]] = None

    # ── Dispatch ────────────────────────────────────────────────

    def handle(self, msg: dict) -> Optional[dict]:
        """Handle one JSON-RPC message; None means 'no reply'."""
        method = msg.get("method")
        msg_id = msg.get("id")
        if method is None:                    # a response — ignore
            return None
        try:
            if method == "initialize":
                result = self._initialize(msg.get("params") or {})
            elif method in ("notifications/initialized",
                            "notifications/cancelled",
                            "initialized"):
                return None                   # notifications: no reply
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._list_tools()}
            elif method == "tools/call":
                result = self._call_tool(msg.get("params") or {})
            elif method in ("resources/list", "resources/templates/list"):
                # Declared empty rather than unsupported so hosts that
                # probe every capability do not surface an error.
                key = ("resourceTemplates"
                       if method.endswith("templates/list")
                       else "resources")
                result = {key: []}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                if msg_id is None:
                    return None
                return _error(msg_id, -32601, f"Unknown method: {method}")
        except BridgeError as exc:
            if msg_id is None:
                return None
            return _error(msg_id, -32000, str(exc))
        except Exception as exc:              # never take the loop down
            if msg_id is None:
                return None
            return _error(msg_id, -32603, f"Internal error: {exc}")
        if msg_id is None:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # ── Methods ─────────────────────────────────────────────────

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion")
        version = (asked if asked in SUPPORTED_PROTOCOLS
                   else LATEST_PROTOCOL)
        # Best-effort: the app may not be up yet, and initialize must
        # never fail for that reason.
        app_version = "unknown"
        try:
            status = self._bridge.request("get_status")
            app_version = str((status or {}).get("version", "unknown"))
        except Exception:
            pass
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {},
                "prompts": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "KherveSlide",
                "version": app_version,
            },
            "instructions": _INSTRUCTIONS,
        }

    def _list_tools(self) -> List[dict]:
        if self._tools_cache is None:
            tools = self._bridge.request("list_tools") or []
            self._tools_cache = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "inputSchema": t.get(
                        "input_schema", {"type": "object",
                                         "properties": {}}),
                }
                for t in tools
            ]
        return self._tools_cache

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        if not name:
            raise BridgeError("tools/call requires a tool name.")
        args = params.get("arguments") or {}
        result = self._bridge.request(
            "call_tool", {"name": name, "input": args})
        is_error = isinstance(result, dict) and "error" in result
        content = []
        if isinstance(result, dict) and result.get("image_png_base64"):
            # A rendered page travels as a real image block, not as a
            # wall of base64 text the model cannot see.
            result = dict(result)
            content.append({"type": "image", "mimeType": "image/png",
                            "data": result.pop("image_png_base64")})
        content.insert(0, {"type": "text",
                           "text": json.dumps(result, indent=2,
                                              default=str)})
        return {"content": content, "isError": bool(is_error)}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


# ── Entry point ────────────────────────────────────────────────────

def serve(endpoint_file: Optional[str] = None) -> int:
    """Run the stdio loop until stdin closes."""
    bridge = BridgeClient(endpoint_file)
    server = McpServer(bridge)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    _log(f"listening on stdio; endpoint="
         f"{endpoint_file or endpoint_path()}")
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except Exception as exc:
            _log(f"bad JSON on stdin: {exc}")
            continue
        # A host may batch messages into a JSON array.
        batch = msg if isinstance(msg, list) else [msg]
        replies = [r for r in (server.handle(m) for m in batch)
                   if r is not None]
        for reply in replies:
            stdout.write((json.dumps(reply) + "\n").encode("utf-8"))
        if replies:
            stdout.flush()
    bridge.close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    endpoint_file = None
    if "--endpoint" in args:
        i = args.index("--endpoint")
        if i + 1 < len(args):
            endpoint_file = args[i + 1]
    return serve(endpoint_file)


if __name__ == "__main__":
    sys.exit(main())
