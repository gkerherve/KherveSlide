"""kherveSlide — a dedicated WYSIWYG slide designer that compiles to
beamer LaTeX. Shares KherveTeX's tectonic / preview / icon engine but is
its own application."""
from __future__ import annotations

from pathlib import Path

# Minor is bumped by hand for behaviour changes; the patch component is
# the repo's total commit count, appended automatically at runtime.
__version__ = "0.1"


def _git_build_info() -> tuple[int, str] | None:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        import pygit2
        if not (repo_root / ".git").exists():
            return None
        repo = pygit2.Repository(str(repo_root))
        if repo.head_is_unborn:
            return None
        head_oid = repo.head.target
        count = sum(1 for _ in repo.walk(head_oid, pygit2.GIT_SORT_NONE))
        return count, str(head_oid)[:7]
    except Exception:
        return None


def version_string() -> str:
    info = _git_build_info()
    if info is None:
        return f"v{__version__}"
    count, sha = info
    return f"v{__version__}.{count}+{sha}"
