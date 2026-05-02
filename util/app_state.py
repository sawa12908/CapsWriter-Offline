# coding: utf-8
"""
应用全局状态模块（合并 ClientState + Cosmic）

提供进程内单例 AppState，管理：
- 录音状态（recording, recording_has_audio, recording_start_time）
- 识别状态（model_loaded, model_loading_progress）
- 消息队列（queue_in / queue_out：multiprocessing.Queue，与 Recognizer 子进程通信）
- 历史记录（history：用于 LLM 上下文）
- 客户端组件引用（stream, shortcut_handler, stream_manager, processor 等）

替代：
- util/client/state.py 的 ClientState（WebSocket 相关字段移除）
- util/server/server_cosmic.py 的 Cosmic（queue_in / queue_out 迁移至此）
"""

from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass, field
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from rich.console import Console
from rich.theme import Theme

from . import get_logger

logger = get_logger('client')

if TYPE_CHECKING:
    import sounddevice as sd
    from multiprocessing import Process


_theme = Theme(
    {
        "markdown.code": "cyan",
        "markdown.item.number": "yellow",
    }
)
console = Console(highlight=False, soft_wrap=True, theme=_theme)


@dataclass
class HistoryEntry:
    """
    LLM 对话历史条目

    存储单次语音输入及其处理结果，用于 LLM 上下文组装。
    """
    text: str                           # 用户输入的原始文本（识别结果）
    llm_result: Optional[str] = None    # LLM 处理后的结果
    role_name: Optional[str] = None     # 触发的角色名称
    timestamp: float = field(default_factory=time.time)  # 记录时间戳


@dataclass
class AppState:
    """
    应用全局状态单例

    合并原 ClientState 和 Cosmic 的职责：
    - 录音状态管理
    - 识别子进程通信队列
    - 客户端组件引用
    - LLM 对话历史
    - 模型加载状态
    """

    # ========== 事件循环 ==========
    loop: Optional[asyncio.AbstractEventLoop] = None

    # ========== 与 Recognizer 子进程通信的队列（multiprocessing.Queue） ==========
    # queue_in: 主进程 -> Recognizer 子进程（发送 AudioTask）
    # queue_out: Recognizer 子进程 -> 主进程（接收 RecognitionOutput）
    queue_in: Queue = field(default_factory=Queue)
    queue_out: Queue = field(default_factory=Queue)

    # control_queue: 录音控制消息队列（begin/data/finish），与 queue_in 分离
    # 避免 AudioRecorder 消费掉发给 Recognizer 的 Task 对象
    control_queue: Queue = field(default_factory=Queue)

    # ========== Recognizer 子进程 ==========
    recognize_process: Optional[Process] = None
    model_loaded: bool = False          # 模型是否已加载完成

    # ========== 音频流 ==========
    stream: Optional["sd.InputStream"] = None

    # ========== 客户端组件引用 ==========
    shortcut_handler: Any = None
    stream_manager: Any = None
    processor: Any = None
    mouse_handler: Any = None
    udp_controller: Any = None
    recording_indicator: Any = None

    # ========== 录音状态 ==========
    recording: bool = False
    recording_has_audio: bool = False
    recording_start_time: float = 0.0
    audio_files: Dict[str, Path] = field(default_factory=dict)

    # ========== 识别结果缓存 ==========
    last_recognition_text: Optional[str] = None
    last_output_text: Optional[str] = None

    # ========== LLM 对话历史 ==========
    history: List[HistoryEntry] = field(default_factory=list)

    def initialize(self) -> None:
        """初始化事件循环引用"""
        self.loop = asyncio.get_event_loop()
        logger.debug("AppState initialized")

    def reset(self) -> None:
        """释放外部资源"""
        logger.debug("resetting AppState")

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

        logger.debug("AppState reset complete")

    # ========== 录音状态方法（从 ClientState 迁移） ==========

    def start_recording(self, start_time: float) -> None:
        """标记录音开始"""
        self.recording = True
        self.recording_has_audio = False
        self.recording_start_time = start_time

        if self.recording_indicator is not None:
            try:
                self.recording_indicator.show_recording()
            except Exception as e:
                logger.debug(f"failed to show recording indicator on start: {e}")

        logger.debug(f"recording state updated: recording=True, start_time={start_time:.2f}")

    def mark_recording_audio_started(self, start_time: Optional[float] = None) -> None:
        """标记麦克风帧已开始到达"""
        if not self.recording or self.recording_has_audio:
            return

        self.recording_has_audio = True
        if start_time is not None:
            self.recording_start_time = start_time

        if self.recording_indicator is not None:
            try:
                self.recording_indicator.show_recording()
            except Exception as e:
                logger.debug(f"failed to show recording indicator: {e}")

        logger.debug("recording audio confirmed by first input frame")

    def stop_recording(self) -> float:
        """标记录音结束，返回录音时长"""
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

    # ========== 音频文件管理（从 ClientState 迁移） ==========

    def register_audio_file(self, task_id: str, file_path: Path) -> None:
        """记录当前任务的音频文件"""
        self.audio_files[task_id] = file_path
        logger.debug(f"registered audio file: task_id={task_id}, path={file_path}")

    def pop_audio_file(self, task_id: str) -> Optional[Path]:
        """取出并移除任务的音频文件路径"""
        file_path = self.audio_files.pop(task_id, None)
        if file_path:
            logger.debug(f"popped audio file: task_id={task_id}, path={file_path}")
        return file_path

    # ========== 输出文本管理（从 ClientState 迁移） ==========

    def set_output_text(self, text: str) -> None:
        """存储最新输出文本，可选 UDP 广播"""
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

    # ========== 对话历史管理 ==========

    def add_history(self, text: str, llm_result: Optional[str] = None,
                    role_name: Optional[str] = None) -> None:
        """添加一条对话历史"""
        entry = HistoryEntry(text=text, llm_result=llm_result, role_name=role_name)
        self.history.append(entry)
        # 限制历史条数，防止内存无限增长
        max_history = 50
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]
        logger.debug(f"added history entry, total={len(self.history)}")

    def clear_history(self) -> None:
        """清空对话历史"""
        self.history.clear()
        logger.debug("history cleared")


# ========== 全局单例 ==========

_global_state: Optional[AppState] = None


def get_state() -> AppState:
    """返回进程内全局 AppState 单例"""
    global _global_state
    if _global_state is None:
        _global_state = AppState()
        logger.debug("created global AppState instance")
    return _global_state
