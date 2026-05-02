# coding: utf-8
"""
识别桥接层（RecognitionBridge）

替代 WebSocket 的进程内识别通信层。封装 multiprocessing.Queue 的读写，
提供 submit_audio / on_result / start / stop 接口。

职责：
- submit_audio: 将 AudioTask 放入 queue_in（非阻塞，带超时保护）
- on_result: 注册回调，从 queue_out 消费 RecognitionOutput 并回调
- start: 启动 Recognizer 子进程，等待模型加载
- stop: 停止 Recognizer 子进程，清理队列

线程模型：
- submit_audio 可在任意线程调用（multiprocessing.Queue 线程安全）
- on_result 回调在 asyncio 事件循环线程中调用
- queue_out.get 是阻塞调用，通过 asyncio.to_thread 包装
"""

from __future__ import annotations

import asyncio
import errno
import os
import queue
import sys
import time
from multiprocessing import Process, Manager
from typing import Callable, Optional, TYPE_CHECKING

from util.recognition_protocol import AudioTask, RecognitionOutput
from util.server.server_classes import Task, Result
from util.server.server_check_model import check_model
from util.server.server_init_recognizer import init_recognizer
from util.common.lifecycle import lifecycle
from util.tools.asyncio_to_thread import to_thread

from . import get_logger

logger = get_logger('client')

if TYPE_CHECKING:
    from util.app_state import AppState


class RecognitionBridge:
    """
    识别桥接层

    封装与 Recognizer 子进程的通信，替代 WebSocket 网络通信。

    使用方式：
        bridge = RecognitionBridge(state)
        bridge.on_result(my_callback)
        bridge.start()
        ...
        bridge.submit_audio(task)
        ...
        bridge.stop()
    """

    def __init__(self, state: 'AppState'):
        """
        初始化识别桥接层

        Args:
            state: 应用全局状态（AppState 单例）
        """
        self._state = state
        self._on_result_callbacks: list[Callable] = []
        self._consume_task: Optional[asyncio.Task] = None
        self._sockets_id = None  # Manager().list()，跨进程共享
        self._started = False

    # ========== 公共接口 ==========

    def submit_audio(self, task: AudioTask) -> bool:
        """
        提交音频任务到识别队列（非阻塞）

        将 AudioTask 转换为 Recognizer 子进程使用的 Task 格式，
        放入 multiprocessing.Queue。

        Args:
            task: 音频任务

        Returns:
            是否成功入队
        """
        if not self._started:
            logger.warning("RecognitionBridge 未启动，无法提交音频任务")
            return False

        # 转换为 Recognizer 子进程使用的 Task 格式
        # socket_id 使用固定值（进程内通信不需要区分连接）
        internal_task = Task(
            source=task.source,
            data=task.data,
            offset=task.offset,
            overlap=task.overlap,
            task_id=task.task_id,
            socket_id='local',  # 进程内通信，固定 socket_id
            is_final=task.is_final,
            time_start=task.time_start,
            time_submit=task.time_submit,
            context=task.context,
            samplerate=task.samplerate,
        )

        try:
            self._state.queue_in.put(internal_task, timeout=0.5)
            logger.debug(
                f"提交音频任务: task_id={task.task_id[:8]}, "
                f"source={task.source}, is_final={task.is_final}, "
                f"data_size={len(task.data)} bytes"
            )
            return True
        except queue.Full:
            logger.warning(f"音频队列已满，丢弃任务: task_id={task.task_id[:8]}")
            return False

    def on_result(self, callback: Callable[[RecognitionOutput], None]) -> None:
        """
        注册识别结果回调

        回调在 asyncio 事件循环线程中调用，可以安全地 await 异步操作。

        Args:
            callback: 接收 RecognitionOutput 的回调函数
        """
        if callback not in self._on_result_callbacks:
            self._on_result_callbacks.append(callback)
            logger.debug(f"注册结果回调: {callback.__name__}")

    def start(self) -> bool:
        """
        启动识别桥接层

        1. 检查模型文件
        2. 启动 Recognizer 子进程
        3. 等待模型加载完成
        4. 启动结果消费协程

        Returns:
            是否启动成功
        """
        if self._started:
            logger.warning("RecognitionBridge 已启动，跳过重复启动")
            return True

        logger.info("正在启动 RecognitionBridge...")

        # 1. 检查模型文件
        try:
            check_model()
        except SystemExit:
            logger.error("模型文件检查失败，无法启动")
            return False

        # 2. 初始化跨进程共享的 sockets_id
        self._sockets_id = Manager().list()
        # 添加 'local' 作为固定 socket_id（进程内通信）
        self._sockets_id.append('local')

        # 3. 启动 Recognizer 子进程
        # windowed 模式下 sys.stdin 为 None，使用 os.devnull 替代
        if sys.stdin is None:
            stdin_fn = os.open(os.devnull, os.O_RDONLY)
        else:
            stdin_fn = sys.stdin.fileno()
        recognize_process = Process(
            target=init_recognizer,
            args=(
                self._state.queue_in,
                self._state.queue_out,
                self._sockets_id,
                stdin_fn,
            ),
            daemon=False,
        )
        recognize_process.start()
        self._state.recognize_process = recognize_process
        logger.info("Recognizer 子进程已启动")

        # 4. 轮询等待模型加载完成
        while not lifecycle.is_shutting_down:
            try:
                self._state.queue_out.get(timeout=0.1)
                break
            except queue.Empty:
                if recognize_process.is_alive():
                    continue
                else:
                    break
            except (InterruptedError, OSError) as e:
                if isinstance(e, InterruptedError) or (
                    hasattr(e, 'errno') and e.errno == errno.EINTR
                ):
                    continue
                raise

        # 5. 检查子进程是否存活
        if not recognize_process.is_alive():
            logger.error("Recognizer 子进程意外退出（可能是因为模型文件缺失或加载失败）")
            if recognize_process.exitcode != 0:
                logger.error(f"子进程退出码: {recognize_process.exitcode}")
            lifecycle.request_shutdown()
            return False

        if lifecycle.is_shutting_down:
            logger.warning("在加载模型时收到退出请求")
            recognize_process.terminate()
            return False

        self._state.model_loaded = True
        self._started = True
        logger.info("模型加载完成，RecognitionBridge 已启动")

        # 6. 启动结果消费协程
        self._start_consume_loop()

        return True

    def stop(self) -> None:
        """
        停止识别桥接层

        1. 停止结果消费协程
        2. 向 queue_in 发送 None 通知子进程退出
        3. 终止 Recognizer 子进程
        """
        if not self._started:
            return

        logger.info("正在停止 RecognitionBridge...")
        self._started = False

        # 1. 停止消费协程
        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()

        # 2. 通知子进程退出
        try:
            self._state.queue_in.put(None, timeout=1.0)
        except queue.Full:
            logger.warning("无法发送退出信号到识别子进程（队列已满）")

        # 3. 终止子进程
        recognize_process = self._state.recognize_process
        if recognize_process and recognize_process.is_alive():
            logger.info("正在终止 Recognizer 子进程...")
            recognize_process.terminate()
            recognize_process.join(timeout=5)
            if recognize_process.is_alive():
                logger.warning("Recognizer 子进程未能在 5 秒内退出，强制终止")
                try:
                    recognize_process.kill()
                    recognize_process.join(timeout=1)
                except Exception as e:
                    logger.error(f"强制终止失败: {e}")
            else:
                logger.info("Recognizer 子进程已正常退出")
        elif recognize_process:
            logger.info("Recognizer 子进程已退出")

        self._state.model_loaded = False
        self._state.recognize_process = None
        logger.info("RecognitionBridge 已停止")

    # ========== 内部方法 ==========

    def _start_consume_loop(self) -> None:
        """启动结果消费协程（在 asyncio 事件循环中运行）"""
        loop = self._state.loop
        if loop is None:
            loop = asyncio.get_event_loop()
            self._state.loop = loop

        self._consume_task = asyncio.ensure_future(self._consume_loop())

    async def _consume_loop(self) -> None:
        """
        结果消费循环

        从 queue_out 读取 Result，转换为 RecognitionOutput，
        调用所有注册的回调。
        """
        logger.info("结果消费循环已启动")

        while self._started and not lifecycle.is_shutting_down:
            try:
                # 从 multiprocessing.Queue 读取结果（阻塞调用，通过 to_thread 包装）
                result: Result = await to_thread(self._state.queue_out.get)

                # None 表示退出信号
                if result is None:
                    logger.info("收到退出通知，停止结果消费")
                    return

                # 转换为 RecognitionOutput
                output = RecognitionOutput(
                    task_id=result.task_id,
                    source=result.source,
                    is_final=result.is_final,
                    duration=result.duration,
                    time_start=result.time_start,
                    time_submit=result.time_submit,
                    time_complete=result.time_complete,
                    text=result.text,
                    text_accu=result.text_accu,
                    tokens=result.tokens,
                    timestamps=result.timestamps,
                )

                # 调用所有注册的回调
                for callback in self._on_result_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(output)
                        else:
                            callback(output)
                    except Exception as e:
                        logger.error(
                            f"结果回调执行失败: {callback.__name__}: {e}",
                            exc_info=True,
                        )

            except asyncio.CancelledError:
                logger.info("结果消费循环被取消")
                break
            except Exception as e:
                logger.error(f"结果消费循环异常: {e}", exc_info=True)
                # 短暂等待后继续，避免错误时 CPU 空转
                await asyncio.sleep(0.1)

        logger.info("结果消费循环已退出")
