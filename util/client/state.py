# coding: utf-8
"""Shared client runtime state."""

from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from rich.console import Console
from rich.theme import Theme

from . import logger

if TYPE_CHECKING:
    import sounddevice as sd
    from websockets.legacy.client import WebSocketClientProtocol


_theme = Theme(
    {
        "markdown.code": "cyan",
        "markdown.item.number": "yellow",
    }
)
console = Console(highlight=False, soft_wrap=True, theme=_theme)


@dataclass
class ClientState:
    """Keep the mutable runtime objects used by the client."""

    loop: Optional[asyncio.AbstractEventLoop] = None
    queue_in: Optional[asyncio.Queue] = None
    queue_out: Optional[asyncio.Queue] = None
    websocket: Optional["WebSocketClientProtocol"] = None
    stream: Optional["sd.InputStream"] = None

    shortcut_handler: Any = None
    stream_manager: Any = None
    processor: Any = None
    mouse_handler: Any = None
    udp_controller: Any = None
    recording_indicator: Any = None

    recording: bool = False
    recording_has_audio: bool = False
    recording_start_time: float = 0.0
    audio_files: Dict[str, Path] = field(default_factory=dict)

    last_recognition_text: Optional[str] = None
    last_output_text: Optional[str] = None

    def initialize(self) -> None:
        """Prepare queues and event loop references."""
        self.loop = asyncio.get_event_loop()
        self.queue_in = asyncio.Queue()
        self.queue_out = asyncio.Queue()
        logger.debug("client state initialized")

    def reset(self) -> None:
        """Release external resources held by the state object."""
        logger.debug("resetting client state")

        if self.websocket is not None:
            try:
                if not self.websocket.closed:
                    logger.debug("websocket will be closed by cleanup flow")
            except Exception:
                pass
            self.websocket = None

        if self.stream is not None:
            try:
                self.stream.close()
                logger.debug("audio stream closed")
            except Exception:
                pass
            self.stream = None

        if self.recording_indicator is not None:
            try:
                self.recording_indicator.stop()
            except Exception as e:
                logger.debug(f"failed to stop recording indicator: {e}")
            self.recording_indicator = None

        self.recording = False
        self.recording_has_audio = False
        self.recording_start_time = 0.0
        self.audio_files.clear()

        logger.debug("client state reset complete")

    def start_recording(self, start_time: float) -> None:
        """Mark recording as active."""
        self.recording = True
        self.recording_has_audio = False
        self.recording_start_time = start_time

        logger.debug(f"recording state updated: recording=True, start_time={start_time:.2f}")

    def mark_recording_audio_started(self, start_time: Optional[float] = None) -> None:
        """Expose that microphone frames have started arriving for the active record."""
        if not self.recording or self.recording_has_audio:
            return

        self.recording_has_audio = True
        if start_time is not None:
            self.recording_start_time = start_time

        if self.recording_indicator is not None:
            try:
                self.recording_indicator.show()
            except Exception as e:
                logger.debug(f"failed to show recording indicator: {e}")

        logger.debug("recording audio confirmed by first input frame")

    def stop_recording(self) -> float:
        """Mark recording as stopped and return its duration."""
        duration = 0.0
        if self.recording_start_time > 0:
            duration = time.time() - self.recording_start_time

        self.recording = False
        self.recording_has_audio = False
        self.recording_start_time = 0.0

        if self.recording_indicator is not None:
            try:
                self.recording_indicator.hide()
            except Exception as e:
                logger.debug(f"failed to hide recording indicator: {e}")

        logger.debug(f"recording state updated: recording=False, duration={duration:.2f}s")
        return duration

    @property
    def is_connected(self) -> bool:
        """Return whether the websocket looks active."""
        if self.websocket is None:
            return False
        try:
            return not self.websocket.closed
        except AttributeError:
            return self.websocket is not None

    def register_audio_file(self, task_id: str, file_path: Path) -> None:
        """Track an audio file created for the current task."""
        self.audio_files[task_id] = file_path
        logger.debug(f"registered audio file: task_id={task_id}, path={file_path}")

    def pop_audio_file(self, task_id: str) -> Optional[Path]:
        """Remove and return the stored audio path for a task."""
        file_path = self.audio_files.pop(task_id, None)
        if file_path:
            logger.debug(f"popped audio file: task_id={task_id}, path={file_path}")
        return file_path

    def set_output_text(self, text: str) -> None:
        """Store the latest output text and optionally broadcast it by UDP."""
        from config_client import ClientConfig as Config

        self.last_output_text = text

        if Config.udp_broadcast and Config.udp_broadcast_targets:
            message = text.encode("utf-8")
            for addr, port in Config.udp_broadcast_targets:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(message, (addr, port))
                        logger.debug(f"sent UDP output text to {addr}:{port}, len={len(text)}")
                except Exception as e:
                    logger.warning(f"failed to send UDP output text to {addr}:{port}: {e}")


_global_state: Optional[ClientState] = None


def get_state() -> ClientState:
    """Return the process-wide client state singleton."""
    global _global_state
    if _global_state is None:
        _global_state = ClientState()
        logger.debug("created global ClientState instance")
    return _global_state
