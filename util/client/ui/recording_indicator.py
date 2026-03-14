# coding: utf-8
"""Controller for the recording indicator worker process."""

from __future__ import annotations

import atexit
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from .. import logger


class RecordingIndicator:
    """Control a small always-on-top worker window that follows the cursor."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._worker_path = Path(__file__).with_name("recording_indicator_worker.py")
        if not self._worker_path.exists():
            raise FileNotFoundError(f"recording indicator worker missing: {self._worker_path}")

        self._start_worker()
        atexit.register(self.stop)

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _start_worker(self) -> None:
        if self._is_running():
            return

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(
                [sys.executable, str(self._worker_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=creationflags,
            )
            logger.debug("recording indicator worker started")
        except Exception as e:
            self._process = None
            logger.warning(f"failed to start recording indicator worker: {e}")
            raise

    def _write_command(self, command: str, restart_if_needed: bool) -> None:
        if restart_if_needed and not self._is_running():
            self._start_worker()

        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return

        try:
            process.stdin.write(f"{command}\n")
            process.stdin.flush()
        except Exception as e:
            logger.debug(f"recording indicator command failed ({command}): {e}")
            self._terminate_process(wait_timeout=0.5)

            if restart_if_needed:
                self._start_worker()
                process = self._process
                if process is not None and process.stdin is not None:
                    process.stdin.write(f"{command}\n")
                    process.stdin.flush()

    def _terminate_process(self, wait_timeout: float) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass

        try:
            process.wait(timeout=wait_timeout)
            return
        except Exception:
            pass

        try:
            process.terminate()
            process.wait(timeout=wait_timeout)
            return
        except Exception:
            pass

        try:
            process.kill()
            process.wait(timeout=wait_timeout)
        except Exception:
            pass

    def show(self) -> None:
        with self._lock:
            self._write_command("show", restart_if_needed=True)

    def hide(self) -> None:
        with self._lock:
            self._write_command("hide", restart_if_needed=False)

    def stop(self) -> None:
        with self._lock:
            process = self._process
            if process is None:
                return

            try:
                if process.stdin is not None and process.poll() is None:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
            except Exception:
                pass

            self._terminate_process(wait_timeout=0.7)
