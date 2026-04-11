# coding: utf-8

import os
import sys
from pathlib import Path
from platform import system

from config_client import ClientConfig as Config
from util.client.audio import AudioStreamManager
from util.client.cleanup import request_exit_from_tray
from util.client.shortcut.shortcut_config import Shortcut
from util.client.shortcut.shortcut_manager import ShortcutManager
from util.client.state import get_state
from util.client.ui import RecordingIndicator, TipsDisplay
from util.hotword import get_hotword_manager
from util.llm.llm_handler import init_llm_system
from util.tools.empty_working_set import empty_current_working_set
from util.tools.windows_privilege import is_process_elevated, request_admin_restart

from . import logger


def _setup_tray(state, base_dir):
    """Initialize tray actions for the client."""
    try:
        from util.client.ui import enable_min_to_tray
    except ImportError as e:
        logger.warning(f"tray module import failed, skip tray features: {e}")
        return

    def _toast(message: str, duration: int = 2200, bg: str = "#075077") -> None:
        try:
            from util.client.ui import toast

            toast(message, duration=duration, bg=bg)
        except Exception:
            logger.info(message)

    def restart_audio():
        manager = state.stream_manager
        if not manager:
            _toast("Audio stream is not ready yet.", bg="#8a3a2f")
            return
        manager.reopen(reason="tray:restart-audio")
        logger.info("user requested audio restart from tray")

    def restart_capswriter():
        logger.info("user requested full restart from tray")
        ok = request_admin_restart(base_dir=base_dir, python_executable=sys.executable)
        if not ok:
            _toast("Restart request failed. Please try again as administrator.", duration=3200, bg="#8a3a2f")
            logger.warning("tray restart request failed to launch elevated helper")
            return

        _toast("Restarting CapsWriter client and server as administrator...", duration=2600)
        from util.common.lifecycle import lifecycle
        lifecycle.request_shutdown(reason="Tray Restart")

    def clear_memory():
        from util.llm.llm_handler import clear_llm_history

        clear_llm_history()
        _toast("Memory cleared: all role chat history removed.", duration=3000)

    def add_hotword():
        try:
            from util.client.ui import on_add_hotword

            on_add_hotword()
        except ImportError as e:
            logger.warning(f"failed to import hotword menu handler: {e}")

    def add_rectify():
        try:
            from util.client.ui import on_add_rectify_record

            on_add_rectify_record()
        except ImportError as e:
            logger.warning(f"failed to import rectify menu handler: {e}")

    def add_context():
        try:
            from util.client.ui import on_edit_context

            on_edit_context()
        except ImportError as e:
            logger.warning(f"failed to import context menu handler: {e}")

    def copy_last_result():
        text = state.last_output_text
        if text:
            from util.llm.llm_clipboard import copy_to_clipboard

            copy_to_clipboard(text)

    icon_path = os.path.join(base_dir, "assets", "icon.ico")
    enable_min_to_tray(
        "CapsWriter Client",
        icon_path,
        exit_callback=request_exit_from_tray,
        more_options=[
            ("Copy Last Result", copy_last_result),
            ("Edit Context", add_context),
            ("Add Hotword", add_hotword),
            ("Add Rectify", add_rectify),
            ("Clear Memory", clear_memory),
            ("Restart Audio", restart_audio),
            ("Restart CapsWriter", restart_capswriter),
        ],
    )
    logger.info("tray icon enabled")


def _notify_windows_privilege_status() -> None:
    """Warn when the client is not elevated on Windows."""
    if system() != "Windows":
        return

    if is_process_elevated():
        logger.info("client privilege: elevated (administrator)")
        return

    warning = (
        "当前客户端未以管理员身份运行；如果前台程序本身是管理员权限、任务管理器、"
        "某些游戏或独占输入程序，后台全局快捷键可能无法触发。"
    )
    guidance = "如遇到这类场景，请以管理员身份重新启动客户端。"
    logger.warning(f"{warning}{guidance}")

    try:
        from util.client.state import console

        console.print(f"[bold yellow]权限提醒[/]：{warning}")
        console.print(f"[yellow]{guidance}[/]")
    except Exception as e:
        logger.debug(f"print privilege warning skipped: {e}")

    try:
        from util.client.ui import toast

        toast(
            "当前客户端不是管理员。若在管理员程序或游戏里后台热键失效，请以管理员身份运行客户端。",
            duration=5500,
            bg="#8a3a2f",
        )
    except Exception as e:
        logger.debug(f"toast privilege warning skipped: {e}")


def setup_client_components(base_dir):
    state = get_state()
    state.initialize()

    # 1) Tray
    if Config.enable_tray:
        _setup_tray(state, base_dir)

    # 2) Startup tips
    TipsDisplay.show_mic_tips()
    _notify_windows_privilege_status()

    # 2.1) Recording indicator
    try:
        state.recording_indicator = RecordingIndicator()
        logger.info("recording indicator enabled")
    except Exception as e:
        logger.warning(f"failed to initialize recording indicator: {e}")

    # 3) Hotword
    logger.info("loading hotword data...")
    hotword_files = {
        "hot": Path("hot.txt"),
        "rule": Path("hot-rule.txt"),
        "rectify": Path("hot-rectify.txt"),
        "shortcut": Path("hot-shortcut.txt"),
    }
    hotword_manager = get_hotword_manager(
        hotword_files=hotword_files,
        threshold=Config.hot_thresh,
        similar_threshold=Config.hot_similar,
        rectify_threshold=Config.hot_rectify,
    )
    hotword_manager.load_all()
    hotword_manager.start_file_watcher()

    # 4) LLM
    logger.info("initializing LLM system...")
    init_llm_system()
    logger.info("LLM system initialized")

    # 5) Audio stream
    logger.info("opening audio stream...")
    stream_manager = AudioStreamManager(state)
    state.stream_manager = stream_manager
    if getattr(Config, "keep_mic_stream_open", True):
        stream_manager.open()
    else:
        logger.info("microphone stream lazy mode enabled; idle will not occupy mic")

    # 6) Shortcut manager
    shortcuts = [Shortcut(**sc) for sc in Config.shortcuts]
    logger.info(f"initializing shortcut manager, total={len(shortcuts)}")
    shortcut_manager = ShortcutManager(state, shortcuts)
    state.shortcut_manager = shortcut_manager
    shortcut_manager.start()
    state.shortcut_handler = shortcut_manager

    # 7) UDP control (optional)
    if Config.udp_control:
        from util.client.udp.udp_control import UDPController

        logger.info(f"starting UDP control on port {Config.udp_control_port}")
        udp_controller = UDPController(shortcut_manager)
        state.udp_controller = udp_controller
        udp_controller.start()

    # 8) Working-set cleanup on Windows
    if system() == "Windows":
        empty_current_working_set()

    logger.info("client initialization complete, waiting for speech input...")
    return state
