# coding: utf-8
"""
快捷键任务模块

管理单个快捷键的录音任务状态
"""

import asyncio
import time
from threading import Event, Timer
from typing import TYPE_CHECKING, Optional

from config_client import ClientConfig as Config
from . import logger
from util.tools.my_status import Status

if TYPE_CHECKING:
    from util.client.shortcut.shortcut_config import Shortcut
    from util.client.state import ClientState
    from util.client.audio.recorder import AudioRecorder



class ShortcutTask:
    """
    单个快捷键的录音任务

    跟踪每个快捷键独立的录音状态，防止互相干扰。
    """

    def __init__(self, shortcut: 'Shortcut', state: 'ClientState', recorder_class=None):
        """
        初始化快捷键任务

        Args:
            shortcut: 快捷键配置
            state: 客户端状态实例
            recorder_class: AudioRecorder 类（可选，用于延迟导入）
        """
        self.shortcut = shortcut
        self.state = state
        self._recorder_class = recorder_class

        # 任务状态
        self.task: Optional[asyncio.Future] = None
        self.recording_start_time: float = 0.0
        self.is_recording: bool = False
        self.is_pending_hold: bool = False
        self.pending_hold_started_at: float = 0.0

        # hold_mode 状态跟踪
        self.pressed: bool = False
        self.released: bool = True
        self.event: Event = Event()
        self._release_timer: Optional[Timer] = None

        # 线程池（用于 countdown）
        self.pool = None

        # 录音状态动画
        self._status = Status('开始录音', spinner='point')

    def _get_recorder(self) -> 'AudioRecorder':
        """获取 AudioRecorder 实例"""
        if self._recorder_class is None:
            from util.client.audio.recorder import AudioRecorder
            self._recorder_class = AudioRecorder
        return self._recorder_class(self.state)

    def _sync_stream_with_system_default(self, stage: str = "after-record") -> None:
        """Ensure stream follows current system default input at a non-critical stage."""
        if not getattr(Config, "keep_mic_stream_open", True):
            return
        if bool(getattr(Config, "mic_force_preferred_input", False)):
            return

        stream_manager = getattr(self.state, "stream_manager", None)
        if stream_manager is None:
            return

        sync_fn = getattr(stream_manager, "ensure_default_input_synced", None)
        if not callable(sync_fn):
            return

        try:
            sync_fn(reason=f"shortcut:{self.shortcut.key}:{stage}")
        except Exception as e:
            logger.debug(f"[{self.shortcut.key}] sync default input skipped: {e}")

    def _ensure_stream_ready(self) -> None:
        """
        Open input stream on demand when not running.
        This avoids holding Bluetooth hands-free profile while idle.
        """
        stream_manager = getattr(self.state, "stream_manager", None)
        if stream_manager is None:
            return

        if getattr(self.state, "stream", None) is not None:
            return

        try:
            logger.info(f"[{self.shortcut.key}] opening microphone stream on demand")
            preferred_name = getattr(Config, "mic_preferred_input_name", None)
            force_preferred = bool(getattr(Config, "mic_force_preferred_input", False))
            prefer_non_bluetooth = bool(
                getattr(Config, "mic_auto_prefer_non_bluetooth_input", False)
            )
            if force_preferred and not str(preferred_name or "").strip():
                logger.error(
                    f"[{self.shortcut.key}] force preferred input enabled but mic_preferred_input_name is empty"
                )
                return
            if preferred_name:
                stream = stream_manager.open(
                    preferred_input_name=preferred_name,
                    fallback_to_default=False,
                    allow_first_available_fallback=False,
                )
                if stream is None:
                    if force_preferred:
                        logger.error(
                            f"[{self.shortcut.key}] preferred input unavailable and force enabled: {preferred_name}"
                        )
                        return
                    logger.warning(
                        f"[{self.shortcut.key}] preferred input unavailable: {preferred_name}, fallback to default"
                    )
                    stream_manager.open(
                        prefer_non_bluetooth=prefer_non_bluetooth,
                        allow_first_available_fallback=False,
                    )
            else:
                stream_manager.open(
                    prefer_non_bluetooth=prefer_non_bluetooth,
                    allow_first_available_fallback=False,
                )
        except Exception as e:
            logger.warning(f"[{self.shortcut.key}] failed to open microphone stream: {e}")

    def _release_stream_when_idle(self, stage: str) -> None:
        """
        Release input stream after record when configured.
        """
        if getattr(Config, "keep_mic_stream_open", True):
            return

        self._cancel_pending_release()

        def _do_release() -> None:
            if getattr(Config, "keep_mic_stream_open", True):
                return
            if self.state.recording:
                return

            stream_manager = getattr(self.state, "stream_manager", None)
            if stream_manager is None:
                return
            if getattr(self.state, "stream", None) is None:
                return

            try:
                stream_manager.close()
                logger.info(f"[{self.shortcut.key}] microphone stream released ({stage})")
            except Exception as e:
                logger.warning(f"[{self.shortcut.key}] failed to release microphone stream: {e}")

        delay = float(getattr(Config, "mic_idle_release_delay", 0.0) or 0.0)
        if delay <= 0:
            _do_release()
            return

        timer = Timer(delay, _do_release)
        timer.daemon = True
        self._release_timer = timer
        timer.start()
        logger.debug(
            f"[{self.shortcut.key}] schedule microphone release in {delay:.2f}s ({stage})"
        )

    def _cancel_pending_release(self) -> None:
        timer = self._release_timer
        if timer and timer.is_alive():
            try:
                timer.cancel()
            except Exception:
                pass
        self._release_timer = None

    def _play_record_start_sound(self) -> None:
        """开始录音提示音已移除。"""
        return

    def mark_pending_hold(self) -> None:
        """标记长按等待态，短按阶段不启动录音链路。"""
        self.pressed = True
        self.released = False
        self.is_pending_hold = True
        self.pending_hold_started_at = time.time()
        logger.debug(f"[{self.shortcut.key}] 进入长按等待态")

    def clear_pending_hold(self) -> None:
        """清理长按等待态。"""
        self.is_pending_hold = False
        self.pending_hold_started_at = 0.0

    def launch(self) -> None:
        """启动录音任务"""
        logger.info(f"[{self.shortcut.key}] 触发：开始录音")

        self.clear_pending_hold()

        # Mark recording first so open-stream latency won't reduce effective hold duration.
        self._cancel_pending_release()
        self.recording_start_time = time.time()
        self.is_recording = True
        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({'type': 'begin', 'time': self.recording_start_time, 'data': None}),
            self.state.loop
        )

        self.state.start_recording(self.recording_start_time)
        self._status.start()

        recorder = self._get_recorder()
        self.task = asyncio.run_coroutine_threadsafe(
            recorder.record_and_send(),
            self.state.loop,
        )

        # Ensure input stream after task is armed.
        self._sync_stream_with_system_default(stage="before-record")
        self._ensure_stream_ready()

    def cancel(self) -> None:
        """取消录音任务（时间过短）"""
        logger.debug(f"[{self.shortcut.key}] 取消录音任务（时间过短）")

        self.clear_pending_hold()
        self.is_recording = False
        self.state.stop_recording()
        self._status.stop()

        if self.task is not None:
            self.task.cancel()
            self.task = None

        # Keep stream/device sync behavior consistent even on short-cancel paths.
        self._sync_stream_with_system_default(stage="after-cancel")
        self._release_stream_when_idle(stage="after-cancel")

    def finish(self) -> None:
        """完成录音任务"""
        logger.info(f"[{self.shortcut.key}] 释放：完成录音")

        self.clear_pending_hold()
        self.is_recording = False
        self.state.stop_recording()
        self._status.stop()

        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({
                'type': 'finish',
                'time': time.time(),
                'data': None
            }),
            self.state.loop
        )

        # Sync input stream after the current record so next trigger follows system default
        # without delaying hotkey-to-record latency.
        self._sync_stream_with_system_default(stage="after-record")
        self._release_stream_when_idle(stage="after-record")

        # 执行 restore（可恢复按键 + 非阻塞模式）
        # 阻塞模式下按键不会发送到系统，状态不会改变，不需要恢复
        if self.shortcut.is_toggle_key() and not self.shortcut.suppress:
            self._restore_key()

    def _restore_key(self) -> None:
        """恢复按键状态（防自捕获逻辑由 ShortcutManager 处理）"""
        # 通知管理器执行 restore
        # 防自捕获：管理器会设置 flag 再发送按键
        manager = self._manager_ref()
        if manager:
            logger.debug(f"[{self.shortcut.key}] 自动恢复按键状态 (suppress={self.shortcut.suppress})")
            manager.schedule_restore(self.shortcut.key)
        else:
            logger.warning(f"[{self.shortcut.key}] manager 引用丢失，无法 restore")

