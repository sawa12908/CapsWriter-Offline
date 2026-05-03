# CapsWriter-Offline 编码规范

**日期:** 2026-05-03
**版本:** 2.4.19

---

## 文件组织

### 编码声明

所有 Python 文件以 `# coding: utf-8` 开头。

### 导入顺序

1. `from __future__ import annotations`（46 个文件使用）
2. 标准库
3. 第三方库
4. 项目内部模块

### 类型注解

- 使用 `from __future__ import annotations` 延迟求值
- `TYPE_CHECKING` 守卫避免循环导入
- `@dataclass` 广泛使用（30+ 处）

## 命名约定

| 类型 | 风格 | 示例 |
|------|------|------|
| 文件名 | snake_case | `result_processor.py`, `app_state.py` |
| 类名 | PascalCase | `AppState`, `RecognitionBridge`, `ResultProcessor` |
| 函数/方法 | snake_case | `start_recording()`, `get_state()` |
| 变量 | snake_case | `audio_buffer`, `last_output_text` |
| 常量 | UPPER_SNAKE_CASE | `SAMPLE_RATE`, `MAX_LINES` |
| 私有成员 | _leading_underscore | `_bridge`, `_consume_loop()` |
| 模块级私有 | __all__ | 未广泛使用 |

## 配置模式

配置使用 Python 类而非 JSON/YAML：

```python
class ClientConfig:
    addr = '127.0.0.1'
    port = '6016'
    shortcuts = [{...}]
    threshold = 0.3
```

- 类属性即配置项
- 支持内联注释说明
- 热重载：修改文件后 watchdog 检测变化自动重载

## 错误处理

### 模式

```python
try:
    some_operation()
except SpecificError as e:
    logger.error(f"操作失败: {e}", exc_info=True)
```

### 反模式（存在但应避免）

- `except:` 裸异常捕获（约 8 处）
- `except Exception: pass` 静默吞异常

## 异步模式

### asyncio + 多线程

```python
# 从其他线程调度协程
asyncio.run_coroutine_threadsafe(coro, loop)

# 在线程池中运行阻塞操作
await asyncio.to_thread(blocking_func, arg)

# 从 asyncio 线程更新 UI
root.after(0, ui_callback, *args)
```

### 子进程通信

```python
# multiprocessing.Queue 用于进程间通信
queue_in = Queue()   # 主进程 → 子进程
queue_out = Queue()  # 子进程 → 主进程
```

## UI 约定

### 框架

- Tkinter + ttk 作为 UI 框架
- 暗色主题（VS Code Dark+ 配色）
- 页面模式：`Page` 基类 → 具体页面（`ConsolePage`）

### 配色方案

| 元素 | 颜色 |
|------|------|
| 背景 | `#1E1E1E` |
| 前景/文字 | `#CCCCCC` |
| 选择背景 | `#007ACC` |
| 绿色（成功） | `#6A9955` |
| 青色（信息） | `#4EC9B0` |
| 黄色（警告） | `#DCDCAA` / `#FFB900` |
| 红色（错误） | `#F44747` / `#E81123` |
| 品红 | `#C586C0` |

### 字体

- 代码/日志：`Consolas`, 10pt
- UI 标签：`Microsoft YaHei UI`, 10pt bold
- Toast：`楷体`, 23pt

## 日志

```python
from util.logger import setup_logger
logger = setup_logger('client', level=Config.log_level)

# 使用
logger.info("message")
logger.debug("detail")
logger.error("error", exc_info=True)
```

- 日志级别通过 `config_client.py` / `config_server.py` 配置
- 输出到 `logs/client.log` 和 `logs/server.log`
- UI 模式下重定向到 ConsolePage

## 注释

- 注释和文档字符串使用中文
- 模块级 docstring 描述模块用途
- 函数/方法级 docstring 简洁描述参数和返回值
- 废弃模块标注 `[DEPRECATED]`

## 单例模式

```python
_global_state: Optional[AppState] = None

def get_state() -> AppState:
    global _global_state
    if _global_state is None:
        _global_state = AppState()
    return _global_state
```

## 数据类

```python
@dataclass
class HistoryEntry:
    text: str
    llm_result: Optional[str] = None
    role_name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
```

## 生命周期管理

```python
from util.common.lifecycle import lifecycle

# 注册清理回调
lifecycle.register_on_shutdown(cleanup_func)

# 请求关闭
lifecycle.request_shutdown(reason="User Exit")

# 等待关闭信号
await lifecycle.wait_for_shutdown()

# 执行清理
lifecycle.cleanup()
```
