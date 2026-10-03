"""Shared pytest set-up."""
import os
import sys


def pytest_unconfigure(config):
    """Leave with pytest's own status before the interpreter tears Qt down.
    PySide6 objects destroyed after QApplication during interpreter exit
    crash (macOS: exit 139; Windows: exit 1) after every test has passed."""
    sys.stdout.flush()
    sys.stderr.flush()
    status = getattr(config, "_kslide_status", 0)
    if sys.platform == "win32":
        # os._exit still runs DLL detach on Windows, where Qt's threads
        # fault; TerminateProcess skips it.
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.TerminateProcess(k32.GetCurrentProcess(), status)
    os._exit(status)


def pytest_sessionfinish(session, exitstatus):
    session.config._kslide_status = int(exitstatus)
