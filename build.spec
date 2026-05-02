# -*- mode: python ; coding: utf-8 -*-
"""
现代化 PyInstaller 打包配置（单 EXE 模式）
适配 PyInstaller 6.0+ 版本

process-merge 后：server 逻辑已内嵌到 client，只打包一个 CapsWriter-Offline.exe

增量构建策略：
- COLLECT 到临时目录 → 只把 EXE 复制到目标 dist
- internal/ 目录只在首次创建，后续不重建（依赖没变）
- util/LLM/models/assets 用 junction 链接源码，改源码直接生效
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
from os.path import join, basename, dirname, exists
from os import walk, makedirs, unlink
from shutil import copyfile, rmtree, move
from platform import system


# ==================== 打包配置选项 ====================

# 是否收集 CUDA provider
INCLUDE_CUDA_PROVIDER = False

# ====================================================


binaries = []
hiddenimports = []
datas = []

# 收集 sherpa_onnx 相关文件
try:
    sherpa_datas = collect_data_files('sherpa_onnx', include_py_files=False)

    if not INCLUDE_CUDA_PROVIDER:
        filtered_datas = []
        for src, dest in sherpa_datas:
            if 'providers_cuda' not in basename(src).lower():
                filtered_datas.append((src, dest))
            else:
                print(f"[INFO] 排除 CUDA provider: {basename(src)}")
        sherpa_datas = filtered_datas

    datas += sherpa_datas
except:
    pass

# 收集 Pillow 相关文件（用于托盘图标）
try:
    pillow_datas = collect_data_files('PIL', include_py_files=False)
    datas += pillow_datas
    pillow_binaries = collect_all('PIL')
    binaries += pillow_binaries[1]
except:
    pass

# 收集 rich 子模块（Markdown 渲染需要）
try:
    rich_submodules = collect_submodules('rich._unicode_data')
    hiddenimports += rich_submodules
    print(f"[INFO] 收集到 {len(rich_submodules)} 个 rich._unicode_data 子模块")
except Exception as e:
    print(f"[WARNING] 收集 rich 子模块失败: {e}")

hiddenimports += [
    'websockets',
    'websockets.client',
    'websockets.server',
    'rich',
    'rich.console',
    'rich.markdown',
    'keyboard',
    'pyclip',
    'numpy',
    'numba',
    'sounddevice',
    'pypinyin',
    'watchdog',
    'typer',
    'srt',
    'sherpa_onnx',
    'PIL',
    'PIL.Image',
    'pystray',
]

a = Analysis(
    ['core_client.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build_hook.py'],
    excludes=['IPython',
              'PySide6', 'PySide2', 'PyQt5',
              'matplotlib', 'wx',
              'funasr', 'torch',
              ],
    noarchive=False,
)

# 过滤掉从二进制依赖分析中收集的 DLL
filtered_binaries = []
for name, src, type in a.binaries:
    src_lower = src.lower() if isinstance(src, str) else ''
    is_system_cuda_dll = (
        '\\nvidia gpu computing toolkit\\cuda\\' in src_lower or
        '\\nvidia\\cudnn\\' in src_lower or
        ('\\cuda\\v' in src_lower and '\\bin\\' in src_lower)
    )
    is_unwanted_onnx_dll = (
        'onnxruntime_providers_cuda.dll' in name.lower() or
        'directml.dll' in name.lower()
    )

    if not is_system_cuda_dll and not is_unwanted_onnx_dll:
        filtered_binaries.append((name, src, type))
    else:
        reason = "环境 CUDA DLL" if is_system_cuda_dll else "冗余 ONNX DLL"
        print(f"[INFO] 排除 {reason}: {name} (从 {src} 收集)")
a.binaries = filtered_binaries

# 排除不要打包的模块（这些将作为源文件复制到 dist）
private_module = ['util', 'config_client', 'config_server', 'LLM',
                  'core_server', 'core_client',
                  ]

pure = a.pure.copy()
a.pure.clear()
for name, src, type in pure:
    condition = [name == m or name.startswith(m + '.') for m in private_module]
    if condition and any(condition):
        ...
    else:
        a.pure.append((name, src, type))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CapsWriter-Offline',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\\\icon.ico'],
    contents_directory='internal',
)

# COLLECT 到临时目录，然后增量复制到目标
tmp_root = join('dist', '_coll_temp')
if exists(tmp_root):
    rmtree(tmp_root)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='_coll_temp',
)

# ========== 增量部署到 dist/CapsWriter-Offline ==========

dest_root = join('dist', 'CapsWriter-Offline')

# 1. 复制 EXE（每次都更新）
# EXE 设置了 exclude_binaries=True，单独生成在 build/build/ 下
exe_name = 'CapsWriter-Offline.exe'
tmp_exe = join('build', 'build', exe_name)
dest_exe = join(dest_root, exe_name)
if exists(tmp_exe):
    makedirs(dest_root, exist_ok=True)
    if exists(dest_exe):
        try:
            unlink(dest_exe)
        except PermissionError:
            bak = dest_exe + '.old'
            if exists(bak):
                unlink(bak)
            move(dest_exe, bak)
            print(f"[INFO] 旧 EXE 正在使用，已重命名为 .old")
    copyfile(tmp_exe, dest_exe)
    print(f"[INFO] EXE 已更新: {dest_exe}")

# 2. internal/ 目录只在首次创建
tmp_internal = join(tmp_root, 'internal')
dest_internal = join(dest_root, 'internal')
if exists(tmp_internal) and not exists(dest_internal):
    move(tmp_internal, dest_internal)
    print(f"[INFO] internal/ 已创建: {dest_internal}")
elif exists(tmp_internal):
    rmtree(tmp_internal)
    print(f"[INFO] internal/ 已存在，跳过")

# 3. 为 models 等大文件夹建立目录连接符（必须在复制文件之前）
if system() == 'Windows':
    from _winapi import CreateJunction
    link_folders = ['models', 'assets', 'util', 'LLM']
    for folder in link_folders:
        src_folder = join(os.getcwd(), folder)
        if not exists(src_folder):
            continue
        dest_folder = join(dest_root, folder)
        if exists(dest_folder):
            continue
        try:
            CreateJunction(src_folder, dest_folder)
            print(f"[INFO] Junction created: {dest_folder} -> {src_folder}")
        except Exception as e:
            print(f'警告：无法创建目录连接符 {dest_folder}: {e}')

# 4. 复制额外所需的文件（仅首次或文件缺失时）
# 注意：util/ 已是 junction，复制文件会直接写入源码目录
my_files = [
    'config_client.py',
    'config_server.py',
    'core_server.py',
    'core_client.py',
    'hot.txt',
    'hot-server.txt',
    'hot-rectify.txt',
    'hot-rule.txt',
    'readme.md',
    'util/client/ui/recording_indicator_worker.py',
]
my_folders = []

for folder in my_folders:
    if not exists(folder):
        continue
    for dirpath, dirnames, filenames in walk(folder):
        for filename in filenames:
            src_file = join(dirpath, filename)
            if exists(src_file):
                my_files.append(src_file)

for file in my_files:
    if not exists(file):
        continue
    rel_path = file.replace('\\', '/') if '\\' in file else file
    dest_file = join(dest_root, rel_path)
    if exists(dest_file):
        continue
    dest_folder = dirname(dest_file)
    makedirs(dest_folder, exist_ok=True)
    copyfile(file, dest_file)

# 5. 清理临时 COLLECT 目录
if exists(tmp_root):
    rmtree(tmp_root)
    print(f"[INFO] 临时目录已清理: {tmp_root}")
