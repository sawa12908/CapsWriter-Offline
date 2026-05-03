# Roadmap: CapsWriter-Offline

**Project:** CapsWriter-Offline — 离线语音输入工具
**Core Value:** 快、准、稳、离线
**Created:** 2026-05-03
**Granularity:** Coarse

---

## Phases

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | 架构收尾 + 主窗口骨架 | 消除技术债务，搭建主窗口框架 | ARCH-01~05, UI-01~04, UI-06~07, IND-01~02 | 6 |
| 2 | 功能面板 | 识别历史、热词管理、角色管理面板 | UI-05, HIST-01~04, HOT-01~04, ROLE-01~04 | 5 |
| 3 | 设置 + 统一打包 | 图形化配置，单一 EXE 产出 | SET-01~04, BUILD-01~03 | 4 |

---

## Phase 1: 架构收尾 + 主窗口骨架

**Goal:** 清理 process-merge 遗留的技术债务，搭建 Tkinter 主窗口框架（导航栏 + 页面路由 + 状态栏 + 托盘），修复关键稳定性问题。做完后用户启动即可看到主窗口，按住 CapsLock 正常识别上屏。

**Requirements:** ARCH-01, ARCH-02, ARCH-03, ARCH-04, ARCH-05, UI-01, UI-02, UI-03, UI-04, UI-06, UI-07, IND-01, IND-02

**Success criteria:**
1. 6 个废弃模块已从代码库移除，无 import 引用残留
2. 应用收到关闭信号后，Recognizer 子进程、麦克风、托盘图标全部正确清理，无孤儿进程
3. AppState 的 recording / last_recognition_text / last_output_text / history 在多线程访问下无竞态条件
4. 启动应用后出现 Tkinter 主窗口，包含左侧导航栏、右侧内容区、底部状态栏
5. 关闭窗口时最小化到托盘而非退出，托盘右键菜单可退出应用
6. Recording indicator worker 崩溃后自动重启不超过 3 次，超过后优雅降级

**UI hint:** yes

---

## Phase 2: 功能面板

**Goal:** 在主窗口框架内实现三个核心面板：识别历史（列表、搜索、复制、回听）、热词管理（可视化编辑 hot.txt / hot-rule.txt / hot-rectify.txt）、角色管理（切换/编辑 LLM 角色）。同时完成 ConsolePage 集成（日志实时显示）。

**Requirements:** UI-05, HIST-01, HIST-02, HIST-03, HIST-04, HOT-01, HOT-02, HOT-03, HOT-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04

**Success criteria:**
1. 历史面板实时显示识别结果，支持文本搜索过滤
2. 点击历史条目可复制，有录音文件的条目可双击回听
3. 热词面板可增删改查 hot.txt 条目，修改后自动触发热重载
4. 角色面板可下拉切换当前 LLM 角色，可视化编辑角色配置并保存
5. ConsolePage 实时显示结构化日志，日志级别可切换

**UI hint:** yes

---

## Phase 3: 设置 + 统一打包

**Goal:** 图形化配置所有选项，合并双配置文件为单一 AppConfig，统一打包为单个 EXE。

**Requirements:** SET-01, SET-02, SET-03, SET-04, BUILD-01, BUILD-02, BUILD-03

**Success criteria:**
1. 设置面板表单覆盖所有 ClientConfig + ServerConfig 配置项
2. config_client.py 和 config_server.py 合并为单一配置，首次启动自动迁移旧配置
3. 配置修改即时保存并触发热重载
4. 单一 `build.spec` 产出单个 EXE，启动后自动加载模型、显示主窗口、进入就绪状态

**UI hint:** yes

---

## Dependency Graph

```
Phase 1 (架构收尾 + 主窗口骨架)
  ├── process-merge 收尾 (ARCH-01~05)
  ├── main-window 框架 (UI-01~04, UI-07)
  ├── Toast 保留 (UI-06)
  └── 稳定性修复 (IND-01~02)
       │
       ▼
Phase 2 (功能面板)
  ├── ConsolePage (UI-05)
  ├── History Panel (HIST-01~04)
  ├── Hotword Panel (HOT-01~04)
  └── Role Panel (ROLE-01~04)
       │
       ▼
Phase 3 (设置 + 统一打包)
  ├── Settings Panel (SET-01~04)
  └── Unified Build (BUILD-01~03)
```

## Parallel Opportunities

- **Phase 1 内部:** 架构收尾（ARCH-*）和主窗口框架（UI-*）可并行推进
- **Phase 2 内部:** 三个功能面板 + ConsolePage 可并行推进
- **Phase 3 内部:** 设置面板和统一打包有依赖（设置面板完成后再打包），但设置面板的开发可与 Phase 2 面板并行

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| AppState 加锁导致性能退化 | Medium | High | 优先使用 threading.Lock 细粒度锁，必要时重构为消息传递 |
| 优雅关闭改动用 os._exit(0) 风险高 | Low | High | 分步替换：先加清理回调 → 改信号处理 → 移除 os._exit(0) |
| Recognizer 子进程孤儿无感知 | Medium | Medium | 添加心跳检测 + 自动重启（上限 3 次） |
| 废弃模块移除引入 import 错误 | Low | Medium | grep 全仓库确认无引用后逐一移除 |
| Tkinter 主窗口性能（多个面板同时加载） | Low | Low | 懒加载面板，首次切换到页面时才创建 |

---
*Last updated: 2026-05-03 after roadmap creation*
