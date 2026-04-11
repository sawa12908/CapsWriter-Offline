# coding: utf-8


"""
这个文件仅仅是为了 PyInstaller 打包用
"""

import os
import sys
from pathlib import Path

import typer
from core_client import init_file, init_mic
from util.client.ui.recording_indicator_worker import main as run_recording_indicator_worker
from util.tools.windows_privilege import ensure_single_instance

if __name__ == "__main__":
    if os.environ.get("CAPSWRITER_RECORDING_INDICATOR_WORKER") == "1":
        raise SystemExit(run_recording_indicator_worker())

    ensure_single_instance(base_dir=str(Path(__file__).resolve().parent), role="client")

    # 如果参数传入文件，那就转录文件
    # 如果没有多余参数，就从麦克风输入
    if sys.argv[1:]:
        typer.run(init_file)
    else:
        init_mic()
