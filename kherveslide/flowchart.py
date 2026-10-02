"""Flowcharts for LaTeX — the model behind the flowchart builder.

A :class:`Flowchart` is a set of nodes (the classic flowchart shapes) on
a grid and the arrows between them. :func:`to_tikz` writes it as a TikZ
picture; :func:`standalone_doc` wraps that in a document the builder
compiles for its live preview and for the slide, where the chart is
placed as a vector PDF with its source kept beside it (``.flow.json``,
reopened on double-click) and the TikZ itself (``.tikz``, to reuse in
any LaTeX document).

No Qt here, so it is fully testable.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

# kind -> (label, TikZ shape options)
KINDS: dict[str, tuple[str, str]] = {
    "terminal": ("Start / end", "rounded rectangle, minimum width=2.4cm"),
    "process": ("Process", "rectangle, minimum width=2.6cm"),
    "decision": ("Decision", "diamond, aspect=1.8, inner sep=1pt,"
                             " minimum width=2.6cm"),
    "io": ("Input / output", "trapezium, trapezium left angle=72,"
                             " trapezium right angle=108,"
                             " minimum width=2.4cm"),
    "document": ("Document", "tape, tape bend top=none,"
                             " minimum width=2.4cm"),
    "database": ("Data", "cylinder, shape border rotate=90, aspect=0.22,"
                         " minimum width=2.2cm"),
    "subprocess": ("Sub-process", "rectangle, double, double distance=1.6pt,"
                                  " minimum width=2.6cm"),
    "connector": ("Connector", "circle, minimum size=0.8cm, inner sep=1pt"),
    "note": ("Note", "rectangle, dashed, minimum width=2.2cm"),
}

# Colour schemes: kind -> (fill, text colour); "line" is the arrows /
# outlines. "presentation" is filled in from the presentation's theme.
SCHEMES: dict[str, dict[str, tuple[str, str]]] = {
    "Blue": {"terminal": ("#1F4E79", "#FFFFFF"), "process": ("#DEEBF7", "#1A1A1A"),
             "decision": ("#FCE4C4", "#1A1A1A"), "io": ("#E2EFDA", "#1A1A1A"),
             "line": ("#404040", "")},
    "Green": {"terminal": ("#2E6B30", "#FFFFFF"), "process": ("#E3EDE3", "#1A1A1A"),
              "decision": ("#FFF2CC", "#1A1A1A"), "io": ("#DDEBF7", "#1A1A1A"),
              "line": ("#404040", "")},
    "Purple": {"terminal": ("#500778", "#FFFFFF"), "process": ("#EFE3F5", "#1A1A1A"),
               "decision": ("#F8D7E3", "#1A1A1A"), "io": ("#E0F0EF", "#1A1A1A"),
               "line": ("#404040", "")},
    "Pastel": {"terminal": ("#F4B6C2", "#1A1A1A"), "process": ("#CDE7F0", "#1A1A1A"),
               "decision": ("#FFF1B8", "#1A1A1A"), "io": ("#D5F0D5", "#1A1A1A"),
               "line": ("#555555", "")},
    "Black & white": {"terminal": ("#FFFFFF", "#000000"),
                      "process": ("#FFFFFF", "#000000"),
                      "decision": ("#FFFFFF", "#000000"),
                      "io": ("#FFFFFF", "#000000"), "line": ("#000000", "")},
}
SCHEME_NAMES = ["Presentation colours", *SCHEMES]


@dataclass
class Node:
    id: str
    kind: str = "process"
    text: str = ""
    x: float = 0.0          # grid position (columns), right is positive
    y: float = 0.0          # grid position (rows), down is positive
    fill: str = ""          # "" = from the colour scheme


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    route: str = "auto"     # auto | straight | elbow
    dashed: bool = False
    head: str = "end"       # arrowheads: end | start | both | none (a line)
    src_side: str = "auto"  # where it leaves: auto | north | south | east | west
    dst_side: str = "auto"  # where it arrives (same choices)


#: Arrowhead choices: key -> (label, TikZ arrow spec).
HEADS = {"end": ("→  Arrow", "->"), "start": ("←  Reversed arrow", "<-"),
         "both": ("↔  Both ends", "<->"), "none": ("—  Line, no arrow", "-")}
#: Sides of a box an arrow can leave from / arrive at.
SIDES = {"auto": "Automatic", "north": "Top", "south": "Bottom",
         "east": "Right", "west": "Left"}
_STUB = {"north": "(0,0.35)", "south": "(0,-0.35)", "east": "(0.35,0)",
         "west": "(-0.35,0)"}


@dataclass
class Flowchart:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    direction: str = "TB"   # TB (top to bottom) | LR (left to right)
    scheme: str = "Presentation colours"
    font_pt: int = 11
    col_cm: float = 3.6     # grid spacing
    row_cm: float = 1.7

    # ---- editing helpers ----
    def node(self, nid: str) -> Node | None:
        return next((n for n in self.nodes if n.id == nid), None)

    def new_id(self) -> str:
        used = {n.id for n in self.nodes}
        i = 1
        while f"n{i}" in used:
            i += 1
        return f"n{i}"

    def add(self, kind: str, text: str = "", after: str | None = None,
            label: str = "") -> Node:
        """Add a node; *after* places it one step on from that node (down
        or right, on a free spot) and connects the two."""
        x = y = 0.0
        prev = self.node(after) if after else None
        if prev is not None:
            dx, dy = (0, 1) if self.direction == "TB" else (1, 0)
            x, y = prev.x + dx, prev.y + dy
            while any(abs(n.x - x) < 0.5 and abs(n.y - y) < 0.5
                      for n in self.nodes):
                x, y = x + dy, y + dx           # sidestep
        elif self.nodes:
            last = self.nodes[-1]
            x, y = (last.x, last.y + 1) if self.direction == "TB" \
                else (last.x + 1, last.y)
        n = Node(self.new_id(), kind, text or KINDS[kind][0], x, y)
        self.nodes.append(n)
        if prev is not None:
            self.connect(prev.id, n.id, label)
        return n

    def connect(self, src: str, dst: str, label: str = "") -> Edge | None:
        if src == dst or self.node(src) is None or self.node(dst) is None:
            return None
        for e in self.edges:
            if e.src == src and e.dst == dst:
                return e
        e = Edge(src, dst, label)
        self.edges.append(e)
        return e

    def remove(self, nid: str) -> None:
        self.nodes = [n for n in self.nodes if n.id != nid]
        self.edges = [e for e in self.edges if nid not in (e.src, e.dst)]

    # ---- persistence ----
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Flowchart":
        d = json.loads(text)
        fc = cls(**{k: v for k, v in d.items()
                    if k in ("direction", "scheme", "font_pt", "col_cm",
                             "row_cm")})
        fc.nodes = [Node(**n) for n in d.get("nodes", [])]
        fc.edges = [Edge(**e) for e in d.get("edges", [])]
        return fc


# ------------------------------------------------------------------ layout
def auto_layout(fc: Flowchart) -> None:
    """Tidy up: rank nodes by their longest path from a start node (back
    edges ignored), then spread each rank around the centre line."""
    ids = [n.id for n in fc.nodes]
    if not ids:
        return
    out: dict[str, list[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in fc.edges:
        if e.src in out and e.dst in out:
            out[e.src].append(e.dst)
            indeg[e.dst] += 1
    starts = [i for i in ids if indeg[i] == 0] or [ids[0]]
    rank = {i: 0 for i in starts}
    order = list(starts)
    seen_edges: set = set()
    k = 0
    while k < len(order):
        u = order[k]
        k += 1
        for v in out[u]:
            if (u, v) in seen_edges:
                continue
            seen_edges.add((u, v))
            if v not in rank:
                rank[v] = rank[u] + 1
                order.append(v)
            elif rank[v] <= rank[u] and v not in _ancestors(u, out, rank):
                rank[v] = rank[u] + 1
                order.append(v)
    for i in ids:
        rank.setdefault(i, 0)
    levels: dict[int, list[str]] = {}
    for i in ids:
        levels.setdefault(rank[i], []).append(i)
    for r, members in levels.items():
        for j, nid in enumerate(members):
            off = j - (len(members) - 1) / 2
            n = fc.node(nid)
            if fc.direction == "TB":
                n.x, n.y = off, float(r)
            else:
                n.x, n.y = float(r), off


def _ancestors(u: str, out: dict, rank: dict) -> set:
    """Nodes that can reach *u* (so an edge back to them is a loop)."""
    rev: dict[str, list[str]] = {}
    for a, bs in out.items():
        for b in bs:
            rev.setdefault(b, []).append(a)
    seen, stack = set(), [u]
    while stack:
        x = stack.pop()
        for p in rev.get(x, []):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


# -------------------------------------------------------------------- TikZ
def _hex(h: str) -> str:
    return (h or "").lstrip("#").upper()


def colours(fc: Flowchart, primary: str = "#1F4E79") -> dict:
    """kind -> (fill, text) for the chart's scheme ("Presentation colours"
    tints the presentation's main colour)."""
    if fc.scheme in SCHEMES:
        base = SCHEMES[fc.scheme]
    else:
        base = {"terminal": (primary, _readable(primary)),
                "process": (_tint(primary, 0.86), "#1A1A1A"),
                "decision": ("#FCE4C4", "#1A1A1A"),
                "io": (_tint(primary, 0.72), "#1A1A1A"),
                "line": ("#404040", "")}
    out = {}
    for kind in KINDS:
        fallback = base["process"] if kind in ("subprocess", "document",
                                               "database") else (
            base["terminal"] if kind == "connector" else ("#FFFFFF",
                                                          "#555555"))
        out[kind] = base.get(kind, fallback)
    out["line"] = base["line"]
    return out


def _tint(h: str, amount: float) -> str:
    h = _hex(h)
    if len(h) != 6:
        return "#EEEEEE"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(f"{round(c + (255 - c) * amount):02X}"
                         for c in (r, g, b))


def _readable(h: str) -> str:
    h = _hex(h)
    if len(h) != 6:
        return "#FFFFFF"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 \
        else "#FFFFFF"


def _route(fc: Flowchart, e: Edge) -> str:
    """The TikZ path between two nodes: straight when they line up, an
    elbow otherwise, and around the side for a loop back."""
    a, b = fc.node(e.src), fc.node(e.dst)
    lbl = _label(e)
    if e.src_side != "auto" or e.dst_side != "auto":
        return _sided_route(fc, e, lbl)
    if e.route == "straight" or abs(a.x - b.x) < 0.01 or abs(a.y - b.y) < 0.01:
        if (fc.direction == "TB" and b.y < a.y and abs(a.x - b.x) < 0.01) or \
                (fc.direction == "LR" and b.x < a.x and abs(a.y - b.y) < 0.01):
            # loop back along the same line: go round the side (the
            # left / bottom, away from decision branches on the right)
            side = "west" if fc.direction == "TB" else "south"
            step = "++(-1.9,0)" if fc.direction == "TB" else "++(0,-1.3)"
            turn = "|-" if fc.direction == "TB" else "-|"
            return (f"({e.src}.{side}) -- {step}{lbl} {turn} "
                    f"({e.dst}.{side})")
        return f"({e.src}) --{lbl} ({e.dst})"
    first_across = (a.x != b.x) if fc.direction == "TB" else (a.y != b.y)
    decision = a.kind == "decision"
    if fc.direction == "TB":
        turn = "-|" if (decision and first_across) else "|-"
    else:
        turn = "|-" if (decision and first_across) else "-|"
    return f"({e.src}) {turn}{lbl} ({e.dst})"


def _sided_route(fc: Flowchart, e: Edge, lbl: str) -> str:
    """A path that leaves / arrives at the chosen sides: a short stub out
    of the start side, then an elbow that comes into the end side head
    on (a top / bottom side is reached vertically, left / right
    horizontally)."""
    start = f"({e.src})"
    if e.src_side in _STUB:
        start = f"({e.src}.{e.src_side}) -- ++{_STUB[e.src_side]}"
    end = f"({e.dst}.{e.dst_side})" if e.dst_side in _STUB else f"({e.dst})"
    if e.route == "straight":
        return f"{start} --{lbl} {end}"
    if e.dst_side in ("north", "south"):
        turn = "-|"                       # finish going up / down
    elif e.dst_side in ("east", "west"):
        turn = "|-"                       # finish going sideways
    else:
        turn = "|-" if e.src_side in ("east", "west") else "-|"
    return f"{start} {turn}{lbl} {end}"


def _label(e: Edge) -> str:
    if not e.label:
        return ""
    return (f" node[pos=0.25, auto, font=\\sffamily\\footnotesize,"
            f" inner sep=2pt, text width=]"
            f" {{{e.label}}}")


def to_tikz(fc: Flowchart, primary: str = "#1F4E79") -> str:
    """The flowchart as a TikZ picture (needs the shapes.geometric,
    shapes.misc, shapes.symbols and arrows.meta libraries)."""
    cols = colours(fc, primary)
    lines = ["\\begin{tikzpicture}[",
             f"  font=\\sffamily\\fontsize{{{fc.font_pt}}}"
             f"{{{round(fc.font_pt * 1.2)}}}\\selectfont,",
             f"  >={{Stealth[length=2.4mm]}},",
             "  every node/.style={align=center, minimum height=0.9cm,"
             " inner sep=4pt, text width=2.4cm},",
             f"  line/.style={{draw=fc-line, thick}},",
             "]"]
    defs = [f"\\definecolor{{fc-line}}{{HTML}}{{{_hex(cols['line'][0])}}}"]
    for kind in KINDS:
        fill, text = cols[kind]
        defs.append(f"\\definecolor{{fc-{kind}}}{{HTML}}{{{_hex(fill)}}}")
        defs.append(f"\\definecolor{{fc-{kind}-text}}{{HTML}}"
                    f"{{{_hex(text)}}}")
    body = []
    for n in fc.nodes:
        shape = KINDS.get(n.kind, KINDS["process"])[1]
        width = "" if n.kind != "connector" else ", text width=0.5cm"
        fill = f"fc-{n.kind}"
        if n.fill:
            defs.append(f"\\definecolor{{fc-{n.id}}}{{HTML}}"
                        f"{{{_hex(n.fill)}}}")
            fill = f"fc-{n.id}"
        x = n.x * fc.col_cm
        y = -n.y * fc.row_cm
        body.append(f"  \\node[{shape}{width}, draw=fc-line, fill={fill},"
                    f" text=fc-{n.kind}-text] ({n.id}) at ({x:.2f},{y:.2f})"
                    f" {{{n.text}}};")
    for e in fc.edges:
        if fc.node(e.src) is None or fc.node(e.dst) is None:
            continue
        arrow = HEADS.get(e.head, HEADS["end"])[1]
        style = f"line, {arrow}" + (", dashed" if e.dashed else "")
        body.append(f"  \\draw[{style}] {_route(fc, e)};")
    return "\n".join(defs + lines + body + ["\\end{tikzpicture}"]) + "\n"


TIKZ_LIBRARIES = ("shapes.geometric", "shapes.misc", "shapes.symbols",
                  "arrows.meta")


def standalone_doc(fc: Flowchart, primary: str = "#1F4E79") -> str:
    """A cropped standalone document drawing the chart (sans-serif Latin
    Modern, like the slides)."""
    return "\n".join([
        "\\documentclass[border=4pt]{standalone}",
        "\\usepackage{lmodern}",
        "\\usepackage{tikz}",
        f"\\usetikzlibrary{{{','.join(TIKZ_LIBRARIES)}}}",
        "\\begin{document}",
        to_tikz(fc, primary).rstrip(),
        "\\end{document}", ""])


# --------------------------------------------------------------- templates
def _chain(fc: Flowchart, steps: list[tuple[str, str]]) -> None:
    prev = None
    for kind, text in steps:
        prev = fc.add(kind, text, after=prev.id if prev else None)


def template_simple() -> Flowchart:
    fc = Flowchart()
    _chain(fc, [("terminal", "Start"), ("process", "Collect data"),
                ("process", "Analyse"), ("terminal", "Report")])
    return fc


def template_decision() -> Flowchart:
    fc = Flowchart()
    start = fc.add("terminal", "Start")
    run = fc.add("process", "Run the experiment", after=start.id)
    check = fc.add("decision", "Result valid?", after=run.id)
    done = fc.add("terminal", "Publish", after=check.id, label="Yes")
    fix = Node(fc.new_id(), "process", "Adjust the setup", 1.3, check.y)
    fc.nodes.append(fix)
    fc.connect(check.id, fix.id, "No")
    fc.connect(fix.id, run.id)
    del done
    return fc


def template_algorithm() -> Flowchart:
    fc = Flowchart()
    s = fc.add("terminal", "Start")
    i = fc.add("io", "Read $n$", after=s.id)
    init = fc.add("process", "$i \\leftarrow 1$, $s \\leftarrow 0$",
                  after=i.id)
    test = fc.add("decision", "$i \\le n$?", after=init.id)
    body = fc.add("process", "$s \\leftarrow s + i$\\\\$i \\leftarrow i+1$",
                  after=test.id, label="Yes")
    fc.connect(body.id, test.id)
    out = Node(fc.new_id(), "io", "Print $s$", 1.3, test.y)
    fc.nodes.append(out)
    end = Node(fc.new_id(), "terminal", "End", 1.3, test.y + 1.4)
    fc.nodes.append(end)
    fc.connect(test.id, out.id, "No")
    fc.connect(out.id, end.id)
    return fc


def template_pipeline() -> Flowchart:
    fc = Flowchart(direction="LR", row_cm=1.8, col_cm=3.4)
    _chain(fc, [("database", "Raw data"), ("process", "Clean"),
                ("subprocess", "Model"), ("document", "Report")])
    return fc


TEMPLATES = {
    "Simple process": template_simple,
    "Decision with a loop": template_decision,
    "Algorithm (sum to n)": template_algorithm,
    "Data pipeline (left to right)": template_pipeline,
}
