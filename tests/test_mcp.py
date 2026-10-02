"""MCP connection to Claude: the stdio protocol, the in-app bridge, and
the slide / theme tools, driven against a real (offscreen) window."""
import json
import os
import threading
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KHERVESLIDE_NO_UPDATE", "1")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kherveslide import mcp_bridge, mcp_server  # noqa: E402
from kherveslide.mcp_bridge import tool_allowed  # noqa: E402
from kherveslide.mcp_server import BridgeClient, McpServer  # noqa: E402
from kherveslide.mcp_tools import (  # noqa: E402
    NO_UNDO_BLOCK_TOOLS, PATH_TOOLS, READ_ONLY_TOOLS, TOOLS, ToolExecutor,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def private_assets(tmp_path, monkeypatch):
    """Logos copied by apply_theme_kit go to a temp folder, not the
    user's real theme assets."""
    from kherveslide import theme_import
    monkeypatch.setattr(theme_import, "assets_dir",
                        lambda: tmp_path / "assets")


@pytest.fixture
def window(qapp, monkeypatch):
    from kherveslide.window import SlideWindow
    # No compiles, no package downloads: the tools are what's under test.
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages", "_add_recent",
                 "_forget_recent"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    w = SlideWindow()
    yield w
    if getattr(w, "_mcp_bridge", None) is not None:
        w._mcp_bridge.stop()
    w.close()


def _run(window, _tool, **kw):
    return ToolExecutor(window).execute(_tool, kw)


# ── protocol ───────────────────────────────────────────────────────

class _FakeBridge:
    def __init__(self, result=None):
        self.result = result

    def request(self, method, params=None):
        if method == "get_status":
            return {"version": "9.9"}
        if method == "list_tools":
            return TOOLS[:2]
        return self.result


def test_initialize_reports_version_and_instructions():
    res = McpServer(_FakeBridge()).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26"}})["result"]
    assert res["protocolVersion"] == "2025-03-26"
    assert res["serverInfo"]["name"] == "kherveslide"
    assert "KherveSlide" in res["instructions"]
    assert "import_theme" in res["instructions"]


def test_rendered_slide_is_returned_as_an_image_block():
    srv = McpServer(_FakeBridge({"slide": 0, "image_png_base64": "AAAA"}))
    res = srv.handle({"id": 3, "method": "tools/call",
                      "params": {"name": "render_slide",
                                 "arguments": {"slide": 0}}})["result"]
    assert [c["type"] for c in res["content"]] == ["text", "image"]
    assert "AAAA" not in res["content"][0]["text"]


def test_missing_app_explains_how_to_fix(tmp_path):
    srv = McpServer(BridgeClient(str(tmp_path / "none.json")))
    reply = srv.handle({"id": 5, "method": "tools/list"})
    assert "Connect to Claude" in reply["error"]["message"]


def test_every_tool_has_an_implementation_and_a_category():
    names = {t["name"] for t in TOOLS}
    assert len(names) == len(TOOLS)
    for name in names:
        assert hasattr(ToolExecutor, f"_t_{name}"), name
    for group in (READ_ONLY_TOOLS, NO_UNDO_BLOCK_TOOLS, PATH_TOOLS):
        assert group <= names


def test_access_levels():
    assert tool_allowed("list_slides", "read")
    assert not tool_allowed("add_text", "read")
    assert tool_allowed("add_text", "edit")
    assert not tool_allowed("import_theme", "edit")
    assert tool_allowed("import_theme", "full")


def test_host_entry_runs_this_package():
    from kherveslide.mcp_hosts import server_entry
    entry = server_entry()
    assert entry["args"][-1] == "kherveslide.mcp_server"
    assert "PYTHONPATH" in entry["env"]


# ── tools on a live window ─────────────────────────────────────────

def test_slides_and_objects(window):
    n = len(window.deck.slides)
    r = _run(window, "add_slide", title="Results")
    assert r["ok"] and len(window.deck.slides) == n + 1
    s = r["index"]
    assert window.current == s                 # the user sees it
    t = _run(window, "add_text", slide=s, x=0.1, y=0.3, w=0.5, h=0.2,
             text="\\begin{itemize}\n\\item one\n\\end{itemize}",
             font_pt=22)
    eq = _run(window, "add_equation", slide=s, latex="E=mc^2")
    sh = _run(window, "add_shape", slide=s, shape="ellipse", fill="#FF0000")
    ln = _run(window, "add_line", slide=s, x1=0.1, y1=0.8, x2=0.6, y2=0.8,
              arrow_end=True)
    tb = _run(window, "add_table", slide=s, rows=[["a", "b"], ["1"]])
    assert [t["index"], eq["index"], sh["index"], ln["index"],
            tb["index"]] == [0, 1, 2, 3, 4]
    objs = _run(window, "get_slide", slide=s)["objects"]
    assert [o["kind"] for o in objs] == ["text", "text", "shape", "line",
                                         "table"]
    assert objs[1]["text"] == "\\[E=mc^2\\]"
    assert objs[4]["rows"] == [["a", "b"], ["1", ""]]
    up = _run(window, "update_object", slide=s, index=0,
              changes={"font_pt": "30", "color": "#003E74", "x": 0.2})
    assert up["object"]["font_pt"] == 30 and up["object"]["x"] == 0.2
    assert "error" in _run(window, "update_object", slide=s, index=0,
                           changes={"nonsense": 1})
    assert _run(window, "arrange_object", slide=s, index=0,
                how="front")["index"] == 4
    assert _run(window, "delete_object", slide=s, index=4)["ok"]
    assert "\\item one" not in window.latex_view.source()
    assert "error" in _run(window, "add_shape", slide=s, shape="blob")
    assert "error" in _run(window, "get_slide", slide=99)


def test_slide_operations(window):
    _run(window, "add_slide", title="A")
    _run(window, "add_slide", title="B")
    titles = lambda: [s.title for s in window.deck.slides]  # noqa: E731
    i = titles().index("B")
    _run(window, "move_slide", slide=i, to=0)
    assert titles()[0] == "B"
    _run(window, "duplicate_slide", slide=0)
    assert titles()[:2] == ["B", "B"]
    _run(window, "set_slide", slide=1, title="C", background="#EEEEEE")
    assert window.deck.slides[1].bg == "#EEEEEE"
    _run(window, "delete_slide", slide=1)
    assert "C" not in titles()


def test_presentation_settings(window):
    _run(window, "set_presentation", title="Talk", author="Me",
         page_number="of_total", foot_right="\\today", decorations=True)
    info = _run(window, "get_presentation_info")
    assert info["title"] == "Talk" and info["foot_right"] == "\\today"
    assert window.f_foot_r.text() == "\\today"     # the fields follow
    assert "error" in _run(window, "set_presentation", aspect="99")


def test_theme_kit_and_beamer_theme(window):
    r = _run(window, "apply_theme_kit", preset="UCL-style purple",
             footer_style="bar")
    assert r["ok"] and window.deck.theme_spec.enabled
    th = _run(window, "get_theme")
    assert th["kit"]["primary"] == "#500778"
    assert th["kit"]["footer_style"] == "bar"
    assert "{ks footer bar}" in window.latex_view.source()
    assert "error" in _run(window, "apply_theme_kit", preset="Nope")
    assert "error" in _run(window, "apply_theme_kit",
                           logo="/no/such/logo.png")
    _run(window, "set_beamer_theme", theme="Madrid", color_theme="beaver")
    assert not window.deck.theme_spec.enabled
    assert "\\usetheme{Madrid}" in window.latex_view.source()
    assert "presets" in _run(window, "list_themes")


def test_export_theme_sty_copies_the_logo(window, tmp_path):
    import pymupdf
    logo = tmp_path / "crest.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0)
    pix.save(str(logo))
    _run(window, "apply_theme_kit", primary="#002147", logo=str(logo))
    out = tmp_path / "export"
    r = _run(window, "export_theme_sty", folder=str(out), name="Oxf ord")
    sty = (out / "beamerthemeOxford.sty").read_text()
    assert r["use_with"] == "\\usetheme{Oxford}"
    assert "{crest.png}" in sty                 # relative to the .sty
    assert (out / "crest.png").exists()


def test_unsaved_work_is_not_discarded(window, tmp_path):
    _run(window, "add_slide", title="precious")
    assert _run(window, "get_presentation_info")["unsaved_changes"]
    r = _run(window, "new_presentation")
    assert "unsaved" in r["error"]
    assert "never been saved" in _run(window, "save_presentation")["error"]
    saved = _run(window, "save_presentation", path=str(tmp_path / "t"))
    assert saved["file"].endswith("t.kslide")
    assert not _run(window, "get_presentation_info")["unsaved_changes"]
    assert _run(window, "new_presentation")["ok"]
    assert _run(window, "open_presentation", path=saved["file"])["ok"]
    assert any(s.title == "precious" for s in window.deck.slides)


# ── the bridge over a real socket ──────────────────────────────────

@pytest.fixture
def live(window, tmp_path, monkeypatch):
    ep = tmp_path / "ep.json"
    monkeypatch.setattr(mcp_bridge, "endpoint_path", lambda: str(ep))
    monkeypatch.setattr(mcp_bridge, "state_dir", lambda: str(tmp_path))
    bridge = window.mcp_bridge()
    bridge.set_access("full")
    assert bridge.start()
    yield window, bridge, str(ep)
    bridge.stop()


def _call(qapp, endpoint, method, params=None):
    """Run a blocking client request off-thread while Qt serves it."""
    out = {}

    def run():
        client = BridgeClient(endpoint)
        try:
            out["r"] = client.request(method, params)
        except Exception as exc:
            out["e"] = exc
        finally:
            client.close()

    t = threading.Thread(target=run)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    t.join(1)
    if "e" in out:
        raise out["e"]
    return out["r"]


def test_endpoint_file_is_private_and_removed_on_stop(live):
    window, bridge, ep = live
    info = json.load(open(ep))
    assert info["port"] == bridge.port() and info["token"]
    if os.name != "nt":
        assert oct(os.stat(ep).st_mode & 0o777) == "0o600"
    bridge.stop()
    assert not os.path.exists(ep)


def test_wrong_token_is_refused(live, qapp):
    window, bridge, ep = live
    info = json.load(open(ep))
    info["token"] = "wrong"
    bad = ep + ".bad"
    json.dump(info, open(bad, "w"))
    with pytest.raises(mcp_server.BridgeError, match="token"):
        _call(qapp, bad, "get_status")


def test_one_tool_call_is_one_undo_step(live, qapp):
    window, bridge, ep = live
    n = len(window.slide.objects)
    res = _call(qapp, ep, "call_tool", {
        "name": "add_text",
        "input": {"slide": window.current, "text": "From Claude"}})
    assert res["ok"]
    assert len(window.slide.objects) == n + 1
    window._undo()
    assert len(window.slide.objects) == n


def test_read_access_refuses_edits(live, qapp):
    window, bridge, ep = live
    bridge.set_access("read")
    res = _call(qapp, ep, "call_tool",
                {"name": "add_slide", "input": {}})
    assert res["error"].startswith("Refused")
    names = {t["name"] for t in _call(qapp, ep, "list_tools")}
    assert "add_slide" not in names and "list_slides" in names


def test_edit_access_refuses_client_chosen_paths(live, qapp):
    window, bridge, ep = live
    bridge.set_access("edit")
    for name, args in (("save_presentation", {"path": "/tmp/x.kslide"}),
                       ("apply_theme_kit", {"logo": "/tmp/logo.png"})):
        res = _call(qapp, ep, "call_tool", {"name": name, "input": args})
        assert "Full" in res["error"], name


def test_new_presentation_can_open_an_example(window, tmp_path, monkeypatch):
    from kherveslide.window import SlideWindow
    monkeypatch.setattr(SlideWindow, "examples_dir",
                        staticmethod(lambda: tmp_path))
    names = _run(window, "list_themes")["examples"]
    assert "Research talk" in names
    r = _run(window, "new_presentation", example="Diagrams & workflows",
             discard_unsaved_changes=True)
    assert r["ok"] and r["slides"] >= 5
    assert window.path is None and window.deck.title == "Diagrams with shapes"
    assert "error" in _run(window, "new_presentation", example="Nope",
                           discard_unsaved_changes=True)
