# coding: utf-8
"""
音频分段器（AudioSegmenter）

从 util/server/server_ws_recv.py 的 AudioCache + message_handler 提取出来的纯逻辑组件。
在主进程 asyncio 事件循环中运行，负责：
- 缓存接收到的音频数据
- 按 seg_duration / seg_overlap 切片
- 将切片后的 AudioTask 通过 RecognitionBridge.submit_audio 提交

与原 server_ws_recv.py 的区别：
- 不再依赖 WebSocket（websocket 参数移除）
- 不再依赖 Cosmic.queue_in（改为调用 RecognitionBridge.submit_audio）
- 不再需要 base64 解码（输入已经是原始 bytes）
- socket_id 固定为 'local'（进程内通信）
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from util.constants import AudioFormat
from util.recognition_protocol import AudioTask

from . import get_logger

logger = get_logger('client')

if TYPE_CHECKING:
    from util.recognition_bridge import RecognitionBridge


class AudioCache:
    """
    音频缓冲区

    用于缓存接收到的音频数据，直到达到分段阈值后提交处理。
    与原 server_ws_recv.py 的 AudioCache 逻辑完全一致。
    """

    def __init__(self):
        self.chunks: bytes = b''       # 音频数据缓冲
        self.offset: float = 0.0       # 当前偏移时间（秒）
        self.byte_count: int = 0       # 累计接收字节数

    @property
    def duration(self) -> float:
        """缓冲区音频时长（秒）"""
        return AudioFormat.bytes_to_seconds(len(self.chunks))

    @property
    def total_duration(self) -> float:
        """累计接收的音频总时长（秒）"""
        return AudioFormat.bytes_to_seconds(self.byte_count)

    def reset(self) -> None:
        """重置缓冲区"""
        self.chunks = b''
        self.offset = 0.0
        self.byte_count = 0


class AudioSegmenter:
    """
    音频分段器

    接收原始音频数据，按配置的分段参数切片后提交到识别桥接层。

    使用方式：
        segmenter = AudioSegmenter(bridge)
        segmenter.process_chunk(audio_bytes, task_id, source, seg_duration, seg_overlap, time_start, context)
        segmenter.finalize(task_id, source, seg_duration, seg_overlap, time_start, context)
    """

    def __init__(self, bridge: 'RecognitionBridge'):
        """
        初始化音频分段器

        Args:
            bridge: 识别桥接层实例
        """
        self._bridge = bridge
        self._cache = AudioCache()

    def process_chunk(
        self,
        data: bytes,
        task_id: str,
        source: str = 'mic',
        seg_duration: float = 15.0,
        seg_overlap: float = 2.0,
        time_start: float = 0.0,
        context: str = '',
    ) -> None:
        """
        处理音频数据块

        将数据追加到缓冲区，当缓冲区达到分段阈值时自动切片并提交。

        Args:
            data: 原始音频数据 (float32, 16kHz, mono)
            task_id: 任务唯一标识
            source: 音频来源 ('mic' 或 'file')
            seg_duration: 分段时长（秒）
            seg_overlap: 重叠时长（秒）
            time_start: 录音/音频开始时间戳
            context: 上下文信息
        """
        cache = self._cache
        seg_threshold = seg_duration + seg_overlap * 2

        try:
            cache.chunks += data
            cache.byte_count += len(data)

            # 若缓冲已达到分段阈值，将片段作为任务提交
            segment_bytes = AudioFormat.seconds_to_bytes(seg_duration + seg_overlap)
            stride_bytes = AudioFormat.seconds_to_bytes(seg_duration)

            while cache.duration >= seg_threshold:
                segment_data = cache.chunks[:segment_bytes]
                cache.chunks = cache.chunks[stride_bytes:]

                task = AudioTask(
                    source=source,
                    data=segment_data,
                    offset=cache.offset,
                    overlap=seg_overlap,
                    task_id=task_id,
                    is_final=False,
                    time_start=time_start,
                    time_submit=time.time(),
                    context=context,
                )
                cache.offset += seg_duration
                self._bridge.submit_audio(task)
                logger.debug(
                    f"提交音频片段: task_id={task_id[:8]}, "
                    f"offset={cache.offset:.2f}s, buffer={len(cache.chunks)} bytes"
                )

        except Exception as e:
            logger.error(f"音频分段处理错误: task_id={task_id[:8]}: {e}", exc_info=True)
            raise

    def finalize(
        self,
        task_id: str,
        source: str = 'mic',
        seg_duration: float = 15.0,
        seg_overlap: float = 2.0,
        time_start: float = 0.0,
        context: str = '',
    ) -> None:
        """
        提交最终片段并重置缓冲区

        在音频流结束时调用，将缓冲区中剩余数据作为最终片段提交。

        Args:
            task_id: 任务唯一标识
            source: 音频来源 ('mic' 或 'file')
            seg_duration: 分段时长（秒）
            seg_overlap: 重叠时长（秒）
            time_start: 录音/音频开始时间戳
            context: 上下文信息
        """
        cache = self._cache

        try:
            # 提交最终片段
            task = AudioTask(
                source=source,
                data=cache.chunks,
                offset=cache.offset,
                overlap=seg_overlap,
                task_id=task_id,
                is_final=True,
                time_start=time_start,
                time_submit=time.time(),
                context=context,
            )
            self._bridge.submit_audio(task)
            logger.debug(
                f"提交最终片段: task_id={task_id[:8]}, "
                f"data_size={len(cache.chunks)} bytes"
            )

            # 重置缓冲区
            cache.reset()

        except Exception as e:
            logger.error(f"提交最终片段错误: task_id={task_id[:8]}: {e}", exc_info=True)
            raise

    def reset(self) -> None:
        """重置分段器状态"""
        self._cache.reset()
