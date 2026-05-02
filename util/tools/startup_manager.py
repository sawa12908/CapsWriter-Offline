# coding: utf-8
"""
Windows 开机启动管理模块

通过注册表 HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
管理 CapsWriter 的开机启动项。不需要管理员权限。
"""

import sys
import winreg
from pathlib import Path
from platform import system

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "CapsWriter-Offline"


# 原始注册表路径（仅用于文档）
_REG_PATH_DOC = r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run"


def _escape_ps(path: str) -> str:
    """转义 PowerShell 单引号字符串中的单引号"""
    return path.replace("'", "''")


def _build_startup_command(base_dir: str):
    """构建开机启动用的 PowerShell 命令"""
    base = Path(base_dir).resolve()

    # 检测是否为打包环境（PyInstaller）
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        server_exe = exe_dir / "start_server.exe"
        client_exe = exe_dir / "start_client.exe"
        if server_exe.exists() and client_exe.exists():
            working_dir = str(exe_dir)
            server_cmd = (
                f"Start-Process -FilePath '{_escape_ps(str(server_exe))}' "
                f"-WorkingDirectory '{_escape_ps(working_dir)}'"
            )
            client_cmd = (
                f"Start-Process -FilePath '{_escape_ps(str(client_exe))}' "
                f"-WorkingDirectory '{_escape_ps(working_dir)}'"
            )
        else:
            return None
    else:
        python_exe = sys.executable
        server_script = base / "start_server.py"
        client_script = base / "start_client.py"
        if not server_script.exists() or not client_script.exists():
            return None
        working_dir = str(base)
        server_cmd = (
            f"Start-Process -FilePath '{_escape_ps(python_exe)}' "
            f"-ArgumentList '{_escape_ps(str(server_script))}' "
            f"-WorkingDirectory '{_escape_ps(working_dir)}'"
        )
        client_cmd = (
            f"Start-Process -FilePath '{_escape_ps(python_exe)}' "
            f"-ArgumentList '{_escape_ps(str(client_script))}' "
            f"-WorkingDirectory '{_escape_ps(working_dir)}'"
        )

    ps_cmd = (
        f"Set-Location -LiteralPath '{_escape_ps(working_dir)}'; "
        f"{server_cmd}; "
        f"Start-Sleep -Seconds 2; "
        f"{client_cmd}"
    )
    return f'powershell.exe -WindowStyle Hidden -Command "{ps_cmd}"'


def is_startup_enabled() -> bool:
    """检查 CapsWriter 是否已设置为开机启动"""
    if system() != "Windows":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


def set_startup(enabled: bool, base_dir: str) -> bool:
    """
    设置或取消开机启动

    Args:
        enabled: True 表示启用，False 表示禁用
        base_dir: 项目根目录

    Returns:
        bool: 是否成功
    """
    if system() != "Windows":
        return False

    if enabled:
        cmd = _build_startup_command(base_dir)
        if not cmd:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            return True
        except OSError:
            return False
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, APP_NAME)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False
