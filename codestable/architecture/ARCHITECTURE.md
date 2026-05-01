---
doc_type: architecture
status: current
last_reviewed: 2026-05-01
version: "2.4.19"
---

# CapsWriter-Offline 架构总入口

## 1. 术语表

| 术语 | 定义 |
|---|---|
| **Server** | 主进程运行 WebSocket 服务，独立子进程运行 AI 模型推理（Sherpa-ONNX） |
| **Client** | 轻量进程，负责全局快捷键监听、麦克风录音采集、UI 展示、结果后处理 |
| **识别器子进程 (Recognizer)** | Server fork 出的独立子进程，运行语音模型，通过 multiprocessing 队列与 Server 主进程通信 |
| **热词 (Hotword)** | 基于音素的两阶段模糊检索，匹配 `hot.txt` 中的中英文词汇，修正识别结果 |
| **LLM 润色** | 根据 `LLM/` 目录下的角色配置，调用大语言模型对识别结果进行智能润色或回答 |
| **Toast** | Tkinter 无边框置顶弹窗，用于显示 LLM 输出（支持 Markdown 渲染） |
| **上屏** | 将最终识别结果通过模拟键盘输入或剪贴板粘贴到当前焦点应用 |
| **切片 (Segment)** | 将长音频按固定时长切分，带重叠区域，避免识别截断 |
| **RAG (Retrieval-Augmented Generation)** | 此处指基于音素向量的热词检索与替换，非传统 LLM RAG |

## 2. 定位与受众

CapsWriter-Offline 是一个**全离线**的语音识别输入工具。用户按住快捷键（默认 CapsLock）说话，松开后识别结果自动上屏。核心价值：**隐私保护**（全本地模型）、**低延迟**（流式识别）、**高准确率**（热词 + LLM 双重修正）。

**受众**：需要高效语音输入的开发者、写作者；需要离线隐私保护的敏感场景用户。

## 3. 结构与交互

### 3.1 进程拓扑

```
┌─────────────────────────────────────────────────────────┐
│                      Server 进程                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │   WebSocket 主循环     │  │   Recognizer 子进程       │ │
│  │   (asyncio)           │  │   (multiprocessing)      │ │
│  │   - ws_recv: 接收音频  │  │   - Sherpa-ONNX 模型     │ │
│  │   - ws_send: 推送结果  │  │   - Fun-ASR-Nano GGUF   │ │
│  │   - Cosmic: 全局状态   │  │   - Vulkan/DML GPU 加速  │ │
│  └──────────────────────┘  └──────────────────────────┘ │
│              ↕ multiprocessing.Queue                      │
└─────────────────────────────────────────────────────────┘
                        ↕ WebSocket (ws://127.0.0.1:6016)
┌─────────────────────────────────────────────────────────┐
│                      Client 进程                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ 快捷键监听 │ │ 音频采集  │ │ 结果处理  │ │ UI (托盘+   │ │
│  │ pynput   │ │sounddevice│ │ 热词+LLM │ │ Toast)     │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.2 识别全链路

```
用户按下 CapsLock
  → Client 开始录音 (sounddevice, 48kHz → 重采样 16kHz mono float32)
  → 超过 threshold (0.3s) 后开始流式发送音频块到 Server
  → Server ws_recv 接收 → 放入 Cosmic 队列 → Recognizer 子进程推理
  → 推理结果 (text + text_accu + tokens + timestamps) 通过 ws_send 推回 Client
  → 用户松开 CapsLock → Server 发送 is_final=True
  → Client ResultProcessor 后处理:
      1. 热词替换 (PhonemeCorrector: FastRAG → AccuRAG)
      2. 规则替换 (RuleCorrector: hot-rule.txt 正则)
      3. LLM 润色 (如果角色匹配)
      4. 上屏 (模拟键盘输入 / 剪贴板粘贴)
```

### 3.3 模块职责

**`util/client/` — 客户端工具**

| 子模块 | 职责 | 核心文件 |
|---|---|---|
| `audio/` | 麦克风录音、音频流管理、文件音频读取 | `stream.py`, `recorder.py`, `file_manager.py` |
| `shortcut/` | 快捷键配置、监听、事件分发 | `shortcut_manager.py`, `event_handler.py` |
| `output/` | 识别结果后处理、文本上屏 | `result_processor.py`, `text_output.py` |
| `transcribe/` | 文件转录（音视频 → srt/txt/json） | `file_transcriber.py`, `srt_adjuster.py` |
| `diary/` | 按日期归档识别结果和录音 | `diary_writer.py` |
| `clipboard/` | 剪贴板读写、粘贴恢复 | `clipboard.py` |
| `global_hotkey/` | 全局热键监听（pynput） | `global_hotkey.py` |
| `udp/` | UDP 广播输出、UDP 控制录音 | `udp_control.py` |
| `ui/` | 托盘图标、Toast 弹窗、录音指示灯 | `tray.py`, `toast.py`, `recording_indicator.py` |

**`util/server/` — 服务端工具**

| 子模块 | 职责 | 核心文件 |
|---|---|---|
| `server_ws_recv.py` | WebSocket 接收音频数据，入队 | — |
| `server_ws_send.py` | WebSocket 推送识别结果给客户端 | — |
| `server_cosmic.py` | 全局状态管理（连接池、消息队列） | — |
| `server_init_recognizer.py` | 识别器子进程初始化和主循环 | — |
| `server_recognize.py` | 语音识别处理逻辑 | — |
| `text_merge.py` | 文本拼接算法（模糊匹配 + Token 时间戳去重） | — |
| `service.py` | 识别器子进程管理（启动/停止） | — |

**`util/llm/` — LLM 处理**

| 子模块 | 职责 | 核心文件 |
|---|---|---|
| `llm_handler.py` | LLM 主处理器，编排整个 LLM 流程 | — |
| `llm_role_loader.py` | 从 `LLM/` 目录加载角色配置 | — |
| `llm_role_detector.py` | 根据识别结果前缀匹配角色 | — |
| `llm_context.py` | 上下文组装（热词、纠错、选中文字、历史） | — |
| `llm_message_builder.py` | 构建 LLM 请求消息 | — |
| `llm_client_pool.py` | LLM API 客户端连接池 | — |
| `llm_output_typing.py` | 打字输出模式 | — |
| `llm_output_toast.py` | Toast 弹窗输出模式 | — |
| `llm_watcher.py` | 文件监视器，热重载 `LLM/` 目录 | — |

**`util/hotword/` — 热词管理**

| 子模块 | 职责 | 核心文件 |
|---|---|---|
| `rag_fast.py` | FastRAG：倒排索引 + Numba JIT 快速粗筛 | — |
| `rag_accu.py` | AccuRAG：模糊音权重精确匹配 | — |
| `hot_phoneme.py` | 音素热词修正器 (PhonemeCorrector) | — |
| `hot_rule.py` | 规则替换修正器 (RuleCorrector) | — |
| `hot_rectification.py` | 纠错历史 RAG 检索 | — |
| `manager.py` | HotwordManager 单例，统一管理热词生命周期 | — |

### 3.4 关键数据流

**音频数据流**：`sounddevice callback → queue_in → WebSocket → Cosmic.task_queue → Recognizer`

**识别结果流**：`Recognizer → Cosmic.result_queue → ws_send → WebSocket → Client ResultProcessor`

**LLM 上下文流**：`识别文本 + 热词候选 + 纠错历史 + 选中文字 + 对话历史 → LLM API → 润色结果`

## 4. 数据与状态

### 4.1 通信协议 (`util/protocol.py`)

两个 dataclass 定义客户端与服务端之间的消息格式：

- **`AudioMessage`** (Client → Server)：`task_id`, `source` (mic/file), `data` (base64 音频), `is_final`, `time_start`, `seg_duration`, `seg_overlap`
- **`RecognitionResult`** (Server → Client)：`task_id`, `is_final`, `duration`, `text` (简单拼接), `text_accu` (时间戳去重), `tokens`, `timestamps`

### 4.2 配置系统

- **`config_client.py`** — `ClientConfig`：地址端口、快捷键、阈值、热词参数、LLM 开关、日志级别、音频分段参数、UDP 配置
- **`config_server.py`** — `ServerConfig`：地址端口、模型选择、格式化选项、日志级别；`ModelPaths`：模型文件路径；`FunASRNanoGGUFArgs`：GPU 加速、热词参数

配置文件位于项目根目录，支持用户直接修改。LLM 角色文件 (`LLM/*.py`) 和热词文件 (`hot*.txt`) 支持热重载。

### 4.3 全局状态

- **Server**: `Cosmic` 类管理连接池、任务队列、结果队列（`util/server/server_cosmic.py`）
- **Client**: `ClientState` 持有 WebSocket 连接、音频流、快捷键处理器、结果处理器等引用（`util/client/state.py`）
- **生命周期**: `Lifecycle` 统一管理退出信号、清理回调（`util/common/lifecycle.py`）

## 5. 关键架构决定

### 5.1 离线优先
全本地模型（ASR、标点、LLM），无网络依赖，保护隐私。模型文件存放于 `models/` 目录。

### 5.2 C/S 架构 + 推理子进程隔离
Server 主进程处理 WebSocket I/O，独立子进程运行 Sherpa-ONNX 模型推理。**原因**：CPU 密集型推理不阻塞 asyncio 事件循环，保证网络心跳和连接稳定性。

### 5.3 双重识别结果
同时计算 `text`（简单文本拼接，鲁棒）和 `text_accu`（Token 时间戳去重，精确）。`text` 用于热词替换和上屏，`text_accu` 用于字幕生成。

### 5.4 禁用 VAD，纯时间切片
不使用语音活动检测，仅基于固定时长（默认 60s）和重叠（4s）切片。**原因**：保留完整上下文，避免 VAD 误判切断连续语音。

### 5.5 两阶段热词检索
FastRAG（倒排索引 + Numba JIT 粗筛，减少 90% 计算量）→ AccuRAG（模糊音权重精确匹配）。双阈值：高阈值 (0.85) 用于替换，低阈值 (0.6) 用于 LLM 上下文参考。

### 5.6 配置化 + 热重载
`config*.py`、`hot*.txt`、`LLM/*.py` 位于根目录，用户可直接编辑。Client 启动文件监视器 (watchdog)，实时响应配置变更。

### 5.7 角色驱动的 LLM 润色
`LLM/` 目录下每个 `.py` 文件定义一个角色（名称、匹配前缀、System Prompt、模型、输出模式）。识别结果前缀匹配角色后，自动切换对应的 LLM 处理逻辑。

## 6. 代码锚点

| 概念 | 代码位置 |
|---|---|
| Server 入口 | `core_server.py:97` (`init()`) |
| Client 入口 (麦克风) | `core_client.py:183` (`init_mic()`) |
| Client 入口 (文件) | `core_client.py:207` (`init_file()`) |
| WebSocket 接收 | `util/server/server_ws_recv.py` |
| WebSocket 发送 | `util/server/server_ws_send.py` |
| 识别器子进程 | `util/server/server_init_recognizer.py` |
| 文本拼接算法 | `util/server/text_merge.py` |
| 通信协议定义 | `util/protocol.py` |
| 客户端配置 | `config_client.py` |
| 服务端配置 | `config_server.py` |
| 音频流管理 | `util/client/audio/stream.py` |
| 快捷键管理 | `util/client/shortcut/shortcut_manager.py` |
| 结果处理 | `util/client/output/result_processor.py` |
| 热词管理器 | `util/hotword/manager.py` |
| 音素修正器 | `util/hotword/hot_phoneme.py` |
| LLM 处理器 | `util/llm/llm_handler.py` |
| 角色加载器 | `util/llm/llm_role_loader.py` |
| 系统托盘 | `util/ui/tray.py` |
| Toast 弹窗 | `util/ui/toast.py` |
| 生命周期管理 | `util/common/lifecycle.py` |
| 打包配置 (Server+Client) | `build.spec` |
| 打包配置 (仅 Client) | `build-client.spec` |

## 7. 已知约束 / 边界情况

- **平台**：Windows 10+（MacOS 部分支持，需 sudo 启动）
- **GPU**：推荐 NVIDIA GPU（Vulkan 加速 GGUF 模型推理），也支持 DirectML
- **端口占用**：Server 绑定 `0.0.0.0:6016`，启动时检查端口可用性（`SO_EXCLUSIVEADDRUSE`），端口冲突直接报错退出
- **管理员权限**：Client 在管理员程序或游戏中热键可能失效，需以管理员身份运行
- **模型加载耗时**：Fun-ASR-Nano 模型加载约 10 秒（ONNX + GGUF + Vulkan），Client 需等待 Server 就绪后再连接
- **音频设备**：48kHz 采样率，设备不支持时自动降级；支持设备热插拔检测
- **单实例**：Server 和 Client 各通过 `ensure_single_instance()` 保证单实例运行
- **打包**：PyInstaller 6.0+，所有 Python 依赖放入 `internal/`，根目录保留配置文件、源码入口、模型文件夹

## 8. 相关文档

- `CLAUDE.md` — 项目开发指南（含架构细节、用户偏好）
- `codestable/reference/shared-conventions.md` — CodeStable 共享口径
- `LLM/__init__.py` — LLM 角色配置模板
- `config_client.py` / `config_server.py` — 完整配置项及注释
