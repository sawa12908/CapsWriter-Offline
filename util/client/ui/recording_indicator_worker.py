# coding: utf-8
"""Native worker that renders the recording indicator with per-pixel alpha."""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
from typing import Optional

from PIL import Image, ImageDraw
import win32api
import win32con
import win32gui


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

BI_RGB = 0
DIB_RGB_COLORS = 0
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
SW_SHOWNOACTIVATE = 4
WS_EX_NOACTIVATE = 0x08000000


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def _enable_dpi_awareness() -> None:
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


class IndicatorApp:
    """Small layered window that follows the cursor."""

    dot_size = 12
    render_scale = 12
    tick_seconds = 0.016
    offset_x = 7
    offset_y = 7
    dot_color = "#ff2a2a"

    def __init__(self) -> None:
        _enable_dpi_awareness()

        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._commands: "queue.Queue[str]" = queue.Queue()
        self._running = True
        self._visible = False

        self._class_name = f"CapsWriterRecordingIndicator_{win32api.GetCurrentProcessId()}"
        self._class_atom: Optional[int] = None
        self._hwnd: Optional[int] = None

        self._screen_dc = self._user32.GetDC(0)
        self._memory_dc = self._gdi32.CreateCompatibleDC(self._screen_dc)
        self._bitmap_handle: Optional[int] = None
        self._old_bitmap: Optional[int] = None

        self._register_window_class()
        self._create_window()
        self._install_bitmap()

    def _register_window_class(self) -> None:
        wnd_class = win32gui.WNDCLASS()
        wnd_class.hInstance = win32api.GetModuleHandle(None)
        wnd_class.lpszClassName = self._class_name
        wnd_class.lpfnWndProc = self._wnd_proc
        wnd_class.hCursor = 0
        self._wnd_class = wnd_class
        self._class_atom = win32gui.RegisterClass(wnd_class)

    def _create_window(self) -> None:
        ex_style = (
            win32con.WS_EX_LAYERED
            | win32con.WS_EX_TOPMOST
            | win32con.WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )
        self._hwnd = win32gui.CreateWindowEx(
            ex_style,
            self._class_name,
            self._class_name,
            win32con.WS_POPUP,
            0,
            0,
            self.dot_size,
            self.dot_size,
            0,
            0,
            win32api.GetModuleHandle(None),
            None,
        )
        win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)

    def _build_dot_image(self) -> Image.Image:
        scale_size = self.dot_size * self.render_scale
        mask = Image.new("L", (scale_size, scale_size), 0)
        draw = ImageDraw.Draw(mask)
        pad = self.render_scale
        draw.ellipse(
            (
                pad,
                pad,
                scale_size - pad - 1,
                scale_size - pad - 1,
            ),
            fill=255,
        )
        mask = mask.resize((self.dot_size, self.dot_size), Image.Resampling.LANCZOS)

        image = Image.new("RGBA", (self.dot_size, self.dot_size), self.dot_color)
        image.putalpha(mask)
        return image

    def _install_bitmap(self) -> None:
        image = self._build_dot_image()
        bgra = image.tobytes("raw", "BGRA")

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.dot_size
        bmi.bmiHeader.biHeight = -self.dot_size
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = len(bgra)

        bits = ctypes.c_void_p()
        bitmap = self._gdi32.CreateDIBSection(
            self._screen_dc,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
            ctypes.byref(bits),
            0,
            0,
        )
        if not bitmap or not bits.value:
            raise RuntimeError("failed to create recording indicator bitmap")

        ctypes.memmove(bits.value, bgra, len(bgra))

        old_bitmap = self._gdi32.SelectObject(self._memory_dc, bitmap)
        self._bitmap_handle = bitmap
        self._old_bitmap = old_bitmap

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == win32con.WM_DESTROY:
            self._running = False
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _read_commands(self) -> None:
        try:
            for raw_line in sys.stdin:
                command = raw_line.strip().lower()
                if not command:
                    continue
                self._commands.put(command)
                if command == "stop":
                    return
        finally:
            self._commands.put("stop")

    def _drain_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            self._handle_command(command)

    def _handle_command(self, command: str) -> None:
        if command == "show":
            self._show()
            return
        if command == "hide":
            self._hide()
            return
        if command == "stop":
            self._running = False

    def _show(self) -> None:
        if self._visible or self._hwnd is None:
            return

        self._visible = True
        self._update_position()
        win32gui.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)

    def _hide(self) -> None:
        if not self._visible or self._hwnd is None:
            return

        self._visible = False
        win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)

    def _get_cursor_position(self) -> Optional[tuple[int, int]]:
        point = POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)

    def _clamp_to_virtual_screen(self, x: int, y: int) -> tuple[int, int]:
        left = int(self._user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        top = int(self._user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        width = int(self._user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        height = int(self._user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

        max_x = left + max(0, width - self.dot_size)
        max_y = top + max(0, height - self.dot_size)

        x = max(left, min(x, max_x))
        y = max(top, min(y, max_y))
        return x, y

    def _update_position(self) -> None:
        if not self._visible or self._hwnd is None:
            return

        cursor = self._get_cursor_position()
        if cursor is None:
            return

        x = cursor[0] + self.offset_x
        y = cursor[1] - self.dot_size - self.offset_y
        x, y = self._clamp_to_virtual_screen(x, y)
        win32gui.UpdateLayeredWindow(
            self._hwnd,
            self._screen_dc,
            (x, y),
            (self.dot_size, self.dot_size),
            self._memory_dc,
            (0, 0),
            0,
            (AC_SRC_OVER, 0, 255, AC_SRC_ALPHA),
            ULW_ALPHA,
        )

    def _cleanup(self) -> None:
        if self._hwnd is not None:
            try:
                win32gui.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None

        if self._memory_dc and self._old_bitmap:
            try:
                self._gdi32.SelectObject(self._memory_dc, self._old_bitmap)
            except Exception:
                pass

        if self._bitmap_handle:
            try:
                self._gdi32.DeleteObject(self._bitmap_handle)
            except Exception:
                pass
            self._bitmap_handle = None

        if self._memory_dc:
            try:
                self._gdi32.DeleteDC(self._memory_dc)
            except Exception:
                pass
            self._memory_dc = 0

        if self._screen_dc:
            try:
                self._user32.ReleaseDC(0, self._screen_dc)
            except Exception:
                pass
            self._screen_dc = 0

        if self._class_atom is not None:
            try:
                win32gui.UnregisterClass(self._class_name, win32api.GetModuleHandle(None))
            except Exception:
                pass
            self._class_atom = None

    def run(self) -> None:
        reader = threading.Thread(
            target=self._read_commands,
            name="IndicatorCommandReader",
            daemon=True,
        )
        reader.start()

        while self._running:
            self._drain_commands()

            if self._visible:
                self._update_position()

            win32gui.PumpWaitingMessages()
            time.sleep(self.tick_seconds)

        self._cleanup()


def main() -> int:
    app = IndicatorApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
