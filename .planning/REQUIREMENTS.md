# Requirements: CapsWriter-Offline

**Defined:** 2026-05-03
**Core Value:** 快、准、稳、离线 — 用户按下快捷键说话，松开后即刻获得准确的识别结果

## v1 Requirements

Requirements for the single-EXE integration with full UI. Built on top of validated capabilities.

### Architecture (ARCH)

- [ ] **ARCH-01**: Remove 6 deprecated modules from process-merge transition (core_server.py, util/protocol.py, util/client/websocket_manager.py, util/server/server_ws_send.py, util/server/server_ws_recv.py, util/server/server_cosmic.py)
- [ ] **ARCH-02**: Replace os._exit(0) double-SIGINT with graceful shutdown that cleans up Recognizer subprocess, microphone, tray icon
- [ ] **ARCH-03**: Add thread safety to AppState shared state (recording, last_recognition_text, last_output_text, history)
- [ ] **ARCH-04**: Replace 8 bare except clauses with specific exception types
- [ ] **ARCH-05**: Add Recognizer subprocess health monitoring and auto-restart with maximum restart limit

### UI (UI)

- [ ] **UI-01**: Main window with left navigation bar, right content area, and bottom status bar (Tkinter + ttk, VS Code Dark+ theme)
- [ ] **UI-02**: Page routing system — base Page class with on_enter/on_leave lifecycle, registered panels
- [ ] **UI-03**: Window minimize-to-tray behavior (close = hide to tray, exit from tray = true quit)
- [ ] **UI-04**: System tray icon with context menu (show window, start/stop recording, switch role, exit)
- [ ] **UI-05**: Console/log output page — display structured logs in real-time within the main window
- [ ] **UI-06**: Toast notification overlay for LLM results with markdown rendering (existing, preserved)
- [ ] **UI-07**: Status bar showing current role, recording state, model info

### Recognition History (HIST)

- [ ] **HIST-01**: History panel showing recognition results list (timestamp, raw text, processed text, role)
- [ ] **HIST-02**: Search/filter history entries by text content
- [ ] **HIST-03**: Click to copy text to clipboard, double-click to replay audio (if saved)
- [ ] **HIST-04**: History sourced from in-memory AppState cache + diary archive files

### Hotword Management (HOT)

- [ ] **HOT-01**: Hotword table panel — display, add, edit, delete entries in hot.txt with search
- [ ] **HOT-02**: Rule editor panel — visual editing of hot-rule.txt regex rules
- [ ] **HOT-03**: Rectify history panel — view hot-rectify.txt correction history
- [ ] **HOT-04**: Auto-trigger hot-reload on modification

### Role Management (ROLE)

- [ ] **ROLE-01**: Dropdown to switch current LLM role, showing role config (system prompt, model, output mode)
- [ ] **ROLE-02**: Visual editor for LLM role configs (LLM/*.py files)
- [ ] **ROLE-03**: Add/delete role capabilities
- [ ] **ROLE-04**: Auto-trigger hot-reload on modification

### Settings (SET)

- [ ] **SET-01**: Graphical form for all configuration options: shortcuts, thresholds, audio device, model selection, LLM provider, log level
- [ ] **SET-02**: Merge config_client.py and config_server.py into single AppConfig
- [ ] **SET-03**: ConfigManager with load/save/on_change, backward-compatible migration from old config files
- [ ] **SET-04**: Config changes write to file immediately

### Build & Packaging (BUILD)

- [ ] **BUILD-01**: Single build.spec producing one EXE (merge current build.spec + build-client.spec)
- [ ] **BUILD-02**: Single entry point — launch EXE, model loads, main window appears, ready to use
- [ ] **BUILD-03**: Junction-based incremental deployment preserved

### Recording Indicator (IND)

- [ ] **IND-01**: Recording indicator worker with maximum restart limit to prevent infinite restart loops
- [ ] **IND-02**: Prevent audio device reopen during active recording (WM_DEVICECHANGE handler)

## v2 Requirements

Deferred to future release.

- **HIST-05**: Audio waveform visualization in history panel
- **HOT-05**: Batch import hotwords from CSV/file
- **HOT-06**: Hotword effectiveness analytics (match rate, false positive rate)
- **ROLE-05**: Role template marketplace/presets
- **SET-05**: Profile system — save/load named configuration profiles
- **UI-08**: Customizable theme (light mode, custom accent colors)
- **BUILD-04**: Auto-updater for EXE

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cross-platform UI (macOS/Linux) | Windows 10+ only, Tkinter-specific |
| Mobile / Web client | Desktop-first tool |
| Model download manager | Users manually download models to models/ |
| Cloud sync / multi-device | Fully offline by design |
| Plugin system | Complexity not justified for v1 |
| Real-time collaboration | Offline tool, not collaborative |
| OAuth / SSO login | No user accounts needed |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 1 | Pending |
| ARCH-02 | Phase 1 | Pending |
| ARCH-03 | Phase 1 | Pending |
| ARCH-04 | Phase 1 | Pending |
| ARCH-05 | Phase 1 | Pending |
| UI-01 | Phase 1 | Pending |
| UI-02 | Phase 1 | Pending |
| UI-03 | Phase 1 | Pending |
| UI-04 | Phase 1 | Pending |
| UI-05 | Phase 2 | Pending |
| UI-06 | Phase 1 | Pending |
| UI-07 | Phase 1 | Pending |
| HIST-01 | Phase 2 | Pending |
| HIST-02 | Phase 2 | Pending |
| HIST-03 | Phase 2 | Pending |
| HIST-04 | Phase 2 | Pending |
| HOT-01 | Phase 2 | Pending |
| HOT-02 | Phase 2 | Pending |
| HOT-03 | Phase 2 | Pending |
| HOT-04 | Phase 2 | Pending |
| ROLE-01 | Phase 2 | Pending |
| ROLE-02 | Phase 2 | Pending |
| ROLE-03 | Phase 2 | Pending |
| ROLE-04 | Phase 2 | Pending |
| SET-01 | Phase 3 | Pending |
| SET-02 | Phase 3 | Pending |
| SET-03 | Phase 3 | Pending |
| SET-04 | Phase 3 | Pending |
| BUILD-01 | Phase 3 | Pending |
| BUILD-02 | Phase 3 | Pending |
| BUILD-03 | Phase 3 | Pending |
| IND-01 | Phase 1 | Pending |
| IND-02 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-03*
*Last updated: 2026-05-03 after initial definition*
