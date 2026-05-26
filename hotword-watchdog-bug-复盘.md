# "护盘"热词删不掉问题复盘

日期: 2026-05-26

## 现象

用户多次尝试从热词表中删除 "护盘" 和 "复牌"，但识别 "复盘" 时始终被替换为 "护盘"：

```
识别结果：复盘
热词替换：护盘
完全匹配：复盘->护盘
潜在热词：复盘->复牌(0.83), 复盘->午盘(0.75)
```

## 排查过程

### 第一层：以为是没改对文件

最初只修改了根目录的 `hot.txt` 和 `hot-server.txt`，但程序通过 EXE 启动，工作目录是 `dist/CapsWriter-Offline/`，读的是 dist 下的副本。修改未生效。

### 第二层：同步了 dist 文件仍然不生效

用 `cp` 将根目录文件同步到 `dist/CapsWriter-Offline/`，但日志仍显示 "护盘"。检查发现只触发了 `hot-rectify.txt` 的热重载，`hot.txt` 从未被重载。

### 第三层：定位到 watchdog bug

查看 `util/hotword/manager.py` 的 `_HotwordFileHandler` 类，发现致命缺陷：

```python
# 旧代码 (有 bug)
def on_modified(self, event):
    with self._lock:
        self._last_event = (filename, current_time)  # 只存一个事件！
        ...

def _debounced_worker(self):
    filename, event_time = self._last_event  # 只处理最后一个
    handler = self._file_mapping.get(filename)
    handler()
```

**根因**: `_last_event` 是单个变量，多个文件同时变化时，后一个事件覆盖前一个。`cp` 三个文件的瞬间只有最后一个 `hot-rectify.txt` 被处理，`hot.txt` 和 `hot-server.txt` 的事件丢失。

## 修复方案

将 `_last_event` 从单个元组改为 `_pending_events: Dict[str, float]` 字典，累积所有文件变更，防抖后批量处理：

```python
# 新代码 (已修复)
def _debounced_worker(self):
    while True:
        time.sleep(self._debounce_delay)
        with self._lock:
            now = time.time()
            ready = [f for f, t in self._pending_events.items()
                     if now - t >= self._debounce_delay]
            for f in ready:
                del self._pending_events[f]

        for filename in ready:
            handler = self._file_mapping.get(filename)
            if handler:
                handler()
        break
```

## 关键文件

| 文件 | 作用 | 变更 |
|------|------|------|
| `util/hotword/manager.py` | 客户端热词管理器 + watchdog | 修复多文件事件丢失 bug |
| `hot.txt` | 客户端强制热词表 | 删除护盘/复牌，新增复盘等词 |
| `hot-server.txt` | 服务端 CTC 热词上下文 | 删除护盘/复牌 |
| `hot-rectify.txt` | LLM 纠错历史 | 新增中端→终端、ND文件→MD文件 |

## 教训

- watchdog 防抖逻辑中，如果监控多个文件，必须用集合/字典累积事件，不能只存最后一个
- dist 目录存在副本文件，修改热词时需要确认程序实际读取的路径
- 日志是排查问题的唯一入口——通过日志发现只有 `hot-rectify.txt` 被重载，从而定位到 bug
