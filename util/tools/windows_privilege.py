# coding: utf-8
"""
Windows privilege helpers.
"""

from __future__ import annotations

import ctypes
from platform import system


def is_process_elevated() -> bool:
    """
    Return whether the current process is running elevated on Windows.

    Non-Windows platforms always return False.
    """
    if system() != "Windows":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
