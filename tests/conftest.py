"""Shared pytest set-up."""
import os
import sys


def pytest_unconfigure(config):
    """Leave with pytest's own status before the interpreter tears Qt down.
    PySide6 objects destroyed after QApplication during interpreter exit
    crash (exit 139) after every test has passed. Windows faults even in
    os._exit, so its CI reads the JUnit report instead."""
    sys.stdout.flush()
    sys.stderr.flush()
    status = getattr(config, "_kslide_status", 0)
    os._exit(status)


def pytest_sessionfinish(session, exitstatus):
    session.config._kslide_status = int(exitstatus)
