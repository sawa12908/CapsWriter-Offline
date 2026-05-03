# CapsWriter-Offline Technology Stack

> Generated: 2026-05-03 | Version: 2.4.19

## Languages

- **Python 3.12** -- The entire codebase is Python. The conda environment is named `capswriter` (referenced in project documentation). All source files use `# coding: utf-8` encoding headers.

## Runtime Environment

- **conda** environment (`capswriter`) for dependency management
- **Windows 10/11 64-bit** is the primary target platform (per `readme.md`)
- **macOS** has partial support (keyboard permissions check in `core_client.py` line 66-72, Command+V paste in `util/client/clipboard/clipboard.py` line 126-128)
- **Linux** is not officially supported but some platform-agnostic code paths exist

## Key Frameworks and Libraries

### ASR (Automatic Speech Recognition)

| Library | Version Constraint | Purpose | Key Files |
|---------|-------------------|---------|-----------|
| `sherpa-onnx` | (latest) | Core ASR engine, wraps ONNX + GGUF models | `util/server/server_init_recognizer.py`, `util/fun_asr_gguf.py` |
| `onnxruntime-directml` | (latest) | DirectML acceleration for ONNX models on Windows GPU | `config_server.py` line 104 |
| `gguf` | (latest) | GGUF format model loading for Fun-ASR-Nano decoder | `config_server.py` line 59-63 |
| `numpy` | (latest) | Audio data processing, resampling, energy calculation | `util/client/audio/recorder.py`, `util/client/audio/stream.py` |

### Audio I/O

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `sounddevice` | Microphone input stream (48kHz, 50ms blocks, WASAPI on Windows) | `util/client/audio/stream.py` |
| `numpy` | Audio resampling (48kHz to 16kHz mono), noise gate (RMS/peak) | `util/client/audio/recorder.py` |

### UI

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `tkinter` (stdlib) | Main application window, content pages, console output | `util/ui/main_window.py`, `core_client.py` line 326 |
| `pystray` | System tray icon with context menu | `util/ui/tray_manager.py`, `util/ui/tray.py` |
| `Pillow` (PIL) | Tray icon generation (dynamic rounded-rectangle icon) | `util/ui/tray_manager.py` lines 108-147 |
| `rich` | Terminal formatting, Markdown rendering, progress spinners | `util/app_state.py` line 44, `util/server/server_init_recognizer.py` line 75 |
| `colorama` | ANSI escape code support on Windows terminals | `core_client.py` line 52 |
| `tkhtmlview` | HTML rendering in Tkinter (for toast/markdown display) | `requirements-client.txt` line 28 |

### Input/Output

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `pynput` | Global keyboard/mouse listeners (win32_event_filter), Ctrl+V simulation | `util/client/shortcut/shortcut_manager.py`, `util/client/clipboard/clipboard.py` |
| `keyboard` | Text typing simulation (`keyboard.write`), pressed-key detection | `util/client/output/text_output.py` line 131 |
| `pyclip` | Clipboard read/write with multi-encoding fallback | `util/client/clipboard/clipboard.py` |

### LLM Integration

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `openai` (Python SDK) | Unified API client for all LLM providers (OpenAI-compatible) | `util/llm/llm_client_pool.py`, `util/llm/llm_processor.py` |
| `httpx` | HTTP transport layer (used by openai SDK) | `requirements-client.txt` line 17 |

### Text Processing

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `numba` | JIT-compiled phoneme fuzzy matching for hotword RAG | `util/hotword/` (hotword manager) |
| `pypinyin` | Chinese character to pinyin conversion for phoneme matching | `requirements-client.txt` line 22 |
| `srt` | SRT subtitle parsing and generation | `util/client/transcribe/` |

### CLI and Build

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `typer` | CLI argument parsing (file transcription mode) | `core_client.py` line 572 |
| `PyInstaller` 6.0+ | Single-EXE packaging with junction-based deployment | `build.spec`, `build-client.spec`, `build-merged.spec` |
| `watchdog` | File system monitoring (hotword file changes, LLM role reload) | `util/llm/llm_watcher.py`, `util/hotword/` |

### Networking

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `websockets` | WebSocket client/server (deprecated after process-merge, kept for compatibility) | `core_server.py` (deprecated) |
| `socket` (stdlib) | UDP broadcast for output text, UDP control for recording | `util/app_state.py` lines 235-243, `util/client/udp/udp_control.py` |

### System Integration (Windows)

| Library | Purpose | Key Files |
|---------|---------|-----------|
| `winreg` (stdlib) | Windows registry for startup management (HKCU Run key) | `util/tools/startup_manager.py` |
| `ctypes` | Win32 API calls (window handles, DPI awareness, console hiding) | `util/ui/tray_manager.py`, `util/server/server_init_recognizer.py` |
| `multiprocessing` (stdlib) | Recognizer subprocess, inter-process queues | `util/recognition_bridge.py`, `util/app_state.py` |
| `asyncio` (stdlib) | Async event loop for recognition pipeline, LLM streaming | `core_client.py` line 258-273, `util/recognition_bridge.py` |

## Build System

Three PyInstaller `.spec` files in the project root:

| File | Purpose | Console | Entry Point |
|------|---------|---------|-------------|
| `build.spec` | Main single-EXE build (process-merge) | `console=False` | `core_client.py` |
| `build-client.spec` | Client-only EXE (Win7 compatible) | `console=False` | `start_client.py` |
| `build-merged.spec` | Merged single-EXE with console | `console=True` | `core_client.py` |

**Build strategy** (from `build.spec`):
- Incremental deployment: EXE is copied to `dist/CapsWriter-Offline/` on each build
- `internal/` directory only created on first build
- Junction links for `models/`, `assets/`, `util/`, `LLM/` -- source changes take effect immediately
- Runtime hook (`build_hook.py`) adds `executable_dir` and `internal/` to `sys.path`
- Excluded packages: IPython, PySide6, PyQt5, matplotlib, wx, funasr, torch
- CUDA provider DLLs filtered out (DirectML used instead)

## Configuration System

Two main configuration files using class-based configuration:

| File | Class | Purpose |
|------|-------|---------|
| `config_client.py` | `ClientConfig` | Client settings: shortcuts, audio, hotword, LLM, UDP, logging |
| `config_server.py` | `ServerConfig`, `ModelPaths`, `ParaformerArgs`, `SenseVoiceArgs`, `FunASRNanoGGUFArgs` | Server settings: model type, model paths, inference parameters |

Key configuration areas:
- **Shortcuts**: List of dicts with `key`, `type` (keyboard/mouse), `suppress`, `hold_mode`, `enabled`
- **Hotword**: RAG thresholds (`hot_thresh=0.85`, `hot_similar=0.6`, `hot_rectify=0.6`)
- **Audio**: Noise gate (RMS/peak thresholds), segment duration/overlap, sample rate
- **LLM**: `llm_enabled` toggle, `llm_stop_key` (Esc)
- **UDP**: Output broadcast targets, control port for external recording triggers
- **Logging**: Configurable log level per component

## LLM Providers Supported

Defined in `util/llm/llm_constants.py` (class `APIConfig`):

| Provider | Default API URL | Auth |
|----------|----------------|------|
| `ollama` | `http://localhost:11434/v1` | `ollama` (dummy key) |
| `openai` | `https://api.openai.com/v1` | API key required |
| `deepseek` | `https://api.deepseek.com/v1` | API key required |
| `moonshot` | `https://api.moonshot.cn/v1` | API key required |
| `zhipu` | `https://open.bigmodel.cn/api/paas/v4` | API key required |
| `volcengine` | `https://ark.cn-beijing.volces.com/api/v3` | API key required |
| `cerebras` | `https://api.cerebras.ai/v1` | API key required |
| `claude` | (user-configured) | API key required |
| `gemini` | (user-configured) | API key required |

All providers use the OpenAI-compatible API via the `openai` Python SDK. The `ClientPool` class (`util/llm/llm_client_pool.py`) caches client instances by `provider + api_url`.

## ASR Models

Three model types supported, configured via `ServerConfig.model_type` in `config_server.py`:

| Model | Type | Files | Features |
|-------|------|-------|----------|
| **Fun-ASR-Nano** (default) | GGUF + ONNX hybrid | Encoder/Adaptor (fp16 ONNX), CTC (fp16 ONNX), Decoder (q8_0 GGUF) | CTC hotword retrieval, DirectML + Vulkan acceleration, context-aware |
| **SenseVoice** | ONNX | Single model + tokens | Multi-language (zh/en/ja/ko/yue), built-in punctuation, ITN |
| **Paraformer** | ONNX | Model + tokens + CT-Transformer punctuation | Greedy search decoding, separate punctuation model |

Model paths are configured in `config_server.py` class `ModelPaths`, all under `models/` directory.

## Platform Support

- **Windows 10/11 64-bit**: Full support (primary target)
  - WASAPI audio, DirectML GPU acceleration, system tray, startup manager, admin elevation
- **macOS**: Partial support
  - Keyboard permissions check, Command+V paste, no tray/startup
- **Linux**: Not officially supported

## Architecture Pattern

**Process-Merge Architecture** (post v2.4):
- Server logic embedded in client process via `multiprocessing.Process`
- `RecognitionBridge` (`util/recognition_bridge.py`) replaces WebSocket communication
- Communication via `multiprocessing.Queue` (queue_in, queue_out, control_queue)
- Data classes: `AudioTask` and `RecognitionOutput` in `util/recognition_protocol.py`
- Thread model: Tkinter mainloop (main thread) + asyncio event loop (daemon thread) + Recognizer subprocess

## Dependency Files

| File | Lines | Purpose |
|------|-------|---------|
| `requirements-client.txt` | 31 | Client-side Python dependencies |
| `requirements-server.txt` | 17 | Server-side Python dependencies (ASR core) |
