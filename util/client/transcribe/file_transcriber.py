# coding: utf-8
"""
文件转录模块

提供 FileTranscriber 类用于将音视频文件转录为字幕。

process-merge: 不再通过 WebSocket 发送/接收数据，
改为使用 RecognitionBridge.submit_audio 和 on_result 回调。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from config_client import ClientConfig as Config
from util.app_state import console
from util.recognition_protocol import AudioTask, RecognitionOutput
from .media_tool import MediaTool
from .result_handler import ResultHandler
from . import logger

if TYPE_CHECKING:
    from util.app_state import AppState


class FileTranscriber:
    """
    文件转录器（process-merge 改造）

    协调转录流程：
    1. 检查环境与文件
    2. 调用 MediaTool 提取音频
    3. 通过 RecognitionBridge.submit_audio 发送数据
    4. 通过 on_result 回调接收结果，调用 ResultHandler 处理
    """

    def __init__(self, state: 'AppState', file: Path):
        self.state = state
        self.file = file
        self.task_id: Optional[str] = None
        self._audio_duration: float = 0.0
        self._final_output: Optional[RecognitionOutput] = None
        self._result_event: Optional[asyncio.Event] = None

    async def check(self) -> bool:
        """检查转录条件"""
        # 1. 检查媒体工具环境 (FFmpeg)
        if not MediaTool.check_environment():
            return False

        # 2. 检查 RecognitionBridge 是否可用
        bridge = getattr(self.state, '_bridge', None)
        if bridge is None:
            console.print('识别桥接层不可用')
            logger.error("RecognitionBridge 不可用")
            return False

        # 3. 检查文件是否存在
        if not self.file.exists():
            console.print(f'文件不存在：{self.file}')
            logger.error(f"文件不存在: {self.file}")
            return False

        return True

    async def send(self) -> None:
        """
        发送音频数据到 Recognizer 子进程（process-merge 改造）

        不再通过 WebSocket 发送 base64 编码的 JSON，
        改为通过 RecognitionBridge.submit_audio 传递原始 AudioTask。
        """
        bridge = getattr(self.state, '_bridge', None)
        if bridge is None:
            logger.error("RecognitionBridge 不可用，无法发送音频")
            return

        self.task_id = str(uuid.uuid1())
        console.print(f'\n任务标识：{self.task_id}')
        console.print(f'    处理文件：{self.file}')

        # 1. 预先获取时长
        self._audio_duration = await MediaTool.get_audio_duration(self.file)
        if self._audio_duration > 0:
            console.print(f'    音频长度：{self._audio_duration:.2f}s')

        logger.info(f"开始转录文件: {self.file}, 任务ID: {self.task_id}")

        # 2. 启动 FFmpeg 进程
        ffmpeg_cmd = MediaTool.build_ffmpeg_cmd(self.file)

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )

            # 分块大小：1分钟音频 (16000 * 4 * 60 bytes)
            chunk_size = 16000 * 4 * 60
            bytes_sent = 0
            offset = 0.0

            while True:
                data = await process.stdout.read(chunk_size)
                if not data:
                    break

                bytes_sent += len(data)
                progress = bytes_sent / 4 / 16000
                if self._audio_duration > 0:
                    prog_str = f'    发送进度：{progress:.2f}s / {self._audio_duration:.2f}s'
                else:
                    prog_str = f'    发送进度：{progress:.2f}s'
                console.print(prog_str, end='\r')

                # process-merge: 使用 AudioTask 替代 dict + base64
                task = AudioTask(
                    task_id=self.task_id,
                    source='file',
                    data=data,  # 原始 bytes，不再 base64 编码
                    offset=offset,
                    overlap=Config.file_seg_overlap,
                    is_final=False,
                    time_start=time.time(),
                    time_submit=time.time(),
                    context=Config.context,
                )
                bridge.submit_audio(task)
                offset += len(data) / 4 / 16000

            # 发送结束标志
            final_task = AudioTask(
                task_id=self.task_id,
                source='file',
                data=b'',  # 最终消息无音频数据
                offset=offset,
                overlap=Config.file_seg_overlap,
                is_final=True,
                time_start=time.time(),
                time_submit=time.time(),
                context=Config.context,
            )
            bridge.submit_audio(final_task)
            await process.wait()

            if self._audio_duration == 0:
                self._audio_duration = progress
                console.print(f'    音频长度：{self._audio_duration:.2f}s')

            logger.debug("音频数据发送完成")

        except Exception as e:
            console.print(f'\n[red]转录过程中发生错误: {e}')
            logger.error(f"转录发送异常: {e}", exc_info=True)
            if 'process' in locals() and process.returncode is None:
                process.terminate()
            return

    async def receive(self) -> None:
        """
        接收转录结果（process-merge 改造）

        不再通过 WebSocket 迭代接收 JSON 消息，
        改为通过 RecognitionBridge.on_result 回调接收 RecognitionOutput。
        使用 asyncio.Event 等待最终结果。
        """
        bridge = getattr(self.state, '_bridge', None)
        if bridge is None:
            logger.error("RecognitionBridge 不可用，无法接收结果")
            return

        self._final_output = None
        self._result_event = asyncio.Event()

        def _on_result(output: RecognitionOutput) -> None:
            """接收识别结果回调"""
            if output.task_id != self.task_id:
                return
            console.print(f'    转录进度: {output.duration:.2f}s', end='\r')
            if output.is_final:
                self._final_output = output
                # 线程安全地设置事件
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(self._result_event.set)
                else:
                    self._result_event.set()

        # 注册回调
        bridge.on_result(_on_result)

        try:
            # 等待最终结果
            await asyncio.wait_for(self._result_event.wait(), timeout=Config.file_transcribe_timeout)
        except asyncio.TimeoutError:
            console.print('\n[bold red]错误：转录超时，未收到识别结果。[/bold red]')
            logger.error(f"转录超时: {self.file}")
            return
        except Exception as e:
            logger.error(f"接收结果错误: {e}")
            return

        if self._final_output is None:
            logger.error("未收到最终识别结果")
            return

        # 调用结果处理器进行保存和格式化
        text_display = ResultHandler.save_results(self.file, self._final_output)

        process_duration = self._final_output.time_complete - self._final_output.time_start
        console.print(f'\033[K    处理耗时：{process_duration:.2f}s')
        console.print(f'    识别结果：\n[green]{text_display}')

        logger.info(
            f"转录完成: {self.file}, 处理耗时: {process_duration:.2f}s, "
            f"文本长度: {len(text_display)}"
        )
