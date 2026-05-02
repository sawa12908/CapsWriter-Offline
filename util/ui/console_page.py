# coding: utf-8
"""
ConsolePage 模块

将控制台输出（rich console.print 和 logger）重定向到主窗口内的滚动文本区域。
"""

from __future__ import annotations

import logging
import queue
import re
import tkinter as tk
from tkinter import ttk
from typing import ClassVar, Optional

from .page import Page

# ANSI / rich 标记的简单剥离正则
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_RICH_TAG_RE = re.compile(r'\[/?[a-zA-Z#][^\]]*\]')


class ConsolePage(Page):
    """
    控制台输出页面

    将原本显示在黑色控制台窗口的内容重定向到此页面的滚动文本区域。
    支持 ANSI 颜色码和 rich 标记的简单处理。
    """

    page_id: ClassVar[str] = "console"
    page_title: ClassVar[str] = "输出"

    _MAX_LINES = 5000

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        self._write_queue: queue.Queue = queue.Queue()
        self._after_id: Optional[str] = None
        self._build_ui()
        self._start_polling()

    def _build_ui(self) -> None:
        """构建控制台输出 UI"""
        # 工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=4, pady=(4, 0))

        ttk.Label(toolbar, text="控制台输出", font=("Microsoft YaHei", 10, "bold")).pack(side="left")

        ttk.Button(toolbar, text="清空", command=self._clear).pack(side="right", padx=2)
        ttk.Button(toolbar, text="复制全部", command=self._copy_all).pack(side="right", padx=2)

        # 文本区域 + 滚动条
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=6,
            pady=6,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        # 配置文本标签样式
        self.text.tag_configure("green", foreground="#6a9955")
        self.text.tag_configure("cyan", foreground="#4ec9b0")
        self.text.tag_configure("yellow", foreground="#dcdcaa")
        self.text.tag_configure("magenta", foreground="#c586c0")
        self.text.tag_configure("red", foreground="#f44747")
        self.text.tag_configure("bold", font=("Consolas", 10, "bold"))
        self.text.tag_configure("dim", foreground="#808080")
        self.text.tag_configure("info", foreground="#d4d4d4")
        self.text.tag_configure("warning", foreground="#dcdcaa")
        self.text.tag_configure("error", foreground="#f44747")
        self.text.tag_configure("debug", foreground="#808080")

    def _start_polling(self) -> None:
        """启动定时轮询，将队列中的文本写入 widget"""
        self._flush_queue()
        self._after_id = self.after(50, self._start_polling)

    def _flush_queue(self) -> None:
        """将队列中的所有待写入文本刷新到 widget"""
        try:
            while True:
                text, tag = self._write_queue.get_nowait()
                self._append_text(text, tag)
        except queue.Empty:
            pass

    def _append_text(self, text: str, tag: Optional[str] = None) -> None:
        """向文本区域追加内容"""
        if not text:
            return

        self.text.configure(state="normal")

        # 限制最大行数
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > self._MAX_LINES:
            # 删除前 1000 行
            self.text.delete("1.0", "1000.0")

        if tag:
            self.text.insert("end", text, tag)
        else:
            # 解析 rich 标记和 ANSI 码
            self._insert_with_tags(text)

        # 自动滚动到底部
        self.text.see("end")
        self.text.configure(state="disabled")

    def _insert_with_tags(self, text: str) -> None:
        """解析 rich 标记并插入带标签的文本"""
        # 简单的 rich 标记解析：[color]text[/] 或 [bold color]text[/]
        pos = 0
        while pos < len(text):
            # 查找下一个标记
            tag_match = re.search(r'\[/?[a-zA-Z#][^\]]*\]', text[pos:])
            if not tag_match:
                # 剩余纯文本
                self.text.insert("end", text[pos:])
                break

            # 插入标记前的纯文本
            if tag_match.start() > 0:
                self.text.insert("end", text[pos:pos + tag_match.start()])

            tag_str = tag_match.group()
            tag_start = pos + tag_match.start()

            if tag_str.startswith("[/"):
                # 结束标记，跳过
                pos = tag_start + len(tag_str)
                continue

            # 开始标记，查找对应的结束标记和内容
            inner_start = tag_start + len(tag_str)
            end_tag = "[/]"
            end_pos = text.find(end_tag, inner_start)
            if end_pos == -1:
                # 没有结束标记，当作纯文本
                self.text.insert("end", tag_str)
                pos = inner_start
                continue

            inner_text = text[inner_start:end_pos]

            # 解析颜色
            tag_name = tag_str[1:-1].lower()
            tk_tag = None
            if "green" in tag_name:
                tk_tag = "green"
            elif "cyan" in tag_name:
                tk_tag = "cyan"
            elif "yellow" in tag_name:
                tk_tag = "yellow"
            elif "magenta" in tag_name:
                tk_tag = "magenta"
            elif "red" in tag_name:
                tk_tag = "red"
            elif "bold" in tag_name:
                tk_tag = "bold"
            elif "dim" in tag_name:
                tk_tag = "dim"

            if tk_tag:
                self.text.insert("end", inner_text, tk_tag)
            else:
                self.text.insert("end", inner_text)

            pos = end_pos + len(end_tag)

    def write(self, text: str, tag: Optional[str] = None) -> None:
        """线程安全地写入文本"""
        if not text:
            return
        self._write_queue.put((text, tag))

    def _clear(self) -> None:
        """清空文本区域"""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _copy_all(self) -> None:
        """复制全部内容到剪贴板"""
        content = self.text.get("1.0", "end-1c")
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)

    def destroy(self) -> None:
        """清理资源"""
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        super().destroy()


class TkinterLogHandler(logging.Handler):
    """将 logging 输出重定向到 ConsolePage 的日志处理器"""

    _LEVEL_TAGS = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "error",
    }

    def __init__(self, console_page: ConsolePage):
        super().__init__()
        self._page = console_page

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            tag = self._LEVEL_TAGS.get(record.levelno, "info")
            self._page.write(msg + "\n", tag)
        except Exception:
            pass


class TkinterConsoleFile:
    """
    类似文件的对象，将写入的内容转发到 ConsolePage。

    用于替换 sys.stdout / sys.stderr，以及 rich.console.Console 的 file 参数。
    """

    def __init__(self, console_page: ConsolePage):
        self._page = console_page
        self._buffer = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._page.write(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False
