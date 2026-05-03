# CapsWriter-Offline 测试现状

**日期:** 2026-05-03
**版本:** 2.4.19

---

## 测试概览

**当前状态：项目没有自动化测试。**

- 无 `tests/` 目录
- 无 `pytest` / `unittest` 配置
- 无 CI/CD 流水线
- `requirements-client.txt` 和 `requirements-server.txt` 中未包含测试框架

## 现有质量保障手段

### 日志系统

- 结构化日志输出到 `logs/client.log` 和 `logs/server.log`
- 可配置日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
- UI 模式下日志实时显示在 ConsolePage

### 手动测试

项目依赖开发者手动测试：
- 启动客户端，按下快捷键测试语音识别
- 拖入音视频文件测试转录功能
- 修改 LLM 角色文件测试热重载

### 错误处理

- 关键路径有 try/except + 日志记录
- 生命周期管理器确保资源清理
- 信号处理支持优雅退出

## 测试债务

### 高风险无测试区域

| 区域 | 风险 | 建议测试类型 |
|------|------|------------|
| 文本拼接算法 (`text_merge.py`) | 核心逻辑，影响识别准确率 | 单元测试 |
| 热词 RAG 检索 (`hotword/`) | 模糊匹配，边界情况多 | 单元测试 + 回归测试 |
| 音频重采样 (`recorder.py`) | 数值计算，采样率转换 | 单元测试 |
| RecognitionBridge 生命周期 | 子进程管理，资源泄漏风险 | 集成测试 |
| LLM 上下文组装 (`llm_message_builder.py`) | 多源数据拼接 | 单元测试 |
| 快捷键状态机 (`shortcut_manager.py`) | 并发，时序敏感 | 集成测试 |
| 关闭/重启流程 | 资源清理，孤儿进程风险 | 端到端测试 |

### 建议测试框架

| 用途 | 推荐 |
|------|------|
| 单元测试 | pytest |
| 异步测试 | pytest-asyncio |
| Mock | unittest.mock（标准库） |
| 覆盖率 | pytest-cov |

## 可测试性评估

### 有利因素

- 核心逻辑与 I/O 分离（`text_merge.py` 纯函数）
- dataclass 广泛使用，状态可序列化
- 配置与逻辑分离
- 日志系统完善，便于调试

### 不利因素

- AppState 全局单例，组件间强耦合
- 多线程/多进程架构，测试隔离困难
- 依赖硬件（麦克风、GPU）
- 依赖外部模型文件（数 GB）
- 部分逻辑与 UI 耦合
