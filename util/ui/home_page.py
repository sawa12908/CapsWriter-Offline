# coding: utf-8
"""
HomePage 模块

默认欢迎页，显示程序名称、版本号和基本使用提示。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import ClassVar

from .page import Page


class HomePage(Page):
    """
    默认欢迎页

    显示程序名称、版本号、基本使用提示。
    后续可扩展为状态概览页。
    """

    page_id: ClassVar[str] = "home"
    page_title: ClassVar[str] = "首页"

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self) -> None:
        """构建欢迎页 UI"""
        # 主容器，居中显示
        container = ttk.Frame(self)
        container.place(relx=0.5, rely=0.5, anchor="center")

        # 程序名称
        title_label = ttk.Label(
            container,
            text="CapsWriter Offline",
            font=("Microsoft YaHei", 24, "bold"),
        )
        title_label.pack(pady=(0, 8))

        # 版本号
        try:
            from config_client import __version__
            version_text = f"v{__version__}"
        except ImportError:
            version_text = ""
        version_label = ttk.Label(
            container,
            text=version_text,
            font=("Microsoft YaHei", 12),
            foreground="gray",
        )
        version_label.pack(pady=(0, 24))

        # 分隔线
        separator = ttk.Separator(container, orient="horizontal")
        separator.pack(fill="x", pady=(0, 24))

        # 使用提示
        tips = [
            "按住 CapsLock 键开始录音，松开后自动识别并上屏",
            "右键系统托盘图标可访问更多功能",
            "在 LLM 目录下配置角色，实现智能润色和翻译",
            "编辑 hot.txt 添加自定义热词，提高识别准确率",
        ]
        for tip in tips:
            tip_label = ttk.Label(
                container,
                text=f"  {tip}",
                font=("Microsoft YaHei", 11),
                foreground="#555555",
            )
            tip_label.pack(anchor="w", pady=2)

    def on_enter(self) -> None:
        """进入首页时的回调"""
        pass

    def on_leave(self) -> None:
        """离开首页时的回调"""
        pass
