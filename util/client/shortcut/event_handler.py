# coding: utf-8
"""
事件处理器

处理键盘和鼠标事件的逻辑
"""

import time
from . import logger



class ShortcutEventHandler:
    """
    快捷键事件处理器

    处理按键按下和释放的逻辑，包括录音启动、取消、完成等
    """

    def __init__(self, tasks, pool, emulator):
        """
        初始化事件处理器

        Args:
            tasks: 快捷键任务字典
            pool: 线程池
            emulator: 快捷键模拟器
        """
        self.tasks = tasks
        self.pool = pool
        self.emulator = emulator
        self._pending_hold_futures = {}

    def handle_keydown(self, key_name, task) -> None:
        """处理按键按下事件"""
        # 长按模式
        if task.shortcut.hold_mode:
            self._handle_hold_keydown(key_name, task)
            return

        # 单击模式
        if task.released:
            from threading import Event
            task.pressed = True
            task.released = False
            task.event = Event()  # 创建新事件对象
            self.pool.submit(self._count_down, task)
            self.pool.submit(self._manage_task, task)

    def handle_keyup(self, key_name, task) -> None:
        """处理按键释放事件"""
        # 单击模式
        if not task.shortcut.hold_mode:
            if task.pressed:
                task.pressed = False
                task.released = True
                task.event.set()
            return

        # 长按模式
        task.pressed = False
        task.released = True

        if task.is_pending_hold:
            logger.debug(f"[{key_name}] 松开：短按，未进入录音")
            self._cancel_pending_hold(key_name, task)
            if task.shortcut.suppress:
                logger.debug(f"[{key_name}] 安排异步补发按键")
                self.pool.submit(self.emulator.emulate_key, key_name)
            return

        if not task.is_recording:
            return

        duration = time.time() - task.recording_start_time
        logger.debug(f"[{key_name}] 松开，持续时间: {duration:.2f}s")
        task.finish()

    def _handle_hold_keydown(self, key_name, task) -> None:
        """处理长按模式按下事件。"""
        if task.pressed or task.is_recording or task.is_pending_hold:
            return

        if self._should_delay_hold_launch(key_name, task):
            task.mark_pending_hold()
            future = self.pool.submit(self._arm_hold_recording, key_name, task)
            self._pending_hold_futures[task] = future
            return

        task.launch()

    def _should_delay_hold_launch(self, key_name, task) -> bool:
        """仅对 suppress 的 CapsLock 启用两阶段启动。"""
        normalized_key = str(key_name).replace(' ', '_').lower()
        return (
            normalized_key == 'caps_lock'
            and task.shortcut.suppress
            and task.shortcut.is_toggle_key()
        )

    def _arm_hold_recording(self, key_name, task) -> None:
        """超过阈值后再真正启动录音。"""
        time.sleep(task.threshold)

        if not task.pressed or task.released or not task.is_pending_hold:
            logger.debug(f"[{key_name}] 长按等待取消，不启动录音")
            return

        logger.debug(f"[{key_name}] 超过阈值，开始录音")
        self._pending_hold_futures.pop(task, None)
        task.launch()

    def _cancel_pending_hold(self, key_name, task) -> None:
        """取消等待中的长按启动。"""
        task.clear_pending_hold()
        future = self._pending_hold_futures.pop(task, None)
        if future is not None:
            future.cancel()
        logger.debug(f"[{key_name}] 已取消长按等待态")

    def _count_down(self, task) -> None:
        """倒计时（单击模式）"""
        time.sleep(task.threshold)
        task.event.set()

    def _manage_task(self, task) -> None:
        """管理录音任务（单击模式）"""
        was_recording = task.is_recording

        if not was_recording:
            task.launch()

        if task.event.wait(timeout=task.threshold * 0.8):
            if task.is_recording and was_recording:
                task.finish()
        else:
            if not was_recording:
                task.cancel()
