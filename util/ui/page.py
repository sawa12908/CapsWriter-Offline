# coding: utf-8
"""
Page 基类模块

定义主窗口内容区中所有功能页面的基类。
每个 Page 是 ttk.Frame 的子类，有唯一的 page_id 和导航显示名 page_title。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import ClassVar


class Page(ttk.Frame):
    """
    功能页面基类

    所有嵌入主窗口内容区的页面都应继承此类。

    类属性:
        page_id: 页面唯一标识符（用于路由）
        page_title: 导航栏显示名称

    生命周期方法:
        on_enter(): 页面被切换到前台时调用
        on_leave(): 页面被切换到后台时调用
    """

    page_id: ClassVar[str] = ""
    page_title: ClassVar[str] = ""

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)

    def on_enter(self) -> None:
        """页面被切换到前台时调用（子类可重写）"""
        pass

    def on_leave(self) -> None:
        """页面被切换到后台时调用（子类可重写）"""
        pass
