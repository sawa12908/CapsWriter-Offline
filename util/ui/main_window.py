# coding: utf-8
"""
MainWindow 主窗口模块

Tkinter Toplevel 窗口，程序的主界面框架。
包含左侧导航栏、右侧内容区、底部状态栏。
窗口关闭时最小化到托盘而非退出进程。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from .nav_bar import NavBar
from .status_bar import StatusBar
from .page import Page
from .home_page import HomePage


class MainWindow:
    """
    主窗口框架

    管理导航栏、内容区和状态栏。
    提供页面注册、路由切换、状态更新等接口。

    使用方式:
        main_window = MainWindow()
        main_window.register_page(HomePage(main_window.content_area))
        main_window.show()
    """

    def __init__(
        self,
        title: str = "CapsWriter Offline",
        width: int = 900,
        height: int = 650,
        min_width: int = 600,
        min_height: int = 400,
    ):
        """
        Args:
            title: 窗口标题
            width: 默认宽度（像素）
            height: 默认高度（像素）
            min_width: 最小宽度（像素）
            min_height: 最小高度（像素）
        """
        self._title = title
        self._width = width
        self._height = height
        self._min_width = min_width
        self._min_height = min_height

        # 页面注册表
        self._pages: Dict[str, Page] = {}
        self._current_page_id: Optional[str] = None

        # 关闭回调（由外部设置，用于最小化到托盘）
        self._on_close_callback: Optional[callable] = None

        # 创建窗口（使用 Tk 根窗口而非 Toplevel，避免需要额外的隐藏根窗口）
        self.root = tk.Tk()
        self.root.title(self._title)
        self.root.minsize(self._min_width, self._min_height)
        # 初始隐藏，等调用方决定何时显示
        self.root.withdraw()

        # 居中显示
        self._center_window()

        # 构建 UI
        self._build_ui()

        # 注册默认首页
        home_page = HomePage(self.content_area)
        self.register_page(home_page)

        # 默认显示首页
        self.navigate_to("home")

    def _center_window(self) -> None:
        """将窗口居中显示"""
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - self._width) // 2
        y = (screen_height - self._height) // 2
        self.root.geometry(f"{self._width}x{self._height}+{x}+{y}")

    def _build_ui(self) -> None:
        """构建主窗口 UI 结构"""
        # 主容器
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # 使用 PanedWindow 实现可拖拽分隔的左右布局
        self.paned_window = ttk.PanedWindow(
            self.main_frame, orient="horizontal"
        )
        self.paned_window.pack(fill="both", expand=True)

        # 左侧导航栏
        self.nav_bar = NavBar(
            self.paned_window,
            on_navigate=self.navigate_to,
        )
        self.paned_window.add(self.nav_bar, weight=0)

        # 右侧内容区
        self.content_area = ttk.Frame(self.paned_window)
        self.paned_window.add(self.content_area, weight=1)

        # 底部状态栏
        self.status_bar = StatusBar(self.main_frame)
        self.status_bar.pack(side="bottom", fill="x")

    def register_page(self, page: Page) -> None:
        """
        注册功能页面

        Args:
            page: Page 子类实例
        """
        if page.page_id in self._pages:
            # 已存在同 ID 页面，先移除旧的
            old_page = self._pages.pop(page.page_id)
            old_page.destroy()

        self._pages[page.page_id] = page
        self.nav_bar.add_page(page.page_id, page.page_title)

    def navigate_to(self, page_id: str) -> None:
        """
        切换到指定页面

        Args:
            page_id: 目标页面 ID
        """
        if page_id not in self._pages:
            import logging
            logging.getLogger("util.ui").warning(
                f"导航到不存在的页面: {page_id}"
            )
            return

        if page_id == self._current_page_id:
            return

        # 离开旧页面
        if self._current_page_id and self._current_page_id in self._pages:
            old_page = self._pages[self._current_page_id]
            try:
                old_page.on_leave()
            except Exception:
                pass
            old_page.pack_forget()

        # 进入新页面
        new_page = self._pages[page_id]
        new_page.pack(fill="both", expand=True)
        try:
            new_page.on_enter()
        except Exception:
            pass

        self._current_page_id = page_id
        self.nav_bar.set_active(page_id)

    def set_on_close(self, callback: callable) -> None:
        """
        设置窗口关闭回调

        Args:
            callback: 关闭时调用的函数
        """
        self._on_close_callback = callback

    def set_status(self, status: str) -> None:
        """
        更新状态栏识别状态

        Args:
            status: 状态文本，如 "空闲"、"录音中"、"识别中"
        """
        self.status_bar.set_status(status)

    def set_role(self, role_name: str) -> None:
        """
        更新状态栏角色显示

        Args:
            role_name: 角色名称
        """
        self.status_bar.set_role(role_name)

    def set_model_status(self, loaded: bool = False, progress: float = 0.0) -> None:
        """
        更新状态栏模型状态

        Args:
            loaded: 模型是否已加载
            progress: 加载进度（0.0 ~ 1.0）
        """
        self.status_bar.set_model_status(loaded, progress)

    def show_toast(self, text: str, duration: int = 3000, bg: str = "#075077") -> None:
        """
        显示 Toast 通知（封装现有 toast 功能）

        Args:
            text: 消息文本
            duration: 显示时长（毫秒）
            bg: 背景颜色
        """
        try:
            from .toast import toast
            toast(text, duration=duration, bg=bg)
        except Exception:
            pass

    def show(self) -> None:
        """显示窗口"""
        self.root.deiconify()
        self.root.lift()

    def hide(self) -> None:
        """隐藏窗口（最小化到托盘）"""
        self.root.withdraw()

    def toggle_visible(self) -> None:
        """切换窗口可见性"""
        if self.root.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def destroy(self) -> None:
        """销毁窗口"""
        try:
            self.root.destroy()
        except Exception:
            pass

    def get_hwnd(self) -> int:
        """
        获取窗口句柄（Windows）

        Returns:
            窗口句柄，失败返回 0
        """
        try:
            import ctypes
            # 确保窗口已创建
            self.root.update_idletasks()
            # 使用 Tkinter 的 frame() 方法获取 HWND
            hwnd = self.root.frame()
            if hwnd:
                return hwnd
            # 备用方案：通过窗口标题查找
            hwnd = ctypes.windll.user32.FindWindowW(None, self._title)
            return hwnd
        except Exception:
            return 0


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    import sys
    import os

    # 确保项目根目录在 sys.path 中
    file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(file_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 创建主窗口（MainWindow 内部使用 tk.Tk）
    main_window = MainWindow()

    # 拦截关闭按钮
    main_window.root.protocol("WM_DELETE_WINDOW", main_window.hide)

    print("主窗口已显示。")
    print("测试功能：")
    print("  - 左侧导航栏有'首页'按钮")
    print("  - 右侧显示欢迎页")
    print("  - 底部状态栏显示默认信息")
    print("  - 点 X 隐藏窗口（不退出）")
    print("按 Ctrl+C 退出")

    try:
        main_window.root.mainloop()
    except KeyboardInterrupt:
        print("\n程序退出")
