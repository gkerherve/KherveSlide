# CLAUDE.md — working conventions for KherveSlide

Project: KherveSlide — a dedicated WYSIWYG slide designer. You drag,
resize and stack text/picture boxes freely on a slide; it produces
beamer LaTeX and compiles to PDF with tectonic. Sister project to
KherveTeX (kherveDOC); shares its look and engine but is its own app.

Stack: Python 3.12+, PySide6, tectonic (LaTeX engine).
Remote: https://github.com/gkerherve/KherveSlide

## Branching: `dev` is the working branch

All work goes on `dev`. `main` is the stable mainline that lags behind
`dev` until the user explicitly asks for a merge. Never work in a git
worktree or a throwaway branch — the user watches commits land on `dev`
in PyCharm's Git Log.

Workflow every change:
1. Confirm on `dev` (`git rev-parse --abbrev-ref HEAD` → `dev`).
2. Make the edits.
3. Run `py -m pytest tests/ -q` and verify all tests pass.
4. `git add` the specific files changed (avoid bare `git add -A`).
5. `git commit` with a HEREDOC message explaining the **why**.
6. `git push` — never skip. Report failures, don't retry destructively.

## Every message: bump the version, commit and push

After **every** message that touches the repo, bump `__version__` and
end with a commit + push to `origin/dev`. Never leave changes
uncommitted. The version tracks the number of messages.

`kherveslide/__init__.py` defines `__version__` as `"<major>.<minor>"`
only (e.g. `"0.1"`). The window title renders it as
`KherveSlide v<major>.<minor>.<commit_count>+<sha7>` — the patch count
and build tag are appended automatically from pygit2 at startup. **Never
put a third number in `__version__`.** Bump the **minor** every message;
bump the **major** only at the user's explicit request, in the same
commit as the change that justifies it.

Prefix the commit subject with `v0.XX:` when it includes a version bump.

## Architectural invariants

- The **deck model** (`kherveslide/model.py`) is the single source of
  truth — JSON-serialisable, no Qt/LaTeX deps. The canvas, serializer
  and navigator all read/write through it. Geometry is normalized
  `0..1` fractions of the slide; z-order is list order.
- Never build beamer LaTeX outside `serializer.py`.
- Object positioning uses `textpos` (`absolute,overlay`) bound to
  `\paperwidth`/`\paperheight` so the canvas matches the PDF.
- Toolbar icons are drawn at runtime in `icons.py` with QPainter — do
  not ship PNG/SVG files. `icons.py`, `themes.py`, `compiler.py`,
  `style_manager.py`, `preview.py`, `latex_view.py` — and the builders
  `equation_editor.py`, `math_widget.py`, `mathbox.py`, `mathlayout.py`,
  `chemistry.py`, `chemfig.py`, `drawing_dialog.py`, `paint/`,
  `khervepaint_link.py`, the `mcp_*` modules — are vendored from
  KherveTeX to keep the same look and engine; keep them in sync by hand
  when intentionally diverging.
- The light Fusion palette is intentional (the Windows dark theme made
  the icons invisible in KherveTeX).
- Tests in `tests/` cover model + serializer + templates. Any change to
  those modules must come with matching tests in the same commit.
- **Every user action must be undoable.** Undo/redo is a debounced
  snapshot history of the whole presentation (`SlideWindow._capture_state`
  pushes `deck_to_json(self.deck)`), driven from `_refresh_latex`. So any
  new action that mutates the presentation **must** funnel through the
  normal change path (`_touch_current` / `_reload_all` / `_refresh_latex`)
  so it is captured automatically — never mutate `self.deck` and repaint
  without going through one of those. Do not add a parallel "skip undo"
  path. The user-facing terminology is **"presentation"**, never "deck"
  (deck remains the internal class name only).

## Layout

Window mirrors KherveTeX: left = the WYSIWYG (slide navigator you can
drag to reorder + the live canvas); right = tabs for the generated
LaTeX source and the compiler Console (+ a PDF preview). The LaTeX view
stays live as you edit on the left.

Start-up mirrors KherveTeX too: a runtime-painted splash
(`splash.py`), then the Welcome page — shown inside the window, not as a
dialog (`start_page.py`): a big blank slide in the slide area with new /
open / import, template and example cards, while the slides frame lists
recent files. It also asks how to work (`welcome.py`), worded exactly as
KherveTeX: Visual + PDF side by side, Visual + PDF in its own window
(close it to dock back), or Visual only (PDF/console hidden, no
background compiles). Switch any time from View (Ctrl+4 / 5 / 6). The
user-facing name of the slide editor is "Visual", never "WYSIWYG". Help holds the Welcome page and the GitHub auto-updater
(`updater.py`, ported from KhervePlot: fast-forwards a clean checkout).
The Slideshow menu (`slideshow.py`) presents the compiled PDF — never
the Visual canvas — full screen, in a presenter view (slides on the
other screen; current + next slide, timer and clock here) or as current
+ next slide on two screens. Templates ▸ Example presentations
(`examples.py`) are complete decks built in code.

The canvas is drawn to look like the PDF: text uses beamer's Latin
Modern faces from tectonic's cache (`latex_fonts.py`), and the theme's
own furniture (title bar, head/foot lines, numbers, background, master)
is a compiled backdrop — `serializer.serialize_backdrop` is the deck
with the objects removed, page *i* under slide *i*, followed by
"bullet probe" pages (a real itemize per size and level) from which
`bullets.py` cuts the theme's actual bullets for the canvas. Canvas text
follows TeX's spacing (first baseline = tallest glyph, fixed
baselineskip, beamer's topsep/itemsep), and px-per-pt uses beamer's real
paper height per aspect ratio (16:9 is 9 cm, not 9.6).

Editing is in-place, PowerPoint-style — there is **no properties side
panel**. Double-click a text box to type into it (a floating editor
commits on focus-out / Escape); double-click a picture to swap the
image. Frequent text formatting (font size, bold/italic, alignment,
colours) is on a compact Format toolbar that tracks the selection;
deck/slide settings (title, author, theme, aspect, frame title,
background) live in the menus.

## Building a release (Windows + macOS)

Packaging mirrors KherveNoise. Both specs share `packaging/spec_common.py`
(data files, hidden imports, excludes) so the platforms cannot drift.

- Version: `<__version__>.<commit count>`, e.g. `0.159.161`, stamped into
  `kherveslide/VERSION` at build time (a frozen app has no `.git`;
  `version_string()` falls back to that file). Same number as the title bar.
- tectonic is bundled: `packaging/fetch_tectonic.py` downloads the official
  self-contained release binary into `build/tectonic/`. Never bundle a
  Homebrew tectonic — it links `/opt/homebrew` dylibs users don't have.
- macOS (on a Mac): `.venv/bin/pip install pyinstaller` then
  `.venv/bin/python packaging/build_macos.py` → `dist/KherveSlide-<ver>-macOS-<arch>.dmg`
  (+ stable `KherveSlide-macOS-<arch>.dmg`). Ad hoc signed, not notarised.
- Windows (on Windows): `python packaging/build_installer.py` → Inno installer
  `KherveSlide-Setup-<ver>.exe`, portable zip, stable `KherveSlide-Setup.exe`.
- CI builds everything from one tagged commit on `dev`:
  `git tag v<ver>` → `windows-build.yml`; `git tag macos-v<ver>` →
  `macos-build.yml` (arm64 + x86_64). Both only upload workflow artifacts;
  the GitHub release is created by hand.
- `packaging/smoke_test.py <exe>` checks VERSION, tectonic, data files and
  that the frozen app stays up.
