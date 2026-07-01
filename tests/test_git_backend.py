"""Tests for the git_backend helpers behind the HistoryDialog.

Builds a throwaway git repo in tmp_path, makes a couple of commits,
and asserts that history_detailed + diff_for_commit produce what the
GUI expects. Skipped if pygit2 isn't installed so a stripped-down
checkout still passes CI."""

from pathlib import Path

import pytest

from kherveslide import git_backend


pytestmark = pytest.mark.skipif(
    not git_backend.is_available(),
    reason="pygit2 not installed — skipping git_backend tests",
)


def _make_repo_with_two_commits(tmp_path: Path) -> Path:
    """Return a repo dir with two commits: first creates hello.txt
    with one line, second appends a second line."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "hello.txt").write_text("hello world\n", encoding="utf-8")
    git_backend.commit_all(repo_dir, message="initial commit")
    (repo_dir / "hello.txt").write_text(
        "hello world\nsecond line\n", encoding="utf-8")
    git_backend.commit_all(repo_dir, message="add a second line\n\nbody text")
    return repo_dir


def test_history_detailed_returns_newest_first(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    commits = git_backend.history_detailed(repo)
    assert len(commits) == 2
    # Newest is "add a second line"; initial is older.
    assert commits[0]["subject"] == "add a second line"
    assert commits[0]["body"] == "body text"
    assert commits[1]["subject"] == "initial commit"
    # Required keys for the dialog:
    for c in commits:
        for key in ("oid", "short_oid", "timestamp", "author",
                    "subject", "body", "epoch"):
            assert key in c, f"missing {key!r} in {c!r}"
        assert len(c["short_oid"]) == 8


def test_diff_for_commit_shows_addition_for_second_commit(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    second = git_backend.history_detailed(repo)[0]
    diff = git_backend.diff_for_commit(repo, second["oid"])
    # The added line shows up as a `+` line in the unified diff.
    assert "+second line" in diff
    # The previous line was context, so it appears with a leading space.
    assert " hello world" in diff


def test_diff_for_root_commit_shows_initial_content(tmp_path: Path):
    """The first commit has no parent — we still want a meaningful
    diff that shows the initial file contents as additions, otherwise
    the history dialog would show an empty pane for the root commit."""
    repo = _make_repo_with_two_commits(tmp_path)
    root = git_backend.history_detailed(repo)[-1]
    diff = git_backend.diff_for_commit(repo, root["oid"])
    assert "+hello world" in diff
    # New file marker should be present.
    assert "new file" in diff or "+++ b/hello.txt" in diff


def test_diff_for_unknown_oid_returns_empty_string(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    assert git_backend.diff_for_commit(repo, "0" * 40) == ""


def test_history_detailed_on_empty_repo_returns_empty_list(tmp_path: Path):
    empty = tmp_path / "empty_repo"
    empty.mkdir()
    git_backend.init_repo(empty)
    # Unborn HEAD — no commits yet.
    assert git_backend.history_detailed(empty) == []


# ----- remote management -----

def test_set_remote_creates_and_lists(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    assert git_backend.get_remotes(repo) == []
    assert git_backend.set_remote(repo, "origin", "https://example.org/x.git")
    remotes = git_backend.get_remotes(repo)
    assert remotes == [("origin", "https://example.org/x.git")]


def test_set_remote_updates_url(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    git_backend.set_remote(repo, "origin", "https://old.example.org/x.git")
    assert git_backend.set_remote(repo, "origin", "https://new.example.org/y.git")
    assert git_backend.get_remotes(repo) == [
        ("origin", "https://new.example.org/y.git")]


def test_set_remote_supports_multiple_remotes(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    git_backend.set_remote(repo, "origin", "https://example.org/a.git")
    git_backend.set_remote(repo, "backup", "https://other.org/a.git")
    names = sorted(n for n, _ in git_backend.get_remotes(repo))
    assert names == ["backup", "origin"]


def test_remove_remote(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    git_backend.set_remote(repo, "origin", "https://example.org/a.git")
    assert git_backend.remove_remote(repo, "origin")
    assert git_backend.get_remotes(repo) == []


def test_remove_unknown_remote_returns_false(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    assert git_backend.remove_remote(repo, "ghost") is False


# ----- pull -----

def test_pull_no_remote_configured(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    ok, msg = git_backend.pull(repo)
    assert ok is False
    assert "remote" in msg.lower()


def test_pull_already_up_to_date_via_file_remote(tmp_path: Path):
    """Fastest test for the happy 'already up to date' branch: clone
    a repo via a file:// remote, then pull immediately. The local and
    remote HEAD match, so the function should report up to date."""
    upstream = _make_repo_with_two_commits(tmp_path)
    clone_path = tmp_path / "clone"
    import pygit2
    pygit2.clone_repository(str(upstream), str(clone_path))
    ok, msg = git_backend.pull(clone_path)
    assert ok is True
    assert "up to date" in msg.lower()


def test_pull_fast_forwards_new_commits(tmp_path: Path):
    """Clone the upstream, add a commit upstream, then pull from the
    clone — expect the clone to fast-forward and report N commits."""
    upstream = _make_repo_with_two_commits(tmp_path)
    clone_path = tmp_path / "clone"
    import pygit2
    pygit2.clone_repository(str(upstream), str(clone_path))
    # Commit something new in the upstream so the clone is behind.
    (upstream / "hello.txt").write_text(
        "hello world\nsecond line\nthird line\n", encoding="utf-8")
    git_backend.commit_all(upstream, "third line")
    ok, msg = git_backend.pull(clone_path)
    assert ok is True
    assert "pulled 1 commit" in msg.lower()


def test_current_branch(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    # init_repo writes refs/heads/dev — that's what we should report.
    assert git_backend.current_branch(repo) == "dev"


# ----- push (new tuple form) -----

def test_push_with_no_remote_returns_message(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    ok, msg = git_backend.push(repo, "origin")
    assert ok is False
    assert "no remote" in msg.lower() or "remote" in msg.lower()


def test_push_with_unborn_head_returns_message(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    git_backend.init_repo(empty)
    ok, msg = git_backend.push(empty, "origin")
    assert ok is False
    # Either "no commits yet" or "no remote" — both indicate
    # there's nothing to push to.
    assert any(word in msg.lower()
               for word in ("commit", "remote"))


# ----- restore_to_commit -----

def test_restore_to_commit_brings_old_contents_back(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    commits = git_backend.history_detailed(repo)
    root = commits[-1]  # initial commit — hello.txt has one line
    # Sanity: current file has two lines (added in commit 2).
    current = (repo / "hello.txt").read_text(encoding="utf-8")
    assert "second line" in current
    # Roll back.
    ok, msg = git_backend.restore_to_commit(repo, root["oid"])
    assert ok, msg
    restored = (repo / "hello.txt").read_text(encoding="utf-8")
    assert "second line" not in restored
    assert "hello world" in restored


def test_restore_to_commit_keeps_head_pointing_at_latest(tmp_path: Path):
    """Restore is a working-tree operation; HEAD must not move.
    Otherwise the user would lose access to commits made after the
    restore point."""
    import pygit2
    repo = _make_repo_with_two_commits(tmp_path)
    head_before = pygit2.Repository(str(repo)).head.target
    commits = git_backend.history_detailed(repo)
    git_backend.restore_to_commit(repo, commits[-1]["oid"])
    head_after = pygit2.Repository(str(repo)).head.target
    assert str(head_before) == str(head_after)


def test_restore_unknown_oid_fails_cleanly(tmp_path: Path):
    repo = _make_repo_with_two_commits(tmp_path)
    ok, msg = git_backend.restore_to_commit(repo, "0" * 40)
    assert ok is False
    assert msg
