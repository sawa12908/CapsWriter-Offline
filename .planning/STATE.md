# Project State: CapsWriter-Offline

**Last updated:** 2026-05-03
**Current phase:** Phase 1 — 架构收尾 + 主窗口骨架
**Phase status:** Not started

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-03)

**Core value:** 快、准、稳、离线 — 用户按下快捷键说话，松开后即刻获得准确的识别结果
**Current focus:** Phase 1 — 清理技术债务 + 搭建主窗口框架

## Phase Progress

### Phase 1: 架构收尾 + 主窗口骨架

**Goal:** 清理 process-merge 遗留的技术债务，搭建 Tkinter 主窗口框架

| Requirement | Status | Notes |
|-------------|--------|-------|
| ARCH-01 — 移除 6 个废弃模块 | Pending | |
| ARCH-02 — 替换 os._exit(0) 为优雅关闭 | Pending | |
| ARCH-03 — AppState 线程安全 | Pending | |
| ARCH-04 — 替换 8 处裸 except | Pending | |
| ARCH-05 — Recognizer 子进程健康监控 | Pending | |
| UI-01 — 主窗口框架 | Pending | 已有 codestable/features/2026-05-01-main-window |
| UI-02 — 页面路由系统 | Pending | |
| UI-03 — 最小化到托盘 | Pending | |
| UI-04 — 托盘图标 + 右键菜单 | Pending | |
| UI-06 — Toast 通知（保留） | Pending | 已有功能，需确认主窗口集成 |
| UI-07 — 状态栏 | Pending | |
| IND-01 — 录音指示灯重启上限 | Pending | |
| IND-02 — 录音期间阻止设备重开 | Pending | |

### Phase 2: 功能面板

**Goal:** 识别历史 + 热词管理 + 角色管理面板

| Requirement | Status | Notes |
|-------------|--------|-------|
| UI-05 — ConsolePage 日志面板 | Pending | |
| HIST-01~04 — 识别历史面板 | Pending | |
| HOT-01~04 — 热词管理面板 | Pending | |
| ROLE-01~04 — 角色管理面板 | Pending | |

### Phase 3: 设置 + 统一打包

**Goal:** 图形化配置 + 单一 EXE

| Requirement | Status | Notes |
|-------------|--------|-------|
| SET-01~04 — 设置面板 | Pending | |
| BUILD-01~03 — 统一打包 | Pending | |

## Active Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| os._exit(0) 导致资源泄漏 | Critical | ARCH-02 |
| AppState 多线程无锁访问 | High | ARCH-03 |
| 8 处裸 except 捕获 | Medium | ARCH-04 |
| Recognizer 子进程孤儿 | High | ARCH-05 |
| Recording indicator 无限重启 | Medium | IND-01 |
| 音频设备热插拔截断录音 | Medium | IND-02 |

## Completed Items

- Process-Merge 核心架构（v2.4.19）
- Fun-ASR-Nano GGUF DML+Vulkan 加速
- 热词 RAG 两阶段检索
- LLM 多角色系统
- 单 EXE PyInstaller 打包（junction 部署）
- 暗色主题（VS Code Dark+）
- 系统托盘 + Toast
- 日记归档

---
*Last updated: 2026-05-03 after project initialization*
