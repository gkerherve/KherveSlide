"""Shared pytest set-up."""
import os
import sys


def pytest_unconfigure(config):
    """Leave with pytest's own status before the interpreter tears Qt down.
    On macOS, PySide6 objects destroyed after QApplication during
    interpreter exit segfault (exit 139) after every test has passed."""
    if sys.platform == "darwin":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(getattr(config, "_kslide_status", 0))


def pytest_sessionfinish(session, exitstatus):
    session.config._kslide_status = int(exitstatus)
