# coding: utf-8
"""Audio recorder pipeline for mic input."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import TYPE_CHECKING, Optional

import numpy as np
import websockets

from config_client import ClientConfig as Config
from util.client.audio.file_manager import AudioFileManager
from util.client.state import console
from . import logger

if TYPE_CHECKING:
    from util.client.state import ClientState


class AudioRecorder:
    """Manage one full hold-to-talk recording session."""

    def __init__(self, state: 'ClientState'):
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

    async def _send_message(self, message: dict) -> None:
        websocket = self.state.websocket

        if websocket is None:
            if message['is_final']:
                self.state.pop_audio_file(message['task_id'])
                console.print('    server not connected, cannot send\n')
                logger.warning('server not connected, cannot send audio')
            return

        try:
            if hasattr(websocket, 'closed') and websocket.closed:
                if message['is_final']:
                    self.state.pop_audio_file(message['task_id'])
                    console.print('    server connection closed\n')
                    logger.error('server connection closed')
                return

            await websocket.send(json.dumps(message))

        except websockets.ConnectionClosedError:
            if message['is_final']:
                self.state.pop_audio_file(message['task_id'])
                console.print('[red]connection lost')
                logger.error('websocket connection lost')
        except websockets.ConnectionClosedOK:
            if message['is_final']:
                self.state.pop_audio_file(message['task_id'])
                console.print('[yellow]connection closed')
                logger.info('websocket connection closed')
        except Exception as e:
            logger.error(f'failed to send audio message: {e}', exc_info=True)

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

            file_path = None
            if Config.save_audio:
                self._file_manager = AudioFileManager()

            def _send_audio_chunk(data: np.ndarray, time_frame: float) -> None:
                nonlocal has_sent_audio, file_path
                if data is None or data.size == 0:
                    return

                if Config.save_audio and self._file_manager and file_path is None:
                    channels = data.shape[1] if data.ndim > 1 else 1
                    file_path, _ = self._file_manager.create(channels, self._start_time)
                    self.state.register_audio_file(self.task_id, file_path)
                    logger.debug(f'create audio file: {file_path}')

                self._duration += len(data) / 48000
                if Config.save_audio and self._file_manager:
                    self._file_manager.write(data)

                message = {
                    'task_id': self.task_id,
                    'seg_duration': Config.mic_seg_duration,
                    'seg_overlap': Config.mic_seg_overlap,
                    'is_final': False,
                    'time_start': self._start_time,
                    'time_frame': time_frame,
                    'source': 'mic',
                    'data': base64.b64encode(self._to_mono(data[::3]).tobytes()).decode('utf-8'),
                    'context': Config.context,
                }
                asyncio.create_task(self._send_message(message))
                has_sent_audio = True

            def _flush_pending(time_frame: float) -> None:
                nonlocal pending_chunks_count, pending_duration
                if not pending_chunks:
                    return

                data = pending_chunks[0] if len(pending_chunks) == 1 else np.concatenate(pending_chunks)
                pending_chunks.clear()
                pending_chunks_count = 0
                pending_duration = 0.0
                _send_audio_chunk(data, time_frame)

            def _buffer_or_send(data: np.ndarray, time_frame: float, stage: str) -> None:
                nonlocal pending_chunks_count, pending_duration
                if data is None or data.size == 0:
                    return

                if has_sent_audio:
                    _send_audio_chunk(data, time_frame)
                    return

                pending_chunks.append(data)
                pending_chunks_count += 1
                pending_duration += len(data) / 48000

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

            while task := await self.state.queue_in.get():
                self.state.queue_in.task_done()

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

                    if not has_sent_audio:
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

                    message = {
                        'task_id': self.task_id,
                        'seg_duration': 15,
                        'seg_overlap': 2,
                        'is_final': True,
                        'time_start': self._start_time,
                        'time_frame': task['time'],
                        'source': 'mic',
                        'data': '',
                        'context': Config.context,
                    }
                    asyncio.create_task(self._send_message(message))
                    break

        except Exception as e:
            logger.error(f'record task error: {e}', exc_info=True)

    def get_file_manager(self) -> Optional[AudioFileManager]:
        return self._file_manager
