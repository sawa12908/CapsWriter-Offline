"""
客户端资源清理模块

负责在客户端退出时释放各种资源。

process-merge: 移除 WebSocket 关闭逻辑，增加 Recognizer 子进程终止。
"""

from . import logger
from util.common.lifecycle import lifecycle
from util.app_state import get_state, console


def request_exit_from_tray(icon=None, item=None):
    """
    托盘引用的退出回调
    """
    logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
    lifecycle.request_shutdown(reason="Tray Icon")

def cleanup_client_resources():
    """
    清理客户端资源（process-merge 改造）

    移除 WebSocket 关闭逻辑，增加 RecognitionBridge 停止（终止 Recognizer 子进程）。
    """
    state = get_state()

    # 停止快捷键监听
    if state.shortcut_handler:
        try:
            state.shortcut_handler.stop()
            logger.debug("快捷键监听已停止")
        except Exception as e:
            logger.warning(f"停止快捷键监听时发生错误: {e}")

    # 停止鼠标监听器
    if state.mouse_handler:
        try:
            state.mouse_handler.stop()
            logger.debug("鼠标监听已停止")
        except Exception as e:
            logger.warning(f"停止鼠标监听时发生错误: {e}")

    # 停止音频流
    if state.stream_manager:
        try:
            if hasattr(state.stream_manager, 'close'):
                 state.stream_manager.close()
        except Exception as e:
            logger.warning(f"停止音频流时发生错误: {e}")

    # 停止结果处理器
    if state.processor:
        try:
            state.processor.request_exit()
        except Exception as e:
            logger.warning(f"停止结果处理器时发生错误: {e}")

    # process-merge: 停止 RecognitionBridge（终止 Recognizer 子进程）
    bridge = getattr(state, '_bridge', None)
    if bridge is not None:
        try:
            logger.info("正在停止识别桥接层（终止 Recognizer 子进程）...")
            bridge.stop()
            logger.info("识别桥接层已停止")
        except Exception as e:
            logger.warning(f"停止识别桥接层时发生错误: {e}")

    # 彻底重置状态
    try:
        state.reset()
    except Exception as e:
        logger.warning(f"重置状态时发生错误: {e}")

    # 停止托盘图标
    try:
        from util.client.ui import stop_tray
        stop_tray()
    except Exception as e:
        logger.warning(f"停止托盘图标时发生错误: {e}")

    logger.info("客户端资源清理完成")
    console.print('[green4]再见！')
