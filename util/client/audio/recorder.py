# coding: utf-8
"""Audio recorder pipeline for mic input.

process-merge: _send_message 改为调用 RecognitionBridge.submit_audio，
去掉 base64 编码和 JSON 序列化，音频数据以原始 bytes 传递。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Optional

import numpy as np

from config_client import ClientConfig as Config
from util.client.audio.file_manager import AudioFileManager
from util.app_state import console
from util.recognition_protocol import AudioTask
from util.tools.asyncio_to_thread import to_thread
from . import logger

if TYPE_CHECKING:
    from util.app_state import AppState

# 目标采样率（识别模型要求）
TARGET_SAMPLE_RATE = 16000


class AudioRecorder:
    """Manage one full hold-to-talk recording session."""

    def __init__(self, state: 'AppState'):
        self.state = state
        self.task_id: Optional[str] = None
        self._file_manager: Optional[AudioFileManager] = None
        self._start_time: float = 0.0
        self._duration: float = 0.0
        self._cache: list[np.ndarray] = []

    @staticmethod
    def _to_mono(data: np.ndarray) -> np.ndarray:
        if data is None or data.size == 0:
            return np.array([], dtype=np.float32)
        if data.ndim == 1:
            return data.astype(np.float32, copy=False)
        if data.shape[1] == 1:
            return data[:, 0].astype(np.float32, copy=False)
        # Use the strongest channel to avoid phase-cancel or weak-channel dilution.
        channel_rms = np.sqrt(np.mean(np.square(data, dtype=np.float32), axis=0))
        best_idx = int(np.argmax(channel_rms))
        return data[:, best_idx].astype(np.float32, copy=False)

    def _get_source_sample_rate(self) -> int:
        """获取当前音频流的实际采样率"""
        manager = getattr(self.state, 'stream_manager', None)
        if manager is not None:
            return getattr(manager, 'current_sample_rate', 48000)
        return 48000

    @staticmethod
    def _resample_to_16k(data: np.ndarray, src_rate: int) -> np.ndarray:
        """将音频转单声道并重采样到 16kHz（纯 numpy 实现，无 scipy 依赖）"""
        mono = AudioRecorder._to_mono(data)
        if mono.size == 0:
            return mono
        if src_rate == TARGET_SAMPLE_RATE:
            return mono
        target_len = int(len(mono) * TARGET_SAMPLE_RATE / src_rate)
        # 使用线性插值重采样，对语音识别足够精确
        src_indices = np.linspace(0, len(mono) - 1, target_len)
        lo = np.floor(src_indices).astype(np.intp)
        hi = np.clip(lo + 1, 0, len(mono) - 1)
        frac = src_indices - lo
        return (mono[lo] * (1 - frac) + mono[hi] * frac).astype(np.float32)

    def _is_low_energy(self, data: np.ndarray) -> bool:
        if not getattr(Config, 'noise_gate_enabled', False):
            return False

        mono = self._to_mono(data)
        if mono.size == 0:
            return True

        rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float32))))
        peak = float(np.max(np.abs(mono)))
        rms_th = float(getattr(Config, 'noise_gate_rms_threshold', 0.01))
        peak_th = float(getattr(Config, 'noise_gate_peak_threshold', 0.035))
        # Treat a chunk as effective only when both RMS and PEAK are sufficient.
        return rms < rms_th or peak < peak_th

    @staticmethod
    def _energy_stats(data: np.ndarray) -> tuple[float, float]:
        if data is None or data.size == 0:
            return 0.0, 0.0
        mono = AudioRecorder._to_mono(data)
        if mono.size == 0:
            return 0.0, 0.0
        rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float32))))
        peak = float(np.max(np.abs(mono)))
        return rms, peak

    def _has_effective_energy(self, data: np.ndarray) -> bool:
        if data is None or data.size == 0:
            return False
        if not getattr(Config, 'noise_gate_enabled', False):
            return True

        mono = self._to_mono(data)
        if mono.size == 0:
            return False

        # 50ms windows avoid long leading silence diluting RMS of the whole chunk.
        win = 2400
        for i in range(0, mono.size, win):
            piece = mono[i:i + win]
            if piece.size == 0:
                continue
            if not self._is_low_energy(piece):
                return True
        return False

    def _send_message(self, task: AudioTask) -> None:
        """
        提交音频任务到识别桥接层（替代 WebSocket 发送）

        process-merge: 不再通过 WebSocket 发送 JSON + base64，
        改为直接调用 RecognitionBridge.submit_audio 传递原始 AudioTask。
        """
        bridge = getattr(self.state, '_bridge', None)

        if bridge is None:
            if task.is_final:
                self.state.pop_audio_file(task.task_id)
                logger.warning('RecognitionBridge not available, cannot send audio')
            return

        try:
            if not self.state.model_loaded:
                if task.is_final:
                    self.state.pop_audio_file(task.task_id)
                    logger.warning('模型未加载完成，无法发送音频')
                return

            bridge.submit_audio(task)

        except Exception as e:
            logger.error(f'failed to submit audio task: {e}', exc_info=True)

    async def record_and_send(self) -> None:
        try:
            self.task_id = str(uuid.uuid1())
            logger.debug(f'create record task id={self.task_id}')

            self._start_time = 0.0
            self._duration = 0.0
            self._cache = []
            has_sent_audio = False

            min_effective_chunks = max(1, int(getattr(Config, 'noise_gate_min_effective_chunks', 1)))
            min_effective_duration = max(0.0, float(getattr(Config, 'noise_gate_min_effective_duration', 0.0)))

            pending_chunks: list[np.ndarray] = []
            pending_chunks_count = 0
            pending_duration = 0.0
            max_seen_rms = 0.0
            max_seen_peak = 0.0

            # 音频分段缓冲：累积重采样后的音频字节，达到 seg_duration 后才发送给识别器
            # 识别器的 encode_audio 会将短音频填充到 30s，小块音频会导致模型在静音中识别
            seg_duration = float(Config.mic_seg_duration)
            seg_overlap = float(Config.mic_seg_overlap)
            seg_threshold = seg_duration + seg_overlap * 2
            audio_buffer = bytearray()
            buffer_offset = 0.0  # 当前缓冲区的起始偏移（秒）

            file_path = None
            if Config.save_audio:
                self._file_manager = AudioFileManager()

            def _send_audio_chunk(data: np.ndarray, time_frame: float) -> None:
                nonlocal has_sent_audio, file_path
                if data is None or data.size == 0:
                    return

                if Config.save_audio and self._file_manager and file_path is None:
                    channels = data.shape[1] if data.ndim > 1 else 1
                    file_path, _ = self._file_manager.create(
                        channels,
                        self._start_time,
                        self._get_source_sample_rate(),
                    )
                    self.state.register_audio_file(self.task_id, file_path)
                    logger.debug(f'create audio file: {file_path}')

                self._duration += len(data) / self._get_source_sample_rate()
                if Config.save_audio and self._file_manager:
                    self._file_manager.write(data)

                has_sent_audio = True

            def _buffer_resampled_and_send(data: np.ndarray, time_frame: float) -> None:
                """将重采样后的音频累积到缓冲区，达到阈值后分段发送给识别器"""
                nonlocal buffer_offset

                resampled = self._resample_to_16k(data, self._get_source_sample_rate())
                if resampled.size == 0:
                    return

                audio_buffer.extend(resampled.tobytes())

                # 计算缓冲区当前时长（float32, 16000Hz, mono = 64000 bytes/s）
                buffer_duration = len(audio_buffer) / 64000.0

                # 达到分段阈值时，切出片段发送
                segment_bytes = int((seg_duration + seg_overlap) * 64000)
                stride_bytes = int(seg_duration * 64000)

                while buffer_duration >= seg_threshold:
                    segment_data = bytes(audio_buffer[:segment_bytes])
                    del audio_buffer[:stride_bytes]
                    segment_overlap = 0.0 if buffer_offset <= 0 else min(
                        seg_overlap,
                        len(segment_data) / 64000.0,
                    )

                    task = AudioTask(
                        task_id=self.task_id,
                        source='mic',
                        data=segment_data,
                        offset=buffer_offset,
                        overlap=segment_overlap,
                        is_final=False,
                        time_start=self._start_time,
                        time_submit=time_frame,
                        context=Config.context,
                    )
                    self._send_message(task)
                    buffer_offset += seg_duration
                    buffer_duration = len(audio_buffer) / 64000.0

            def _flush_pending(time_frame: float) -> None:
                nonlocal pending_chunks_count, pending_duration
                if not pending_chunks:
                    return

                data = pending_chunks[0] if len(pending_chunks) == 1 else np.concatenate(pending_chunks)
                pending_chunks.clear()
                pending_chunks_count = 0
                pending_duration = 0.0
                _send_audio_chunk(data, time_frame)
                _buffer_resampled_and_send(data, time_frame)

            def _buffer_or_send(data: np.ndarray, time_frame: float, stage: str) -> None:
                nonlocal pending_chunks_count, pending_duration
                if data is None or data.size == 0:
                    return

                if has_sent_audio:
                    _send_audio_chunk(data, time_frame)
                    _buffer_resampled_and_send(data, time_frame)
                    return

                pending_chunks.append(data)
                pending_chunks_count += 1
                pending_duration += len(data) / self._get_source_sample_rate()

                if (
                    pending_chunks_count >= min_effective_chunks
                    and pending_duration >= min_effective_duration
                ):
                    logger.debug(
                        f'task_id={self.task_id} effective audio reached in {stage}, '
                        f'count={pending_chunks_count}, duration={pending_duration:.3f}s'
                    )
                    _flush_pending(time_frame)
                else:
                    logger.debug(
                        f'task_id={self.task_id} buffering audio in {stage}, '
                        f'count={pending_chunks_count}/{min_effective_chunks}, '
                        f'duration={pending_duration:.3f}/{min_effective_duration:.3f}s'
                    )

            while task := await to_thread(self.state.control_queue.get):

                if task['type'] == 'begin':
                    self._start_time = task['time']
                    logger.debug(f'record begin at {self._start_time}')

                elif task['type'] == 'data':
                    if task['time'] - self._start_time < Config.threshold:
                        self._cache.append(task['data'])
                        continue

                    if self._cache:
                        data = np.concatenate([*self._cache, task['data']])
                        self._cache.clear()
                    else:
                        data = task['data']

                    rms, peak = self._energy_stats(data)
                    max_seen_rms = max(max_seen_rms, rms)
                    max_seen_peak = max(max_seen_peak, peak)

                    if not self._has_effective_energy(data):
                        logger.debug(f'task_id={self.task_id} skip low-energy chunk in data stage')
                        continue

                    _buffer_or_send(data, task['time'], 'data')

                elif task['type'] == 'finish':
                    if self._cache:
                        data = np.concatenate(self._cache)
                        self._cache.clear()
                        rms, peak = self._energy_stats(data)
                        max_seen_rms = max(max_seen_rms, rms)
                        max_seen_peak = max(max_seen_peak, peak)
                        if self._has_effective_energy(data):
                            _buffer_or_send(data, task['time'], 'finish')
                        else:
                            logger.debug(f'task_id={self.task_id} skip low-energy cache chunk in finish stage')

                    if (
                        not has_sent_audio
                        and pending_chunks_count >= min_effective_chunks
                        and pending_duration >= min_effective_duration
                    ):
                        _flush_pending(task['time'])

                    if has_sent_audio and pending_chunks:
                        _flush_pending(task['time'])

                    if Config.save_audio and self._file_manager and file_path:
                        self._file_manager.finish()
                        logger.debug('finish audio file write')

                    console.print(f'任务标识：{self.task_id}')
                    console.print(f'    录音时长：{self._duration:.2f}s')
                    logger.info(f'record task done, task_id={self.task_id}, duration={self._duration:.2f}s')

                    if not has_sent_audio and len(audio_buffer) == 0:
                        logger.info(f'task_id={self.task_id} no effective audio, skip final send')
                        logger.info(
                            f'task_id={self.task_id} peak/rms observed: '
                            f'peak={max_seen_peak:.6f}, rms={max_seen_rms:.6f}, '
                            f"thresholds peak>={float(getattr(Config, 'noise_gate_peak_threshold', 0.0)):.6f}, "
                            f"rms>={float(getattr(Config, 'noise_gate_rms_threshold', 0.0)):.6f}"
                        )
                        dropped_path = self.state.pop_audio_file(self.task_id)
                        if dropped_path:
                            try:
                                dropped_path.unlink(missing_ok=True)
                            except Exception as e:
                                logger.debug(f'failed to delete dropped audio file: {e}')
                        break

                    # 发送缓冲区中剩余的音频（最后一段，可能不足 seg_duration）
                    if len(audio_buffer) > 0:
                        remaining_data = bytes(audio_buffer)
                        audio_buffer.clear()
                        remaining_overlap = 0.0 if buffer_offset <= 0 else min(
                            seg_overlap,
                            len(remaining_data) / 64000.0,
                        )
                        remaining_task = AudioTask(
                            task_id=self.task_id,
                            source='mic',
                            data=remaining_data,
                            offset=buffer_offset,
                            overlap=remaining_overlap,
                            is_final=False,
                            time_start=self._start_time,
                            time_submit=task['time'],
                            context=Config.context,
                        )
                        self._send_message(remaining_task)
                        logger.debug(
                            f'发送剩余音频: {len(remaining_data)} bytes '
                            f'({len(remaining_data) / 64000.0:.2f}s)'
                        )

                    # process-merge: 使用 AudioTask 替代 dict
                    final_task = AudioTask(
                        task_id=self.task_id,
                        source='mic',
                        data=b'',  # 最终消息无音频数据
                        offset=self._duration,
                        overlap=0.0,
                        is_final=True,
                        time_start=self._start_time,
                        time_submit=task['time'],
                        context=Config.context,
                    )
                    self._send_message(final_task)
                    break

        except Exception as e:
            logger.error(f'record task error: {e}', exc_info=True)

    def get_file_manager(self) -> Optional[AudioFileManager]:
        return self._file_manager
