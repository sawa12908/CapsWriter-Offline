# coding: utf-8
"""
CapsWriter Offline Client 入口模块

这是语音输入客户端的主程序入口，支持两种模式：
1. 麦克风模式：实时语音输入（带主窗口 UI）
2. 文件转录模式：将音视频文件转录为字幕（无主窗口）

使用方法：
    python core_client.py              # 麦克风模式
    python core_client.py file1.mp4    # 文件转录模式
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path
from platform import system
from typing import List

import colorama
import typer

from config_client import ClientConfig as Config, __version__
from util.logger import setup_logger
from util.common.lifecycle import lifecycle
from util.client.cleanup import cleanup_client_resources, request_exit_from_tray

# 确保根目录位置正确，用相对路径加载模型
# 打包后 __file__ 可能指向 internal/，需要用 sys.executable 定位 EXE 所在目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)
os.chdir(BASE_DIR)

# 确保终端能使用 ANSI 控制字符
colorama.init()

# 初始化日志系统
logger = setup_logger('client', level=Config.log_level)

# 全局变量，用于跟踪资源状态
_main_task = None  # 主任务引用
_main_window = None  # 主窗口引用（麦克风模式）
_asyncio_thread = None  # asyncio 事件循环线程引用
_asyncio_loop = None  # asyncio 事件循环引用（供 Tkinter 线程调度用）


def _check_macos_permissions() -> None:
    """检查 MacOS 权限设置"""
    if system() == 'Darwin' and not sys.argv[1:]:
        if os.getuid() != 0:
            print('在 MacOS 上需要以管理员启动客户端才能监听键盘活动，请 sudo 启动')
            input('按回车退出')
            sys.exit(1)
        else:
            os.umask(0o000)


async def main_mic() -> None:
    """
    麦克风模式主函数（运行在 asyncio 守护线程中）

    启动实时语音识别，监听快捷键开始/结束录音。

    process-merge 后流程：
    1. 初始化 AppState
    2. 启动 RecognitionBridge（内嵌 Recognizer 子进程，等待模型加载）
    3. 初始化客户端组件（快捷键、音频流、热词、LLM）
    4. 进入主循环（ResultProcessor 通过 on_result 回调接收结果）
    """
    global _main_task, _asyncio_loop

    # 初始化生命周期
    lifecycle.initialize(logger=logger, exit_on_signal=True)

    # 保存事件循环引用（供 Tkinter 线程调度用）
    _asyncio_loop = asyncio.get_running_loop()

    # 保存当前任务的引用
    _main_task = asyncio.current_task()

    from util.app_state import get_state, console
    from util.recognition_bridge import RecognitionBridge
    from util.client.output import ResultProcessor
    from util.client.startup import setup_client_components

    logger.info("=" * 50)
    logger.info("CapsWriter Offline Client 正在启动（麦克风模式）")
    logger.info(f"版本: {__version__}")
    logger.info(f"日志级别: {Config.log_level}")

    # 1. 初始化 AppState（替代原 ClientState + Cosmic）
    _state = get_state()
    _state.initialize()

    # 2. 启动 RecognitionBridge（内嵌 Recognizer 子进程，等待模型加载）
    bridge = RecognitionBridge(_state)
    logger.info("正在启动识别桥接层（启动 Recognizer 子进程并等待模型加载）...")
    if not bridge.start():
        logger.error("识别桥接层启动失败")
        console.print("[red]模型加载失败，请检查模型文件是否完整")
        lifecycle.request_shutdown()
        return
    _state._bridge = bridge  # 保存引用供后续使用

    # 通知主线程：模型已就绪
    _schedule_ui_update("model_ready")

    # 3. 初始化客户端组件（快捷键、音频流、热词、LLM 等）
    _state = setup_client_components(BASE_DIR)

    # 4. 接收结果
    try:
        processor = ResultProcessor(_state)
        _state.processor = processor  # 注入状态以便清理

        # 注册 on_result 回调（替代 WebSocket 接收）
        bridge.on_result(processor._handle_result)

        # 主循环：只要没收到退出信号，就一直运行
        while not lifecycle.is_shutting_down:
            # 创建等待退出任务
            wait_shutdown = asyncio.create_task(lifecycle.wait_for_shutdown())
            await wait_shutdown

            if lifecycle.is_shutting_down:
                logger.info("主循环检测到退出信号")
                break

    except asyncio.CancelledError:
        logger.info("主任务被取消，正在退出...")
        raise
    except Exception as e:
        logger.error(f"接收结果时发生错误: {e}", exc_info=True)
        raise
    finally:
        # 全局资源清理交给 lifecycle
        pass


async def main_file(files: List[Path]) -> None:
    """
    文件转录模式主函数

    process-merge 后：使用 RecognitionBridge 替代 WebSocket。

    Args:
        files: 要转录的文件列表
    """
    # 初始化生命周期
    lifecycle.initialize(logger=logger, exit_on_signal=True)

    from util.app_state import get_state, console
    from util.recognition_bridge import RecognitionBridge
    from util.client.transcribe import FileTranscriber, SrtAdjuster
    from util.client.ui import TipsDisplay

    logger.info("=" * 50)
    logger.info("CapsWriter Offline Client 正在启动（文件转录模式）")
    logger.info(f"版本: {__version__}")
    logger.info(f"日志级别: {Config.log_level}")
    logger.info(f"待处理文件: {[str(f) for f in files]}")

    state = get_state()
    state.initialize()

    # 启动 RecognitionBridge（内嵌 Recognizer 子进程）
    bridge = RecognitionBridge(state)
    logger.info("正在启动识别桥接层...")
    if not bridge.start():
        logger.error("识别桥接层启动失败")
        console.print("[red]模型加载失败，请检查模型文件是否完整")
        lifecycle.request_shutdown()
        return
    state._bridge = bridge

    TipsDisplay.show_file_tips()

    srt_adjuster = SrtAdjuster()

    for file in files:
        if lifecycle.is_shutting_down:
            break

        logger.info(f"正在处理文件: {file}")

        if file.suffix in ['.txt', '.json', '.srt']:
            srt_adjuster.adjust(file)
        else:
            transcriber = FileTranscriber(state, file)
            if await transcriber.check():
                await transcriber.send()
                await transcriber.receive()

        logger.info(f"文件处理完成: {file}")

    # 停止识别桥接层
    bridge.stop()

    logger.info("所有文件已处理完成")
    input('\n按回车退出\n')


# ============================================================
# Tkinter 与 asyncio 线程间通信
# ============================================================

def _schedule_ui_update(action: str, *args) -> None:
    """
    从 asyncio 线程调度 UI 更新到 Tkinter 主线程

    Args:
        action: 操作名称，如 "model_ready", "status", "role"
        *args: 操作参数
    """
    global _main_window
    if _main_window is None:
        return
    try:
        _main_window.root.after(0, lambda: _handle_ui_update(action, *args))
    except Exception:
        pass


def _handle_ui_update(action: str, *args) -> None:
    """在主线程中处理 UI 更新（由 root.after 调度）"""
    global _main_window
    if _main_window is None:
        return

    if action == "model_ready":
        _main_window.set_model_status(loaded=True, progress=1.0)
    elif action == "status":
        if args:
            _main_window.set_status(args[0])
    elif action == "role":
        if args:
            _main_window.set_role(args[0])


def _run_asyncio_in_thread() -> None:
    """在守护线程中运行 asyncio 事件循环"""
    global _asyncio_loop
    try:
        _asyncio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_asyncio_loop)
        _asyncio_loop.run_until_complete(main_mic())
    except Exception as e:
        logger.error(f"asyncio 线程异常: {e}", exc_info=True)
    finally:
        # asyncio 线程退出后，通知主线程清理
        if _main_window is not None:
            try:
                _main_window.root.after(0, _on_asyncio_thread_exit)
            except Exception:
                pass


def _on_asyncio_thread_exit() -> None:
    """asyncio 线程退出后的主线程清理"""
    global _main_window
    logger.info("asyncio 线程已退出，执行主线程清理")
    lifecycle.cleanup()
    if _main_window is not None:
        _main_window.destroy()
        _main_window = None


def _on_main_window_close() -> None:
    """主窗口关闭回调：隐藏到托盘而非退出"""
    global _main_window
    if _main_window is not None:
        _main_window.hide()
        logger.debug("主窗口已隐藏到托盘")


def _on_tray_exit() -> None:
    """托盘退出回调：触发完整清理流程"""
    logger.info("托盘退出：请求关闭")
    lifecycle.request_shutdown(reason="Tray Exit")

    # 通知 asyncio 线程退出
    global _asyncio_loop
    if _asyncio_loop is not None and _asyncio_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            _trigger_asyncio_shutdown(), _asyncio_loop
        )


async def _trigger_asyncio_shutdown() -> None:
    """在 asyncio 线程中触发关闭"""
    lifecycle.request_shutdown(reason="Tray Exit")


def _setup_main_window_ui(base_dir: str) -> None:
    """
    创建主窗口并设置托盘（在主线程中调用）

    Args:
        base_dir: 项目根目录
    """
    global _main_window

    from util.ui.main_window import MainWindow
    from util.ui.tray_manager import TrayManager

    # 创建主窗口（MainWindow 内部使用 tk.Tk，无需额外根窗口）
    _main_window = MainWindow()

    # 拦截关闭按钮：隐藏到托盘
    _main_window.root.protocol("WM_DELETE_WINDOW", _on_main_window_close)

    # 设置托盘管理器
    _setup_tray_for_main_window(base_dir)

    logger.info("主窗口 UI 初始化完成")


def _setup_tray_for_main_window(base_dir: str) -> None:
    """为主窗口设置托盘管理器（复用现有托盘菜单逻辑）"""
    global _main_window

    from util.ui.tray_manager import TrayManager

    def _toast(message: str, duration: int = 2200, bg: str = "#075077") -> None:
        try:
            from util.ui.toast import toast
            toast(message, duration=duration, bg=bg)
        except Exception:
            logger.info(message)

    def restart_audio():
        from util.app_state import get_state
        state = get_state()
        manager = state.stream_manager
        if not manager:
            _toast("Audio stream is not ready yet.", bg="#8a3a2f")
            return
        manager.reopen(reason="tray:restart-audio")
        logger.info("user requested audio restart from tray")

    def restart_capswriter():
        logger.info("user requested full restart from tray")
        from util.tools.windows_privilege import request_admin_restart
        ok = request_admin_restart(base_dir=base_dir, python_executable=sys.executable)
        if not ok:
            _toast("Restart request failed. Please try again as administrator.", duration=3200, bg="#8a3a2f")
            logger.warning("tray restart request failed to launch elevated helper")
            return
        _toast("Restarting CapsWriter client and server as administrator...", duration=2600)
        lifecycle.request_shutdown(reason="Tray Restart")

    def clear_memory():
        from util.llm.llm_handler import clear_llm_history
        clear_llm_history()
        _toast("Memory cleared: all role chat history removed.", duration=3000)

    def add_hotword():
        try:
            from util.client.ui import on_add_hotword
            on_add_hotword()
        except ImportError as e:
            logger.warning(f"failed to import hotword menu handler: {e}")

    def add_rectify():
        try:
            from util.client.ui import on_add_rectify_record
            on_add_rectify_record()
        except ImportError as e:
            logger.warning(f"failed to import rectify menu handler: {e}")

    def add_context():
        try:
            from util.client.ui import on_edit_context
            on_edit_context()
        except ImportError as e:
            logger.warning(f"failed to import context menu handler: {e}")

    def copy_last_result():
        from util.app_state import get_state
        state = get_state()
        text = state.last_output_text
        if text:
            from util.llm.llm_clipboard import copy_to_clipboard
            copy_to_clipboard(text)

    # 开机启动
    try:
        from util.tools.startup_manager import is_startup_enabled, set_startup
        has_startup = True
    except Exception as e:
        logger.debug(f"startup manager import failed: {e}")
        has_startup = False

    def toggle_startup(icon, item):
        if not has_startup:
            return
        current = is_startup_enabled()
        success = set_startup(not current, base_dir)
        if success:
            status = "已启用" if not current else "已取消"
            _toast(f"开机启动 {status}")
            logger.info(f"startup toggled: {not current}")
        else:
            _toast("设置开机启动失败", bg="#8a3a2f")
            logger.warning("failed to toggle startup setting")

    icon_path = os.path.join(base_dir, "assets", "icon.ico")
    more_options = [
        ("复制上次结果", copy_last_result),
        ("编辑上下文", add_context),
        ("添加热词", add_hotword),
        ("添加纠错", add_rectify),
        ("清空记忆", clear_memory),
        ("重启音频", restart_audio),
        ("重启软件", restart_capswriter),
    ]
    if has_startup:
        more_options.insert(0, ("开机启动", toggle_startup, lambda item: is_startup_enabled()))

    tray = TrayManager(
        root=_main_window.root,
        name="CapsWriter 客户端",
        icon_path=icon_path,
        exit_callback=_on_tray_exit,
        more_options=more_options,
    )
    tray.start()
    # 保存托盘引用以便清理
    _main_window._tray_manager = tray


def init_mic() -> None:
    """
    初始化并运行麦克风模式（主窗口 + asyncio 子线程）

    主线程：Tkinter mainloop
    子线程：asyncio 事件循环 + 业务逻辑
    """
    global _asyncio_thread, _main_window

    from util.app_state import console

    # 0. Windows: 确保单实例 + 管理员权限
    if system() == "Windows":
        from util.tools.windows_privilege import is_process_elevated, request_admin_restart, ensure_single_instance

        # 先杀掉旧实例（避免多实例互相重启）
        ensure_single_instance(BASE_DIR, "client", python_executable=sys.executable)

        # 非管理员则自动提权重启
        if not is_process_elevated():
            logger.info("当前非管理员，自动请求提权重启...")
            ok = request_admin_restart(base_dir=BASE_DIR, python_executable=sys.executable)
            if ok:
                logger.info("已发起管理员权限重启请求，当前进程退出")
                sys.exit(0)
            else:
                logger.warning("提权重启失败，继续以普通权限运行")

    # 注册清理函数
    lifecycle.register_on_shutdown(cleanup_client_resources)

    # 1. 在主线程创建主窗口和托盘
    _setup_main_window_ui(BASE_DIR)

    # 2. 启动 asyncio 事件循环在守护线程中
    _asyncio_thread = threading.Thread(
        target=_run_asyncio_in_thread,
        daemon=True,
        name="AsyncioThread",
    )
    _asyncio_thread.start()

    # 3. 进入 Tkinter mainloop（阻塞主线程）
    try:
        # MainWindow.root 就是 Tk 根实例，直接进入 mainloop
        _main_window.root.mainloop()
    except KeyboardInterrupt:
        logger.info("收到停止信号...")
    finally:
        # mainloop 退出后执行清理
        lifecycle.cleanup()
        if _main_window is not None:
            _main_window.destroy()
            _main_window = None


def init_file(files: List[Path]) -> None:
    """
    初始化并运行文件转录模式（无主窗口）
    """
    from util.app_state import console

    lifecycle.register_on_shutdown(cleanup_client_resources)

    try:
        asyncio.run(main_file(files))
        lifecycle.cleanup()
    except KeyboardInterrupt:
        logger.info("收到停止信号...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"转录文件时发生错误: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # PyInstaller 打包后，Windows 上使用 multiprocessing.Process 需要调用 freeze_support
    from multiprocessing import freeze_support
    freeze_support()

    # Recording indicator worker 子进程：直接运行 worker 逻辑，不走完整客户端
    if os.environ.get("CAPSWRITER_RECORDING_INDICATOR_WORKER") == "1":
        from util.client.ui.recording_indicator_worker import main as run_recording_indicator_worker
        raise SystemExit(run_recording_indicator_worker())

    # 检查 MacOS 权限
    _check_macos_permissions()

    # 过滤掉 multiprocessing 子进程参数（--multiprocessing-fork 等）
    args = [a for a in sys.argv[1:] if not a.startswith('--multiprocessing-')]

    # 如果参数传入文件，那就转录文件
    # 如果没有多余参数，就从麦克风输入
    if args:
        # 只把存在的文件路径传给 init_file
        files = [Path(f) for f in args if Path(f).exists()]
        if files:
            typer.run(init_file)
        else:
            init_mic()
    else:
        init_mic()
