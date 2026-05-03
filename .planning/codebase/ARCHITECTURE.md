# CapsWriter-Offline 架构

**日期:** 2026-05-03
**版本:** 2.4.19

---

## 1. 顶层架构

### Process-Merge 架构（v2.4+）

Server 逻辑已内嵌到 Client 进程中，通过 `multiprocessing.Process` 运行 Recognizer 子进程。

```
┌─────────────────────────────────────────────────────┐
│                  CapsWriter-Offline.exe              │
│                                                      │
│  ┌──────────────┐     ┌───────────────────────────┐ │
│  │ Tkinter 主线程 │     │ asyncio 守护线程            │ │
│  │  - 主窗口 UI   │     │  - 快捷键监听               │ │
│  │  - 系统托盘    │◄───►│  - 音频采集                 │ │
│  │  - 页面管理    │     │  - 识别结果处理             │ │
│  │              │     │  - LLM 润色                 │ │
│  └──────────────┘     └──────────┬────────────────┘ │
│                                   │                   │
│                          queue_in │ queue_out         │
│                                   │                   │
│                          ┌────────▼────────────────┐ │
│                          │ Recognizer 子进程         │ │
│                          │  - Sherpa-ONNX 引擎      │ │
│                          │  - Fun-ASR-Nano 模型     │ │
│                          │  - CTC 热词检索          │ │
│                          └─────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 关键设计决策

| 决策 | 理由 |
|------|------|
| Server 内嵌为子进程 | 消除 WebSocket 网络层开销，简化部署为单 EXE |
| asyncio 在守护线程 | Tkinter 必须占用主线程；asyncio 管理异步 I/O |
| multiprocessing.Queue | 子进程通信，绕过 GIL，支持 pickle 序列化 |
| AppState 全局单例 | 跨组件共享状态（录音/识别/历史），避免参数传递链 |

## 2. 模块分层

```
┌──────────────────────────────────────────┐
│              入口层 (Entry)               │
│  core_client.py  core_server.py (废弃)    │
├──────────────────────────────────────────┤
│              配置层 (Config)              │
│  config_client.py  config_server.py       │
├──────────────────────────────────────────┤
│              UI 层 (Presentation)         │
│  util/ui/  (main_window, tray, toast,    │
│             console_page, dialogs)        │
├──────────────────────────────────────────┤
│            业务逻辑层 (Business)          │
│  util/client/  (output, audio, shortcut,  │
│                 transcribe, clipboard)     │
│  util/llm/     (handler, processor,       │
│                 role_loader, client_pool)  │
│  util/hotword/ (manager, rag)             │
├──────────────────────────────────────────┤
│            桥接层 (Bridge)                │
│  util/recognition_bridge.py               │
│  util/recognition_protocol.py             │
├──────────────────────────────────────────┤
│            引擎层 (Engine)                │
│  util/server/  (server_init_recognizer,   │
│                 text_merge, cleanup)       │
│  util/fun_asr_gguf/  (nano_ctc, model)    │
├──────────────────────────────────────────┤
│            基础设施层 (Infra)              │
│  util/common/  (lifecycle)                │
│  util/logger.py  util/constants.py        │
│  util/tools/   (windows_privilege,        │
│                 startup_manager)           │
└──────────────────────────────────────────┘
```

## 3. 核心组件

### RecognitionBridge (`util/recognition_bridge.py`)

管理 Recognizer 子进程的完整生命周期：

- `start()` — 启动子进程，等待模型加载完成
- `submit_audio(task)` — 通过 `queue_in` 发送音频任务
- `on_result(callback)` — 注册结果回调
- `_consume_loop()` — 从 `queue_out` 消费识别结果
- `stop()` — 优雅关闭子进程（terminate → kill）

### AppState (`util/app_state.py`)

进程内全局单例，持有所有组件引用和状态：

- 录音状态：`recording`, `recording_has_audio`, `recording_start_time`
- 通信队列：`queue_in`, `queue_out`, `control_queue`
- 组件引用：`stream`, `shortcut_handler`, `stream_manager`, `processor`
- LLM 历史：`history: List[HistoryEntry]`（上限 50 条）
- 输出缓存：`last_recognition_text`, `last_output_text`

### ResultProcessor (`util/client/output/result_processor.py`)

识别结果处理管线：

1. 接收 `RecognitionOutput`（来自 RecognitionBridge 回调）
2. 热词替换（FastRAG + AccuRAG 两阶段）
3. 规则替换（`hot-rule.txt` 正则）
4. LLM 润色（可选，根据角色配置）
5. 输出（打字 / Toast / UDP）

### AudioStreamManager (`util/client/audio/stream.py`)

管理麦克风音频流：

- 按需打开/关闭（`keep_mic_stream_open` 配置）
- 噪声门限（RMS + Peak 阈值）
- 设备热插拔检测（`WM_DEVICECHANGE`）
- 音频回调 → `control_queue` → `AudioRecorder`

### LifecycleManager (`util/common/lifecycle.py`)

应用生命周期管理：

- 信号处理（SIGINT/SIGTERM）
- 关闭回调注册（`register_on_shutdown`）
- 优雅退出流程（`request_shutdown` → `wait_for_shutdown` → `cleanup`）
- 双重 SIGINT 强制退出（`os._exit(0)`）

## 4. 数据流

### 语音识别链路

```
麦克风 → sounddevice 回调 (48kHz float32)
  → AudioStreamManager._audio_callback()
  → 噪声门限过滤
  → control_queue.put(AudioChunk)
  → AudioRecorder.record_and_send()
  → 重采样 48kHz→16kHz
  → queue_in.put(AudioTask)
  → Recognizer 子进程
    → Sherpa-ONNX 识别
    → CTC 热词检索
  → queue_out.put(RecognitionOutput)
  → RecognitionBridge._consume_loop()
  → ResultProcessor._handle_result()
  → 热词替换 → LLM 润色 → 输出
```

### LLM 处理链路

```
ResultProcessor._handle_result()
  → LLMHandler.process()
  → RoleDetector.detect() — 前缀匹配角色
  → MessageBuilder.build() — 组装上下文
    → 热词列表 (enable_hotwords)
    → 纠错历史 (enable_rectify)
    → 选中文字 (enable_read_selection)
    → 对话历史 (enable_history)
    → 用户输入
  → LLMProcessor.stream() — 流式 API 调用
  → 输出 (typing/toast)
```

## 5. 线程模型

```
主线程 (Tkinter mainloop)
  ├── UI 事件处理
  ├── root.after() 回调（来自 asyncio 线程的 UI 更新）
  └── 托盘图标事件

asyncio 守护线程
  ├── 快捷键监听（pynput 回调线程 → run_coroutine_threadsafe）
  ├── 音频录制协程
  ├── 识别结果处理协程
  └── LLM 流式处理协程

pynput 回调线程
  ├── 键盘事件 → asyncio.run_coroutine_threadsafe()
  └── 鼠标事件 → asyncio.run_coroutine_threadsafe()

PortAudio 回调线程
  └── 音频帧 → control_queue.put()

Recognizer 子进程（主线程）
  └── Sherpa-ONNX 推理循环
```

## 6. 废弃模块

以下模块在 process-merge 后标记为 `[DEPRECATED]`：

| 文件 | 替代 |
|------|------|
| `core_server.py` | Recognizer 子进程内嵌 |
| `util/protocol.py` | `util/recognition_protocol.py` |
| `util/client/websocket_manager.py` | `RecognitionBridge` + Queue |
| `util/server/server_ws_send.py` | 不再需要 |
| `util/server/server_ws_recv.py` | 不再需要 |
| `util/server/server_cosmic.py` | `util/app_state.py` |
