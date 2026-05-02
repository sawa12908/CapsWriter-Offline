# coding: utf-8
"""
NavBar 导航栏组件

左侧垂直导航栏，显示程序图标、名称和已注册页面的导航按钮列表。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional


class NavBar(ttk.Frame):
    """
    左侧垂直导航栏

    显示程序图标+名称，以及所有已注册页面的导航按钮。
    点击按钮时触发页面切换回调。
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_navigate: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        """
        Args:
            parent: 父容器
            on_navigate: 导航回调，参数为 page_id
        """
        super().__init__(parent, width=200, **kwargs)
        self.pack_propagate(False)  # 固定宽度 200px
        self._on_navigate = on_navigate
        self._nav_buttons: Dict[str, ttk.Button] = {}
        self._current_page_id: Optional[str] = None

        self._build_ui()

    def _build_ui(self) -> None:
        """构建导航栏 UI"""
        # 程序图标和名称
        logo_frame = ttk.Frame(self)
        logo_frame.pack(fill="x", padx=12, pady=(16, 8))

        logo_label = ttk.Label(
            logo_frame,
            text="CapsWriter",
            font=("Microsoft YaHei", 14, "bold"),
        )
        logo_label.pack(anchor="w")

        subtitle_label = ttk.Label(
            logo_frame,
            text="Offline",
            font=("Microsoft YaHei", 10),
            foreground="gray",
        )
        subtitle_label.pack(anchor="w")

        # 分隔线
        separator = ttk.Separator(self, orient="horizontal")
        separator.pack(fill="x", padx=8, pady=(8, 4))

        # 导航按钮容器
        self._button_frame = ttk.Frame(self)
        self._button_frame.pack(fill="both", expand=True, padx=4, pady=4)

    def add_page(self, page_id: str, page_title: str) -> None:
        """
        添加导航按钮

        Args:
            page_id: 页面唯一标识
            page_title: 导航按钮显示文本
        """
        if page_id in self._nav_buttons:
            return

        btn = ttk.Button(
            self._button_frame,
            text=page_title,
            command=lambda pid=page_id: self._on_button_click(pid),
        )
        btn.pack(fill="x", padx=4, pady=1)
        self._nav_buttons[page_id] = btn

    def set_active(self, page_id: str) -> None:
        """
        设置当前激活的导航按钮（高亮）

        Args:
            page_id: 要激活的页面 ID
        """
        self._current_page_id = page_id
        # 注意：ttk.Button 没有直接的"选中"样式
        # 这里通过修改文本前缀来标识当前选中项
        for pid, btn in self._nav_buttons.items():
            # 从按钮文本中获取原始标题
            text = btn.cget("text")
            if pid == page_id:
                if not text.startswith("  "):
                    btn.configure(text=f"  {text}")
            else:
                if text.startswith("  "):
                    btn.configure(text=text[2:])

    def _on_button_click(self, page_id: str) -> None:
        """导航按钮点击处理"""
        if self._on_navigate:
            self._on_navigate(page_id)
