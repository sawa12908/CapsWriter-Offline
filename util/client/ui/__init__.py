# coding: utf-8
"""Lazy exports for client UI helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .. import logger


_LOCAL_EXPORTS = {
    "TipsDisplay": ("util.client.ui.tips", "TipsDisplay"),
    "RecordingIndicator": ("util.client.ui.recording_indicator", "RecordingIndicator"),
}

_SHARED_EXPORTS = {
    "toast",
    "toast_stream",
    "ToastMessage",
    "ToastMessageManager",
    "enable_min_to_tray",
    "stop_tray",
}

_MENU_EXPORTS = {
    "on_add_rectify_record": ("util.ui.rectify_menu_handler", "on_add_rectify_record"),
    "on_add_hotword": ("util.ui.hotword_menu_handler", "on_add_hotword"),
    "on_edit_context": ("util.ui.context_menu_handler", "on_edit_context"),
}


def _get_shared_ui():
    module = import_module("util.ui")
    module.set_ui_logger(logger)
    return module


def __getattr__(name: str) -> Any:
    if name in _LOCAL_EXPORTS:
        module_name, attr_name = _LOCAL_EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value

    if name in _SHARED_EXPORTS:
        value = getattr(_get_shared_ui(), name)
        globals()[name] = value
        return value

    if name in _MENU_EXPORTS:
        module_name, attr_name = _MENU_EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "logger",
    "TipsDisplay",
    "RecordingIndicator",
    "toast",
    "toast_stream",
    "ToastMessage",
    "ToastMessageManager",
    "enable_min_to_tray",
    "stop_tray",
    "on_add_rectify_record",
    "on_add_hotword",
    "on_edit_context",
]
