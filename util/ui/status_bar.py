# coding: utf-8
"""
StatusBar 状态栏组件

底部状态栏，显示当前角色、识别状态和模型加载状态。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StatusBar(ttk.Frame):
    """
    底部状态栏

    显示三部分信息：
    - 当前角色名称
    - 识别状态（空闲/录音中/识别中）
    - 模型加载状态
    """

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        self._role_text = tk.StringVar(value="default")
        self._status_text = tk.StringVar(value="空闲")
        self._model_text = tk.StringVar(value="模型: 未加载")

        self._build_ui()

    def _build_ui(self) -> None:
        """构建状态栏 UI"""
        # 左侧：角色信息
        role_label = ttk.Label(
            self,
            textvariable=self._role_text,
            font=("Microsoft YaHei", 9),
            foreground="#555555",
        )
        role_label.pack(side="left", padx=(12, 0))

        # 分隔符
        sep1 = ttk.Separator(self, orient="vertical")
        sep1.pack(side="left", fill="y", padx=8, pady=2)

        # 中间：识别状态
        status_label = ttk.Label(
            self,
            textvariable=self._status_text,
            font=("Microsoft YaHei", 9),
            foreground="#555555",
        )
        status_label.pack(side="left")

        # 分隔符
        sep2 = ttk.Separator(self, orient="vertical")
        sep2.pack(side="left", fill="y", padx=8, pady=2)

        # 右侧：模型状态
        model_label = ttk.Label(
            self,
            textvariable=self._model_text,
            font=("Microsoft YaHei", 9),
            foreground="#555555",
        )
        model_label.pack(side="left")

    def set_role(self, role_name: str) -> None:
        """
        更新当前角色显示

        Args:
            role_name: 角色名称，如 "default"、"翻译" 等
        """
        self._role_text.set(f"角色: {role_name}")

    def set_status(self, status: str) -> None:
        """
        更新识别状态显示

        Args:
            status: 状态文本，如 "空闲"、"录音中"、"识别中"
        """
        self._status_text.set(status)

    def set_model_status(self, loaded: bool = False, progress: float = 0.0) -> None:
        """
        更新模型加载状态

        Args:
            loaded: 模型是否已加载
            progress: 加载进度（0.0 ~ 1.0）
        """
        if loaded:
            self._model_text.set("模型: 已就绪")
        elif progress > 0:
            pct = int(progress * 100)
            self._model_text.set(f"模型: 加载中 {pct}%")
        else:
            self._model_text.set("模型: 未加载")
