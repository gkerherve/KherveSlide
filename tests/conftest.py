"""Shared pytest set-up."""
import os
import sys


def pytest_unconfigure(config):
    """Leave with pytest's own status before the interpreter tears Qt down.
    PySide6 objects destroyed after QApplication during interpreter exit
    crash (macOS: exit 139; Windows: exit 1) after every test has passed."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(getattr(config, "_kslide_status", 0))


def pytest_sessionfinish(session, exitstatus):
    session.config._kslide_status = int(exitstatus)
