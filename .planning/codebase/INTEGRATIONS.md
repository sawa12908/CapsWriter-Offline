# CapsWriter-Offline 集成点

**日期:** 2026-05-03
**版本:** 2.4.19

---

## 内部集成

### 进程间通信（IPC）

```
Client 主进程 ←→ Recognizer 子进程
     │                  │
     │  queue_in        │  (multiprocessing.Queue: AudioTask → Recognizer)
     │  queue_out       │  (multiprocessing.Queue: RecognitionOutput → Client)
     │  control_queue   │  (multiprocessing.Queue: AudioChunk → AudioRecorder)
```

- **协议:** `util/recognition_protocol.py` — `AudioTask` / `RecognitionOutput` dataclass
- **桥接层:** `util/recognition_bridge.py` — `RecognitionBridge` 管理子进程生命周期
- **序列化:** pickle（multiprocessing.Queue 默认）

### 线程间通信

```
Tkinter 主线程 ←→ asyncio 守护线程
      │                    │
      │ root.after(0, cb)  │  (asyncio → UI 更新)
      │ run_coroutine_     │  (其他线程 → asyncio 调度)
      │   threadsafe()     │
```

- **共享状态:** `util/app_state.py` — `AppState` 全局单例（无锁，多线程读写）
- **UI 回调:** `_schedule_ui_update()` → `root.after(0, _handle_ui_update)`

### 子进程

| 子进程 | 启动方式 | 通信方式 |
|--------|---------|---------|
| Recognizer | `multiprocessing.Process` (daemon=False) | `queue_in` / `queue_out` |
| Recording Indicator | `subprocess.Popen` | stdin 命令 / stdout 状态 |

## 外部集成

### LLM API 提供商

通过 OpenAI 兼容 API 调用，配置在 `LLM/*.py` 角色文件中：

| 提供商 | API 基础 URL |
|--------|-------------|
| Ollama | `http://localhost:11434/v1` |
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Moonshot | `https://api.moonshot.cn/v1` |
| Zhipu | `https://open.bigmodel.cn/api/paas/v4` |
| Claude | `https://api.anthropic.com` |
| Gemini | `https://generativelanguage.googleapis.com` |

### UDP 广播

- **输出广播:** `config_client.py:88-92` — 识别结果通过 UDP 广播到 `127.255.255.255:6017`
- **控制接口:** `config_client.py:94-96` — 外部程序可通过 UDP 发送 START/STOP 命令到 `127.0.0.1:6018`

### 系统集成

| 集成点 | 实现 |
|--------|------|
| 全局快捷键 | `keyboard` + `pynput` 库，监听 CapsLock / F13 / X2 |
| 系统托盘 | `pystray`，右键菜单（热词/纠错/重启等） |
| 开机启动 | `util/tools/startup_manager.py`，Windows 启动文件夹快捷方式 |
| 管理员提权 | `util/tools/windows_privilege.py`，`ShellExecuteW` + `runas` |
| 音频设备 | `sounddevice` (PortAudio)，支持设备热插拔检测（`WM_DEVICECHANGE`） |
| 剪贴板 | `pyclip`，读取选中文字 / 粘贴识别结果 |
| 键盘模拟 | `keyboard.write()`，直接打字输出 |

### 文件系统监控

| 监控目标 | 实现 | 用途 |
|----------|------|------|
| `hot.txt` | `watchdog` → `HotwordManager` | 热词热重载 |
| `hot-rule.txt` | `watchdog` → `HotwordManager` | 规则热重载 |
| `hot-rectify.txt` | `watchdog` → `HotwordManager` | 纠错历史热重载 |
| `LLM/*.py` | `watchdog` → `LLMFileWatcher` | LLM 角色热重载 |

## 数据流

### 语音识别全链路

```
麦克风 → sounddevice 回调 → AudioStreamManager
  → control_queue → AudioRecorder (重采样 48kHz→16kHz)
  → queue_in → Recognizer 子进程 (Sherpa-ONNX)
  → queue_out → RecognitionBridge._consume_loop()
  → ResultProcessor._handle_result()
  → 热词替换 (FastRAG + AccuRAG)
  → LLM 润色 (可选)
  → 输出 (keyboard.write / Toast / UDP)
```

### 文件转录链路

```
音视频文件 → ffmpeg 提取音频 → AudioSegmenter 切片
  → queue_in → Recognizer 子进程
  → queue_out → FileTranscriber
  → SRT/TXT/JSON 输出
```
# CapsWriter-Offline External Integrations

> Generated: 2026-05-03 | Version: 2.4.19

## 1. External LLM API Integrations

All LLM providers are accessed through the OpenAI-compatible API using the `openai` Python SDK. The integration layer is in `util/llm/`.

### Architecture

```
LLM/role.py (config) --> RoleLoader --> RoleConfig --> ClientPool --> OpenAI SDK --> Provider API
```

Key files:
- `util/llm/llm_constants.py` -- Provider URLs, API keys, timeouts (class `APIConfig`)
- `util/llm/llm_client_pool.py` -- Client instance cache by provider+api_url (class `ClientPool`)
- `util/llm/llm_processor.py` -- Streaming API call execution (class `LLMProcessor`)
- `util/llm/llm_handler.py` -- Orchestrator: role detection, message building, output dispatch (class `LLMHandler`)
- `util/llm/llm_role_loader.py` -- Dynamic import of `.py` role files from `LLM/` directory (class `RoleLoader`)
- `util/llm/llm_role_config.py` -- Role configuration dataclass (`RoleConfig`)

### Supported Providers

| Provider | API Base URL | Auth Method | Timeout | Notes |
|----------|-------------|-------------|---------|-------|
| **Ollama** (local) | `http://localhost:11434/v1` | Dummy key `ollama` | 20s | Local LLM, supports `enable_thinking` |
| **OpenAI** | `https://api.openai.com/v1` | API key in `api_key` field | 10s | GPT-4, GPT-3.5, etc. |
| **DeepSeek** | `https://api.deepseek.com/v1` | API key in `api_key` field | 10s | DeepSeek-V3, DeepSeek-R1 |
| **Moonshot** | `https://api.moonshot.cn/v1` | API key in `api_key` field | 10s | Kimi (Kimi-K2, etc.) |
| **Zhipu (智谱)** | `https://open.bigmodel.cn/api/paas/v4` | API key in `api_key` field | 10s | GLM-4 series |
| **Volcengine (火山引擎)** | `https://ark.cn-beijing.volces.com/api/v3` | API key in `api_key` field | 10s | Doubao, DeepSeek on Volc |
| **Cerebras** | `https://api.cerebras.ai/v1` | API key in `api_key` field | 10s | Cerebras-GPT, Llama |
| **Claude** | User-configured | API key in `api_key` field | 10s | Anthropic Claude via compatible proxy |
| **Gemini** | User-configured | API key in `api_key` field | 10s | Google Gemini via compatible proxy |

### API Communication Details

- **Protocol**: OpenAI-compatible Chat Completions API (POST `/v1/chat/completions`)
- **Streaming**: SSE (Server-Sent Events) via `stream=True`
- **Client**: `openai.OpenAI(base_url=..., api_key=..., timeout=...)`
- **Caching**: `ClientPool` caches one `OpenAI` instance per unique `provider + api_url` combination
- **Error handling**: Wraps OpenAI SDK exceptions (`AuthenticationError`, `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `APIError`) into custom `APIException` hierarchy in `util/llm/llm_exceptions.py`
- **Stop mechanism**: User can interrupt generation via `llm_stop_key` (default: Esc), which calls `stream.close()`

### Role Configuration System

Each role is a `.py` file in the `LLM/` directory. Roles are dynamically imported and their module-level variables are mapped to `RoleConfig` dataclass fields.

Built-in roles:
- `LLM/default.py` -- Default polisher (润色): corrects ASR errors, removes filler words, programmer-oriented terminology
- `LLM/翻译.py` -- Translator: translates Chinese input to English, toast output
- `LLM/小助理.py` -- Assistant: answers questions, toast output

Role configuration fields (from `util/llm/llm_role_config.py`):
- `name`: Display name (empty = default role)
- `match`: Enable prefix matching (e.g., "翻译 hello" triggers translator role)
- `process`: Enable LLM processing (False = passthrough only)
- `provider`, `api_url`, `api_key`, `model`: API configuration
- `max_context_length`: Max tokens for conversation history
- `enable_thinking`: Ollama-only thinking mode
- `enable_history`: Retain conversation history across inputs
- `enable_hotwords`: Include hotword matches in LLM prompt
- `enable_rectify`: Include rectify records in LLM prompt
- `enable_read_selection`: Read selected text via Ctrl+C for context
- `output_mode`: `typing` (keyboard.write) or `toast` (floating window)
- `temperature`, `top_p`, `max_tokens`, `stop`: Generation parameters
- `system_prompt`: System prompt string
