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
  `style_manager.py`, `preview.py`, `latex_view.py` are vendored from
  KherveTeX to keep the same look and engine; keep them in sync by hand
  when intentionally diverging.
- The light Fusion palette is intentional (the Windows dark theme made
  the icons invisible in KherveTeX).
- Tests in `tests/` cover model + serializer + templates. Any change to
  those modules must come with matching tests in the same commit.

## Layout

Window mirrors KherveTeX: left = the WYSIWYG (slide navigator you can
drag to reorder + the live canvas); right = tabs for the generated
LaTeX source and the compiler Console (+ a PDF preview). The LaTeX view
stays live as you edit on the left.

Editing is in-place, PowerPoint-style — there is **no properties side
panel**. Double-click a text box to type into it (a floating editor
commits on focus-out / Escape); double-click a picture to swap the
image. Frequent text formatting (font size, bold/italic, alignment,
colours) is on a compact Format toolbar that tracks the selection;
deck/slide settings (title, author, theme, aspect, frame title,
background) live in the menus.
