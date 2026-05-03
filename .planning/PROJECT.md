# CapsWriter-Offline

## What This Is

CapsWriter-Offline 是一个面向 Windows 的**完全离线**语音输入工具。按住 CapsLock 说话，松开即上屏——支持语音听写、文件转录、热词替换、LLM 润色。全本地模型运行（ASR、标点、LLM），无需联网，保护隐私。

## Core Value

**快、准、稳、离线** — 用户按下快捷键说话，松开后即刻获得准确的识别结果。完全本地运行，数据不离机。

## Requirements

### Validated

- ✓ 语音听写：按住快捷键录音，松开上屏 — v2.4 已稳定
- ✓ 文件转录：拖入音视频文件生成字幕（.srt / .txt / .json） — v2.4
- ✓ Process-Merge 架构：Server 逻辑内嵌为子进程，消除 WebSocket 网络层 — v2.4.19
- ✓ 多 ASR 模型支持：Fun-ASR-Nano、SenseVoice-Small、Paraformer — v2.4
- ✓ DML + Vulkan GPU 加速推理 — v2.4
- ✓ 热词 RAG 音素匹配（两阶段：FastRAG + AccuRAG） — v2.2
- ✓ LLM 角色系统：润色、翻译、Python 助手等多角色 — v2.1
- ✓ 纠错历史检索 — v2.1
- ✓ 系统托盘 + Toast 弹窗 — v2.1
- ✓ UDP 广播识别结果 — v2.2
- ✓ 简体转繁体（zhconv） — v2.2
- ✓ 日记归档：按日期保存识别记录和录音 — v2.3
- ✓ 单 EXE 打包（PyInstaller，junction 部署） — v2.4.19
- ✓ 管理员 UAC 提权 — v2.4
- ✓ 暗色主题 UI（VS Code Dark+ 配色） — v2.4.19

### Active

- [ ] Process-Merge 收尾：清理 6 个废弃模块，合并配置
- [ ] 主窗口框架：导航栏 + 页面路由 + 状态栏（Tkinter）
- [ ] 识别历史面板：列表展示、搜索、复制、回听
- [ ] 热词管理面板：可视化编辑 hot.txt / hot-rule.txt
- [ ] 角色管理面板：切换/编辑 LLM 角色
- [ ] 设置面板：图形化配置
- [ ] 统一打包收尾：单一 build.spec
- [ ] 优雅关闭：替换 os._exit(0)
- [ ] AppState 多线程安全：添加锁或重构为线程安全

### Out of Scope

- 跨平台 UI — Windows 10+ 专属
- 移动端 / Web 端
- 模型下载管理器 — 用户手动下载
- 云端同步 / 多设备协作
- 插件系统
- 实时协作编辑

## Context

- **当前版本**: v2.4.19，约 26,500 行自有代码 + 31,000 行 vendored GGUF 库
- **架构**: Process-Merge 架构 — Tkinter 主线程 + asyncio 守护线程 + Recognizer 子进程
- **通信**: multiprocessing.Queue（主进程 ↔ Recognizer 子进程）
- **ASR 引擎**: Sherpa-ONNX，默认 Fun-ASR-Nano GGUF 模型
- **LLM 提供商**: Ollama（本地）、OpenAI、DeepSeek、Moonshot、Zhipu、Claude、Gemini
- **打包**: PyInstaller 6.0+，单 EXE + junction 增量部署
- **技术债务**: 6 个废弃模块、8 处裸 except、AppState 无锁多线程访问、os._exit(0) 风险
- **测试**: 无自动化测试，无 CI/CD
- **日志**: 结构化日志到 logs/，UI 模式重定向到 ConsolePage

## Constraints

- **平台**: Windows 10+ 专属，Python 3.12+
- **离线优先**: 核心功能（ASR、标点）必须完全本地运行，不依赖网络
- **性能**: 短音频延迟 < 200ms（GPU 加速），录音缓冲最长 60 秒
- **兼容性**: 保留 Fun-ASR-Nano GGUF 作为默认模型，需支持 DML + Vulkan
- **依赖**: conda 环境 `capswriter`，Tkinter 暗色主题，PyInstaller 单 EXE
- **安全**: API Key 不应硬编码在 Python 文件中（当前问题）
- **目标**: 将此项目整合为单个 EXE + 完整图形主窗口

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Process-Merge 架构（Server 内嵌为子进程） | 消除 WebSocket 开销，简化部署为单 EXE | ✓ Good |
| asyncio 在守护线程 | Tkinter 必须占用主线程 | ✓ Good |
| multiprocessing.Queue 进程间通信 | 绕过 GIL，支持 pickle 序列化 | ✓ Good |
| AppState 全局单例 | 跨组件共享状态，避免参数传递链 | ⚠️ Revisit — 多线程无锁风险 |
| Python 类作为配置文件（非 JSON/YAML） | 支持内联注释，热重载 | ✓ Good |
| os._exit(0) 双重 SIGINT 强制退出 | 资源清理完整性 vs 响应性 | ⚠️ Revisit — 应改为优雅关闭 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-03 after initialization*
