# coding: utf-8
"""
Windows privilege helpers.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path
from platform import system


def is_process_elevated() -> bool:
    """
    Return whether the current process is running elevated on Windows.

    Non-Windows platforms always return False.
    """
    if system() != "Windows":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin_restart(base_dir: str, python_executable: str | None = None) -> bool:
    """Start an elevated helper that restarts the CapsWriter client and server."""
    if system() != "Windows":
        return False

    repo_dir = Path(base_dir).resolve()
    python_path = str(Path(python_executable or sys.executable).resolve())
    helper_script = Path(__file__).resolve()
    params = subprocess.list2cmdline(
        [
            str(helper_script),
            "--restart-capswriter",
            "--base-dir",
            str(repo_dir),
            "--python-exe",
            python_path,
        ]
    )

    if is_process_elevated():
        try:
            subprocess.Popen(
                [python_path, str(helper_script), "--restart-capswriter", "--base-dir", str(repo_dir), "--python-exe", python_path],
                cwd=str(repo_dir),
                stdout=None,
                stderr=None,
                stdin=None,
                close_fds=True,
                creationflags=_visible_creationflags(),
            )
            return True
        except Exception:
            return False

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            python_path,
            params,
            str(repo_dir),
            1,
        )
        return result > 32
    except Exception:
        return False


def _visible_creationflags() -> int:
    flags = 0
    for name in ("CREATE_NEW_CONSOLE", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, name, 0)
    return flags


def _launch_process(command: list[str], working_dir: Path) -> None:
    subprocess.Popen(
        command,
        cwd=str(working_dir),
        stdout=None,
        stderr=None,
        stdin=None,
        close_fds=True,
        creationflags=_visible_creationflags(),
    )


def _launch_python_script(python_executable: str, script_path: Path, working_dir: Path) -> None:
    _launch_process([python_executable, str(script_path)], working_dir)


def _launch_executable(executable_path: Path, working_dir: Path) -> None:
    _launch_process([str(executable_path)], working_dir)


def _terminate_capswriter_processes(base_dir: Path) -> None:
    repo = str(base_dir).replace("'", "''")
    exe_dir = str(base_dir / "dist" / "CapsWriter-Offline").replace("'", "''")
    script = rf"""
$repo = '{repo}'
$exeDir = '{exe_dir}'
Get-CimInstance Win32_Process |
Where-Object {{
    (
        $_.Name -match 'python|pythonw' -and
        $_.CommandLine -and
        $_.CommandLine -like "*${{repo}}*" -and
        ($_.CommandLine -match 'start_server\.py|start_client\.py|recording_indicator_worker\.py')
    ) -or (
        $_.ExecutablePath -and
        $_.ExecutablePath -like "*${{exeDir}}*" -and
        $_.Name -match 'start_server|start_client'
    )
}} |
Sort-Object ProcessId -Descending |
ForEach-Object {{
    try {{ taskkill /PID $_.ProcessId /T /F | Out-Null }} catch {{ }}
}}
""".strip()
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def ensure_single_instance(base_dir: str, role: str, python_executable: str | None = None) -> None:
    """Terminate older CapsWriter processes for the same role before startup."""
    if system() != "Windows":
        return

    repo_dir = Path(base_dir).resolve()
    role = role.strip().lower()
    if role not in {"client", "server"}:
        raise ValueError(f"unsupported CapsWriter role: {role}")

    current_pid = subprocess.os.getpid()
    python_path = str(Path(python_executable or sys.executable).resolve())
    script_name = f"start_{role}.py"
    exe_name = f"start_{role}.exe"
    repo = str(repo_dir).replace("'", "''")
    python_path_ps = python_path.replace("'", "''")
    script = rf"""
$repo = '{repo}'
$currentPid = {current_pid}
$pythonPath = '{python_path_ps}'
Get-CimInstance Win32_Process |
Where-Object {{
    $_.ProcessId -ne $currentPid -and (
        (
            $_.Name -match 'python|pythonw' -and
            $_.CommandLine -and
            $_.CommandLine -like "*${{repo}}*" -and
            $_.CommandLine -like "*{script_name}*" -and
            $_.ExecutablePath -and
            $_.ExecutablePath -eq $pythonPath
        ) -or (
            $_.ExecutablePath -and
            $_.ExecutablePath -like "*{exe_name}*"
        )
    )
}} |
Sort-Object ProcessId -Descending |
ForEach-Object {{
    try {{ taskkill /PID $_.ProcessId /T /F | Out-Null }} catch {{ }}
}}
""".strip()
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def restart_capswriter_pair(base_dir: str, python_executable: str | None = None) -> int:
    """Elevated helper entrypoint that restarts both CapsWriter processes."""
    if system() != "Windows":
        return 1

    repo_dir = Path(base_dir).resolve()
    python_path = str(Path(python_executable or sys.executable).resolve())
    server_script = repo_dir / "start_server.py"
    client_script = repo_dir / "start_client.py"
    dist_dir = repo_dir / "dist" / "CapsWriter-Offline"
    server_exe = dist_dir / "start_server.exe"
    client_exe = dist_dir / "start_client.exe"

    use_executables = False
    if not use_executables and (not server_script.exists() or not client_script.exists()):
        return 1

    time.sleep(1.0)
    _terminate_capswriter_processes(repo_dir)
    time.sleep(0.8)
    if use_executables:
        _launch_executable(server_exe, dist_dir)
    else:
        _launch_python_script(python_path, server_script, repo_dir)
    time.sleep(2.0)
    if use_executables:
        _launch_executable(client_exe, dist_dir)
    else:
        _launch_python_script(python_path, client_script, repo_dir)
    return 0


def _main(argv: list[str]) -> int:
    if len(argv) >= 6 and argv[1] == "--restart-capswriter" and argv[2] == "--base-dir" and argv[4] == "--python-exe":
        return restart_capswriter_pair(argv[3], argv[5])
    return 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
