# coding: utf-8
"""
进程内识别协议数据类

定义主进程与 Recognizer 子进程之间传递的数据结构。
替代 util/protocol.py 中基于 WebSocket 的 AudioMessage / RecognitionResult。

AudioTask: 主进程 -> Recognizer 子进程的音频任务（原始 bytes，无 base64 编码）
RecognitionOutput: Recognizer 子进程 -> 主进程的识别输出（与 Result 字段对齐，去掉 socket_id）
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class AudioTask:
    """
    音频识别任务（主进程 -> Recognizer 子进程）

    替代 AudioMessage，去掉 base64 编码，data 为原始 float32 bytes。
    与 util/server/server_classes.py 的 Task 字段对齐，去掉 socket_id。

    Attributes:
        task_id: 任务唯一标识
        source: 音频来源 ('mic' 麦克风 或 'file' 文件)
        data: 原始音频数据 (float32, 16kHz, mono)，不再 base64 编码
        offset: 当前片段在整段音频中的时间偏移（秒）
        overlap: 片段重叠时间（秒），用于去重
        is_final: 是否为当前任务的最后一个数据包
        time_start: 录音/音频开始时间戳
        time_submit: 任务提交时间戳
        context: 上下文信息（传递给识别器）
        samplerate: 采样率，默认 16000 Hz
    """
    task_id: str
    source: Literal['mic', 'file']
    data: bytes
    offset: float
    overlap: float
    is_final: bool
    time_start: float
    time_submit: float
    context: str = ''
    samplerate: int = 16000


@dataclass
class RecognitionOutput:
    """
    识别输出（Recognizer 子进程 -> 主进程）

    替代 RecognitionResult，与 util/server/server_classes.py 的 Result 字段对齐，
    去掉 socket_id（进程内通信不需要）。

    Attributes:
        task_id: 任务唯一标识
        source: 音频来源 ('mic' 或 'file')
        is_final: 是否为最终结果（所有片段识别完成）
        duration: 已处理的音频总时长（秒）
        time_start: 录音/音频开始时间戳
        time_submit: 最后一个片段的提交时间戳
        time_complete: 识别完成时间戳

        text: 主要输出 - 简单文本拼接结果（不依赖时间戳）
        text_accu: 精确输出 - 基于时间戳去重的拼接结果（用于字幕生成）
        tokens: 字级 token 列表（与 timestamps 对应）
        timestamps: 字级时间戳列表（秒）
    """
    task_id: str
    source: str
    is_final: bool = False
    duration: float = 0.0
    time_start: float = 0.0
    time_submit: float = 0.0
    time_complete: float = 0.0

    # 主要输出（简单文本拼接）
    text: str = ''

    # 精确输出（时间戳拼接）
    text_accu: str = ''
    tokens: List[str] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
