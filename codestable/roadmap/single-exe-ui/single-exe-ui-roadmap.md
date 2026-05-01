---
doc_type: roadmap
slug: single-exe-ui
status: active
created: 2026-05-01
last_reviewed: 2026-05-01
tags: [packaging, ui, single-exe, desktop-app]
related_requirements: []
related_architecture: [ARCHITECTURE.md]
---

# 单 EXE 整合 + 图形界面

## 1. 背景

CapsWriter-Offline 当前是 Server + Client 双进程架构，分别打包为两个 exe。用户需要先启动 Server（等待模型加载约 10 秒），再启动 Client，操作繁琐。UI 层面只有系统托盘图标和 Toast 弹窗，没有主窗口——用户看不到识别历史、无法直观管理热词和角色、排查问题只能翻日志文件。

目标：将 Server 和 Client 整合为**单一 exe**，启动后自动完成模型加载和连接，同时提供**完整的图形主窗口**替代当前纯托盘+Toast 的交互方式。

## 2. 范围与明确不做

### 本 roadmap 覆盖

- 单进程整合：Server 逻辑和 Client 逻辑运行在同一进程内，去掉 WebSocket 网络通信
- 主窗口 UI：包含识别历史列表、热词管理、角色切换、设置面板
- 统一打包：PyInstaller 产出单个 exe
- 保留现有功能：听写、转录、热词、LLM 润色、托盘、Toast 全部保留

### 明确不做

- 跨平台 UI（保持 Windows 10+ 专属）
- 移动端 / Web 端
- 模型下载管理器（用户仍需手动下载模型到 `models/`）
- 云端同步 / 多设备协作
- 插件系统

## 3. 模块拆分（概设）

```
单 EXE 整合 + 图形界面
├── 模块 A · 进程整合层：消除 C/S 边界，Server 逻辑内嵌到 Client 进程
├── 模块 B · 主窗口框架：Tkinter 主窗口，含导航、页面路由、生命周期
├── 模块 C · 识别历史面板：展示历史识别结果，支持搜索、复制、回听
├── 模块 D · 热词管理面板：可视化编辑 hot.txt / hot-rule.txt / hot-rectify.txt
├── 模块 E · 角色管理面板：可视化切换和编辑 LLM 角色配置
├── 模块 F · 设置面板：图形化配置所有 ClientConfig / ServerConfig 选项
├── 模块 G · 统一打包：单一 build.spec，产出单个 exe
```

### 模块 A · 进程整合层

- **职责**：将当前 Server 进程的 WebSocket 服务 + Recognizer 子进程管理，内嵌到 Client 进程中。去掉 `websockets` 网络通信，改为进程内队列/回调。Recognizer 子进程保持独立（CPU 密集型推理仍需隔离）。
- **承载的子 feature**：`process-merge`
- **触碰的现有代码/模块**：`core_server.py`、`core_client.py`、`util/server/server_ws_recv.py`、`util/server/server_ws_send.py`、`util/server/server_cosmic.py`、`util/protocol.py`

### 模块 B · 主窗口框架

- **职责**：提供 Tkinter 主窗口（替代纯托盘模式），包含左侧导航栏、右侧内容区、底部状态栏。管理窗口显示/隐藏/最小化到托盘。窗口关闭时最小化到托盘而非退出。
- **承载的子 feature**：`main-window`
- **触碰的现有代码/模块**：`util/ui/tray.py`、`util/ui/toast.py`（保留，主窗口作为新入口）

### 模块 C · 识别历史面板

- **职责**：实时展示识别结果列表（时间、原文、润色后文本），支持搜索过滤、点击复制、双击回听录音（如果保存了音频）。数据来源：内存中的识别结果缓存 + 已有的日记归档文件。
- **承载的子 feature**：`history-panel`
- **触碰的现有代码/模块**：`util/client/diary/diary_writer.py`、`util/client/output/result_processor.py`

### 模块 D · 热词管理面板

- **职责**：表格形式展示 `hot.txt` 热词列表，支持增删改、搜索、批量导入。规则面板编辑 `hot-rule.txt` 正则规则。纠错面板查看 `hot-rectify.txt` 历史。修改后自动触发热重载。
- **承载的子 feature**：`hotword-panel`
- **触碰的现有代码/模块**：`util/hotword/manager.py`、`hot.txt`、`hot-rule.txt`、`hot-rectify.txt`

### 模块 E · 角色管理面板

- **职责**：下拉切换当前 LLM 角色，展示角色配置（System Prompt、模型、输出模式等），支持可视化编辑并保存到 `LLM/*.py`。新增/删除角色。
- **承载的子 feature**：`role-panel`
- **触碰的现有代码/模块**：`util/llm/llm_role_loader.py`、`util/llm/llm_role_detector.py`、`LLM/` 目录

### 模块 F · 设置面板

- **职责**：图形化表单编辑所有配置项（快捷键、阈值、音频设备、模型选择、LLM 提供商、日志级别等），保存到 `config_client.py` / `config_server.py`。合并后只需一份配置文件。
- **承载的子 feature**：`settings-panel`
- **触碰的现有代码/模块**：`config_client.py`、`config_server.py`

### 模块 G · 统一打包

- **职责**：合并 `build.spec` 和 `build-client.spec` 为单一 `build.spec`，产出单个 exe。处理依赖合并、入口统一、资源收集。
- **承载的子 feature**：`unified-build`
- **触碰的现有代码/模块**：`build.spec`、`build-client.spec`、`start_server.py`、`start_client.py`

## 4. 模块间接口契约 / 共享协议（架构层详设）

### 4.1 进程内识别接口（替代 WebSocket 协议）

**方向**：Client 层 → Recognizer 子进程
**形式**：multiprocessing.Queue（保留现有 Cosmic 队列机制，去掉 WebSocket 中间层）

**契约**：

```python
# 替代 util/protocol.py 的 AudioMessage 和 RecognitionResult
# 进程内直接传 dataclass 实例，不再序列化 JSON

# 音频输入（替代 AudioMessage + WebSocket send）
class AudioTask:
    task_id: str
    source: Literal['mic', 'file']
    data: bytes                    # 原始 float32 音频字节，不再 base64 编码
    is_final: bool
    time_start: float
    seg_duration: float = 60.0
    seg_overlap: float = 4.0

# 识别输出（替代 RecognitionResult + WebSocket receive）
class RecognitionOutput:
    task_id: str
    is_final: bool
    duration: float
    time_start: float
    time_submit: float
    time_complete: float
    text: str
    text_accu: str = ''
    tokens: List[str] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)

# 通信接口
class RecognitionBridge:
    """替代 WebSocket 的进程内识别桥接"""
    def submit_audio(self, task: AudioTask) -> None: ...
    def on_result(self, callback: Callable[[RecognitionOutput], None]) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

**约束**：
- `submit_audio` 非阻塞，音频入队后立即返回
- `on_result` 回调在 asyncio 事件循环线程中调用
- Recognizer 子进程仍独立运行，通过 `multiprocessing.Queue` 通信
- 去掉 `AudioMessage.data` 的 base64 编解码（进程内传原始字节）

### 4.2 主窗口页面接口

**方向**：主窗口框架 → 各功能面板
**形式**：Tkinter Frame 嵌入

**契约**：

```python
class Page(ttk.Frame):
    """所有功能面板的基类"""
    page_id: str          # 唯一标识，如 'history', 'hotword', 'role', 'settings'
    page_title: str       # 导航栏显示名称

    def on_enter(self) -> None: ...
    """页面被切换到前台时调用，用于刷新数据"""

    def on_leave(self) -> None: ...
    """页面被切走时调用，用于保存状态"""

class MainWindow:
    """主窗口，管理页面路由"""
    def register_page(self, page: Page) -> None: ...
    def navigate_to(self, page_id: str) -> None: ...
    def show_toast(self, title: str, message: str, duration: int = 3000) -> None: ...
    def set_status(self, text: str) -> None: ...
    # 底部状态栏：显示当前角色、识别状态、模型信息
```

**约束**：
- 页面注册在窗口创建时一次性完成
- `on_enter` / `on_leave` 在主线程同步调用，不做耗时操作
- 主窗口关闭 → 最小化到托盘，托盘退出 → 真正退出进程

### 4.3 配置统一接口

**方向**：合并 `config_client.py` + `config_server.py` → 单一 `config.py`
**形式**：Python 类 + JSON 持久化

**契约**：

```python
# 合并后的配置结构
class AppConfig:
    # 通用
    version: str = '3.0.0'
    log_level: str = 'INFO'

    # 服务端（原 ServerConfig）
    model_type: str = 'fun_asr_nano'
    format_num: bool = True
    format_spell: bool = True

    # 客户端（原 ClientConfig）
    shortcuts: List[dict] = [...]   # 快捷键配置
    threshold: float = 0.3
    hot_enabled: bool = True
    hot_thresh: float = 0.85
    hot_similar: float = 0.6
    llm_enabled: bool = True
    # ... 其余字段

class ConfigManager:
    """配置读写单例，替代直接 import config.py"""
    def load(self) -> AppConfig: ...
    def save(self, config: AppConfig) -> None: ...
    def on_change(self, callback: Callable[[AppConfig], None]) -> None: ...
```

**约束**：
- 配置变更立即写入文件，同时触发 `on_change` 回调
- 热词文件和 LLM 角色文件保持独立文件，不合并到配置
- 向后兼容：首次启动从旧 `config_client.py` / `config_server.py` 迁移

### 4.4 共享状态

```python
class AppState:
    """单例，替代 ClientState + Cosmic 的全局状态"""
    # 识别状态
    is_recording: bool = False
    is_recognizing: bool = False
    current_role: str = 'default'

    # 识别结果缓存（供历史面板消费）
    history: List[HistoryEntry] = field(default_factory=list)
    max_history: int = 500

    # 模型状态
    model_loaded: bool = False
    model_load_progress: float = 0.0   # 0.0 ~ 1.0

class HistoryEntry:
    timestamp: datetime
    raw_text: str
    processed_text: str
    role: str
    audio_path: Optional[str]  # 录音文件路径（如果有）
```

### 4.5 无跨模块接口的模块

模块 C（识别历史面板）、D（热词管理面板）、E（角色管理面板）、F（设置面板）之间无直接交互，各自通过 `AppState` 和 `ConfigManager` 读写共享状态，不定义额外跨模块接口。

## 5. 子 feature 清单

1. **process-merge** — 消除 C/S 边界：将 Server 的 WebSocket 服务 + Recognizer 子进程管理内嵌到 Client 进程，用进程内队列替代网络通信
   - 所属模块：模块 A
   - 依赖：无
   - 状态：in-progress
   - 对应 feature：2026-05-01-process-merge
   - 备注：这是整个 roadmap 的前置基础，后续所有 feature 都依赖它

2. **main-window** — 创建 Tkinter 主窗口框架：导航栏 + 页面路由 + 状态栏 + 最小化到托盘
   - 所属模块：模块 B
   - 依赖：无（可与 process-merge 并行）
   - 状态：in-progress
   - 对应 feature：2026-05-01-main-window

3. **history-panel** — 识别历史面板：实时展示识别结果列表，支持搜索、复制、回听
   - 所属模块：模块 C
   - 依赖：`process-merge`（需要进程整合后的 AppState 提供历史数据）
   - 状态：planned
   - 对应 feature：未启动

4. **hotword-panel** — 热词管理面板：可视化编辑 hot.txt / hot-rule.txt / hot-rectify.txt
   - 所属模块：模块 D
   - 依赖：`main-window`（需要主窗口框架提供页面容器）
   - 状态：planned
   - 对应 feature：未启动

5. **role-panel** — 角色管理面板：可视化切换和编辑 LLM 角色配置
   - 所属模块：模块 E
   - 依赖：`main-window`
   - 状态：planned
   - 对应 feature：未启动

6. **settings-panel** — 设置面板：图形化配置所有选项，合并 config_client.py + config_server.py
   - 所属模块：模块 F
   - 依赖：`main-window`、`process-merge`（需要统一的配置模型）
   - 状态：planned
   - 对应 feature：未启动

7. **unified-build** — 统一打包：合并 build.spec，产出单一 exe，处理入口统一和资源收集
   - 所属模块：模块 G
   - 依赖：`process-merge`、`main-window`（需要整合后的代码和主窗口就绪）
   - 状态：planned
   - 对应 feature：未启动

**最小闭环**：第 1 条 `process-merge` + 第 2 条 `main-window` 做完后，用户启动单一进程即可看到主窗口，按住 CapsLock 说话能正常识别上屏——端到端最窄路径跑通。

## 6. 排期思路

**为什么这样拆**：按依赖关系分层——先消除架构障碍（process-merge），再搭 UI 骨架（main-window），然后逐个填充功能面板，最后统一打包。

**最小闭环选 process-merge + main-window**：这两条做完，用户就能"启动一个 exe → 看到窗口 → 正常识别"，核心价值已交付。后续面板是锦上添花。

**并行空间**：process-merge 和 main-window 无相互依赖，可并行开发。四个功能面板（history/hotword/role/settings）依赖 main-window 完成后可并行推进。

**卡点**：process-merge 风险最高——去掉 WebSocket 层涉及 Server 端核心通信逻辑的重写，需要仔细处理 Recognizer 子进程的生命周期和错误恢复。

## 7. 观察项

- `CLAUDE.md` 中的架构描述（C/S 架构、WebSocket 通信）在 process-merge 完成后会过时，需同步更新
- `codestable/architecture/ARCHITECTURE.md` 第 3.1 节进程拓扑图、第 5.2 节 C/S 架构决定在整合后需更新
- 当前 `util/protocol.py` 的 `AudioMessage` / `RecognitionResult` 在去掉 WebSocket 后是否需要保留（转录模式可能仍需文件→Server 的协议）待 process-merge 设计时决定
- 主窗口技术选型：当前 UI 基于 Tkinter（托盘、Toast），主窗口是否继续 Tkinter 还是换其他框架（如 PyQt/PySide、wxPython）需在 main-window feature 中决定。Tkinter 优势是零依赖、已在使用；劣势是原生外观较差
