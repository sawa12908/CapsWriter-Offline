# coding: utf-8
"""
客户端组件初始化模块

负责初始化热词、LLM、音频流、快捷键等业务组件。
注意：托盘初始化已移至 core_client.py（主窗口模式下由 TrayManager 管理）。
"""

import os
import sys
from pathlib import Path
from platform import system

from config_client import ClientConfig as Config
from util.client.audio import AudioStreamManager
from util.client.shortcut.shortcut_config import Shortcut
from util.client.shortcut.shortcut_manager import ShortcutManager
from util.app_state import get_state
from util.client.ui import RecordingIndicator, TipsDisplay
from util.hotword import get_hotword_manager
from util.llm.llm_handler import init_llm_system
from util.tools.empty_working_set import empty_current_working_set
from util.tools.windows_privilege import is_process_elevated

from . import logger


def _notify_windows_privilege_status() -> None:
    """Log privilege status (auto-elevation handled by init_mic)."""
    if system() != "Windows":
        return

    if is_process_elevated():
        logger.info("client privilege: elevated (administrator)")
    else:
        logger.warning("client running without administrator privileges")


def setup_client_components(base_dir):
    """
    初始化客户端业务组件（在 asyncio 线程中调用）

    注意：state.initialize() 和托盘初始化已由 core_client.py 处理。
    本函数只负责热词、LLM、音频流、快捷键等业务组件的初始化。
    """
    state = get_state()

    # 1) Startup tips
    TipsDisplay.show_mic_tips()
    _notify_windows_privilege_status()

    # 2) Recording indicator
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
