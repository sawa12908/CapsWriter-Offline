# coding: utf-8
"""
TrayManager 托盘管理器

适配现有 util/ui/tray.py 的 _TraySystem，使其操作 Tkinter 主窗口
而非控制台窗口。复用现有托盘图标创建、菜单、监控逻辑。
"""

from __future__ import annotations

import os
import sys
import time
import threading
import platform
import ctypes
from typing import Optional, Callable, List

from . import logger


class TrayManager:
    """
    主窗口托盘管理器

    包装现有 _TraySystem，将操作对象从控制台窗口切换为 Tkinter 窗口。

    使用方式:
        tray = TrayManager(
            root=main_window.root,
            name="CapsWriter 客户端",
            icon_path="assets/icon.ico",
            exit_callback=on_exit,
            more_options=[...]
        )
        tray.start()
    """

    def __init__(
        self,
        root,  # tk.Toplevel or tk.Tk
        name: Optional[str] = None,
        icon_path: Optional[str] = None,
        exit_callback: Optional[Callable] = None,
        more_options: Optional[List] = None,
    ):
        """
        Args:
            root: Tkinter 根窗口或 Toplevel
            name: 托盘显示名称
            icon_path: 图标文件路径
            exit_callback: 退出回调函数
            more_options: 额外菜单项列表
        """
        self.root = root
        self.name = name or "CapsWriter"
        self.icon_path = icon_path
        self.exit_callback = exit_callback
        self.more_options = more_options or []

        self._tray_instance = None
        self._monitor_thread = None
        self._should_exit = False

        # 获取 Tkinter 窗口句柄
        self.hwnd = self._get_tk_hwnd()

    def _get_tk_hwnd(self) -> int:
        """
        获取 Tkinter 窗口的 Windows 句柄

        Returns:
            窗口句柄，失败返回 0
        """
        if platform.system() != "Windows":
            return 0

        try:
            # 确保窗口已创建
            self.root.update_idletasks()
            # Tkinter 8.5+ 提供 frame() 方法获取 HWND
            hwnd = self.root.frame()
            if hwnd:
                return hwnd

            # 备用方案：通过窗口标题查找
            title = self.root.title()
            if title:
                hwnd = ctypes.windll.user32.FindWindowW(None, title)
                if hwnd:
                    return hwnd
        except Exception as e:
            logger.warning(f"获取 Tkinter 窗口句柄失败: {e}")

        return 0

    def _check_tray_available(self) -> bool:
        """检查托盘功能是否可用"""
        if platform.system() != "Windows":
            return False
        try:
            import pystray
            from PIL import Image
            return True
        except ImportError:
            return False

    def _create_icon(self):
        """创建托盘图标（复用 tray.py 的逻辑）"""
        from PIL import Image, ImageDraw

        if self.icon_path and os.path.exists(self.icon_path):
            try:
                image = Image.open(self.icon_path)
                if image.mode != "RGBA":
                    image = image.convert("RGBA")
                return image.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception:
                pass

        # 动态生成图标
        size = 64
        scale = 4
        real_size = size * scale

        image = Image.new("RGBA", (real_size, real_size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        blue = (55, 118, 171)
        yellow = (255, 211, 67)
        white = (255, 255, 255)

        m = 2 * scale
        dc.rounded_rectangle(
            [m, m, real_size - m, real_size - m],
            radius=real_size // 4,
            fill=blue,
        )

        center = real_size // 2
        r = real_size // 3.5
        dc.ellipse([center - r, center - r, center + r, center + r], fill=yellow)

        r2 = r // 2
        dc.ellipse([center - r2, center - r2, center + r2, center + r2], fill=white)

        return image.resize((size, size), Image.Resampling.LANCZOS)

    def _toggle_window(self) -> None:
        """切换主窗口显示/隐藏"""
        try:
            if self.root.state() == "withdrawn":
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            else:
                self.root.withdraw()
        except Exception as e:
            logger.warning(f"切换窗口状态失败: {e}")

    def _on_exit(self, icon, item) -> None:
        """托盘退出处理"""
        logger.info("托盘退出: 用户点击退出菜单")

        # 设置退出标志
        self._should_exit = True

        # 显示窗口（确保能正常销毁）
        try:
            self.root.deiconify()
        except Exception:
            pass

        # 调用退出回调
        if self.exit_callback:
            try:
                self.exit_callback()
            except Exception as e:
                logger.error(f"退出回调执行失败: {e}")

        # 停止托盘图标
        try:
            icon.stop()
        except Exception as e:
            logger.warning(f"停止托盘图标失败: {e}")

    def _monitor_loop(self) -> None:
        """监控线程：检测窗口最小化操作"""
        user32 = None
        try:
            user32 = ctypes.windll.user32
        except Exception:
            pass

        while not self._should_exit:
            if self.hwnd and user32:
                try:
                    # 窗口可见且最小化 -> 隐藏到托盘
                    if (
                        user32.IsWindowVisible(self.hwnd)
                        and user32.IsIconic(self.hwnd)
                    ):
                        self.root.after(0, self.root.withdraw)
                except Exception:
                    pass
            time.sleep(0.2)

    def start(self) -> None:
        """启动托盘系统"""
        if not self._check_tray_available():
            logger.info("托盘功能不可用，跳过")
            return

        # DPI 感知设置
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        import pystray
        from pystray import MenuItem as item

        # 构建菜单
        menu_items = [
            item(f"{self.name}", lambda: None, enabled=False),
            item("显示/隐藏", self._toggle_window, default=True),
        ]

        # 添加额外选项
        for opt in self.more_options:
            if isinstance(opt, (list, tuple)):
                if len(opt) == 2:
                    menu_items.append(item(opt[0], opt[1]))
                elif len(opt) == 3:
                    menu_items.append(item(opt[0], opt[1], checked=opt[2]))
                else:
                    menu_items.append(item(*opt))
            else:
                menu_items.append(opt)

        menu_items.append(item("退出", self._on_exit))

        # 创建托盘图标
        icon_id = "capswriter_main_window"
        self._tray_instance = pystray.Icon(
            icon_id,
            self._create_icon(),
            title=self.name,
            menu=tuple(menu_items),
        )

        # 托盘图标线程
        t_tray = threading.Thread(target=self._tray_instance.run, daemon=False)
        t_tray.start()

        # 状态监控线程
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()

        logger.info("主窗口托盘管理器已启动")

    def stop(self) -> None:
        """停止托盘图标"""
        self._should_exit = True
        if self._tray_instance:
            try:
                self._tray_instance.stop()
            except Exception:
                pass
            self._tray_instance = None
