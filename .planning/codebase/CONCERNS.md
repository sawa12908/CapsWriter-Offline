# CapsWriter-Offline 代码库关注点

**日期:** 2026-05-03
**版本:** 2.4.19
**范围:** ~26,500 行自有代码 + ~31,000 行 vendored GGUF 库

---

## 1. 技术债务

### 1.1 TODO / FIXME

**自有代码（2 处）：**
- `util/llm/llm_stop_monitor.py:72` — Toast 关闭逻辑未实现
- `util/zhconv/zhconv.py:252` — 字符转换查找缺少缓存

**Vendored GGUF 库（40+ 处）：** 全部在 `util/fun_asr_gguf/`，属于第三方代码。

### 1.2 废弃模块（6 个）

| 文件 | 状态 |
|------|------|
| `core_server.py` | process-merge 后废弃 |
| `util/protocol.py` | 被 `recognition_protocol.py` 替代 |
| `util/client/websocket_manager.py` | 被 RecognitionBridge + Queue 替代 |
| `util/server/server_ws_send.py` | 不再需要 |
| `util/server/server_ws_recv.py` | 不再需要 |
| `util/server/server_cosmic.py` | 被 `app_state.py` 替代 |

### 1.3 重复代码

- **Token 估算**：`util/llm/llm_constants.py:95-124` 和 `util/client/output/result_processor.py:31-37` 各有一份中英文字符计数逻辑
- **`import keyboard`**：5 个文件各自导入，与 `pynput` 功能重叠

### 1.4 半成品功能

- `util/concurrency/daemon_executor.py` — 本质是设计讨论文档，`SimpleDaemonExecutor` 每任务创建一个线程
- `util/llm/llm_stop_monitor.py:72` — Toast 关闭逻辑标记 TODO 未实现
- Recording indicator worker 崩溃自动重启无最大次数限制

---

## 2. 已知问题

### 2.1 近期高频修复区域（从 git log）

- **录音指示灯稳定性** — 3 次提交
- **音频设备同步** — 2 次提交
- **热词/标点稳定性** — 2 次提交
- **启动/重启流程** — 2 次提交

### 2.2 裸 except 捕获（8 处）

| 文件 | 行号 | 上下文 |
|------|------|--------|
| `util/common/lifecycle.py` | 188 | atexit 处理器 |
| `util/client/clipboard/clipboard.py` | 116 | 剪贴板操作 |
| `util/tools/window_detector.py` | 52 | 窗口检测 |
| `util/llm/llm_processor.py` | 188 | LLM 处理 |
| `util/server/server_init_recognizer.py` | 150 | queue_in.get() 超时 |
| `util/fun_asr_gguf/__init__.py` | 17 | 模块导入 |
| `util/fun_asr_gguf/nano_ctc.py` | 31 | CTC 解码 |
| `util/fun_asr_gguf/core/model_manager.py` | 156 | 模型管理 |

### 2.3 竞态条件风险

- **AppState 无锁多线程访问**：`recording`, `last_recognition_text`, `last_output_text`, `history` 被多线程无锁读写
- **asyncio 守护线程**：主线程退出时守护线程被强制终止，Recognizer 子进程可能孤儿
- **音频设备热插拔**：录音期间设备变化会导致截断音频

### 2.4 资源泄漏风险

- Recognizer 子进程 `daemon=False`，父进程崩溃时孤儿
- `os._exit(0)` 在 `lifecycle.py:125` 跳过所有清理
- Win32 GDI 对象在 recording indicator worker 被 kill 时泄漏
- ThreadPoolExecutor 关闭时 `wait=False`，运行中任务被丢弃
- 文件监控线程未在清理时显式停止

---

## 3. 安全关注点

### 3.1 API Key 存储

- API Key 直接写在 `LLM/*.py` Python 文件中
- 无环境变量或加密存储选项
- 可能被意外提交到版本控制

### 3.2 权限提升

- `core_client.py:487-501` — 非管理员时自动请求 UAC 提权，无用户提示
- `ensure_single_instance()` 在提权前运行，非管理员进程尝试 kill 管理员进程（静默失败）

### 3.3 UDP 广播

- 识别结果通过 UDP 广播到 `127.255.255.255:6017`
- 本地任何进程监听该端口可接收所有识别文本

---

## 4. 性能关注点

### 4.1 异步上下文中的阻塞调用

- `keyboard.write()` 在 `result_processor.py:285` 异步方法中直接调用（可阻塞数百毫秒）
- `time.sleep(0.05)` 在 `result_processor.py:298` 异步方法中阻塞事件循环
- `queue_in.put(timeout=0.5)` 在 asyncio 线程中阻塞最多 0.5 秒

### 4.2 内存

- 音频缓冲：60 秒 × 64,000 bytes/sec ≈ 3.84 MB（合理）
- LLM 历史：上限 50 条（合理）
- Vendored GGUF 库：~31,000 行代码全部加载，仅使用子集

### 4.3 多进程开销

- Recognizer 子进程：加载 ASR 模型消耗 1-4 GB RAM
- Recording indicator 子进程：额外 ~30-50 MB
- multiprocessing.Queue：每个音频块和识别结果都经过 pickle 序列化

---

## 5. 脆弱区域

### 5.1 强耦合点

- **AppState 全局单例**：持有几乎所有组件引用，任何组件可修改任何状态
- **`state._bridge`**：通过私有属性访问，分布在 `core_client.py`, `recorder.py`, `cleanup.py`

### 5.2 级联故障风险

**Recognizer 子进程崩溃链：**
1. 子进程崩溃 → `queue_out` 无响应
2. `_consume_loop()` 记录错误后重试
3. `queue_in.put()` 开始超时（每次 0.5s）
4. 录音继续但无结果返回
5. 用户看到"录音中"但永远得不到结果
6. UI 无错误提示

**音频设备热插拔链：**
1. `WM_DEVICECHANGE` 触发重开
2. 录音中的流被关闭
3. 录音以截断音频结束
4. 识别结果不完整或为空

### 5.3 关闭边缘情况

- `os._exit(0)` 在 `lifecycle.py:125`（双重 SIGINT）是最危险的路径：
  - 不执行 finally 块
  - 不调用 atexit 处理器
  - Recognizer 子进程孤儿
  - 麦克风可能保持锁定
  - 托盘图标残留
  - 未保存数据丢失

---

## 6. 建议优先级

### 严重（应尽快处理）

1. 替换 `os._exit(0)` 为优雅关闭
2. 为 AppState 多线程访问添加锁
3. 添加 Recognizer 子进程健康监控和自动重启
4. 录音期间阻止音频设备重开
5. Recording indicator worker 添加最大重启次数

### 高（应纳入计划）

6. 移除或隔离 6 个废弃模块
7. 合并重复的 token 估算代码
8. API Key 支持环境变量
9. 队列操作添加超时和错误上报
10. 修复裸 except 为具体异常类型

### 中（应跟踪）

11. 硬编码值迁移到配置
12. 文件监控线程添加清理
13. 文档化双线程架构和线程安全保证
14. 关闭流程添加集成测试
15. 替换或移除 `SimpleDaemonExecutor`

### 低（锦上添花）

16. 处理自有代码中的 TODO（非 vendored）
17. AppState 组件引用添加类型提示（当前为 `Any`）
18. 考虑 recording indicator 轻量化实现
19. 添加结构化日志（请求 ID 追踪音频任务）
