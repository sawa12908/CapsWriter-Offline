# coding: utf-8


'''
这个文件仅仅是为了 PyInstaller 打包用
'''

from multiprocessing import freeze_support
from pathlib import Path

import core_server
from util.tools.windows_privilege import ensure_single_instance

import sys

if __name__ == '__main__':
    freeze_support()
    ensure_single_instance(base_dir=str(Path(__file__).resolve().parent), role='server')
    core_server.init()
    sys.exit(0)
