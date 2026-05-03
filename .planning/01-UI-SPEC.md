---
phase: 1
slug: architecture-cleanup-and-main-window
status: draft
shadcn_initialized: false
preset: none
created: 2026-05-03
---

# Phase 1 — UI Design Contract

> 架构收尾 + 主窗口骨架阶段的视觉和交互合同。

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (Tkinter + ttk 原生) |
| Preset | VS Code Dark+ (manual) |
| Component library | ttk (Tkinter 内置) |
| Icon library | 无（ICO 文件 `assets/icon.ico`） |
| Font | Microsoft YaHei UI 10pt（UI 标签），Consolas 10pt（代码/日志），楷体 23pt（Toast） |

**设计模式**：所有 ttk 组件通过 `ttk.Style` 自定义样式名（如 `"Secondary.TFrame"`），在应用启动时集中注册。无第三方 UI 库依赖。

---

## Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | 内联元素间距（StatusBar 分隔符） |
| sm | 8px | 紧凑元素间距（导航按钮 padding） |
| md | 12px | 默认内边距（页面内容 padding） |
| lg | 16px | 区块间距（NavBar logo padding-y） |
| xl | 24px | 布局间距（未使用） |
| 2xl | 32px | 主要区块分隔（未使用） |
| 3xl | 48px | 页面级间距（未使用） |

**约束**：
- NavBar 固定宽度：**200px**
- StatusBar 自然高度（单行文本，约 **26px**）
- 窗口默认尺寸：**900×650px**，最小 **600×400px**
- Toast 弹窗尺寸：**360px** 宽，高度自适应，最大 **450px**

Exceptions: Toast 弹窗使用独立间距系统（`padx=16, pady=10`），不跟随主窗口的 4px 倍数规则。

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 10pt | normal (400) | 1.4 |
| Label (UI) | 10pt | bold (700) | 1.3 |
| Nav button | 10pt | normal (400) | 1.3 |
| Nav logo | 14pt | bold (700) | 1.3 |
| Status bar | 9pt | normal (400) | 1.3 |
| Code / Log | 10pt | normal (400) | 1.5 (Consolas) |
| Toast | 23pt | normal (400) | 1.4 (楷体) |
| Toast title | 11pt | bold (700) | 1.3 (Microsoft YaHei UI) |

**字体回退链**：无。Tkinter 不支持 CSS font-family 回退。所有组件显式指定字体名。

---

## Color

建立的 VS Code Dark+ 调色板（已在代码中使用）：

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#1E1E1E` | 主窗口背景、内容区背景、页面背景 |
| Secondary (30%) | `#252526` | 导航栏、状态栏、侧边栏 |
| Accent (10%) | `#007ACC` | 选中状态（导航按钮 active、列表选中行） |
| Text Primary | `#CCCCCC` | 正文、标签 |
| Text Secondary | `#888888` | 状态栏信息、次要文字 |
| Text Highlight | `#FFFFFF` | Logo 文字、白色强调 |
| Success | `#6A9955` | 成功状态（日志 INFO 可在此色系） |
| Info | `#4EC9B0` | 信息状态（日志 DEBUG） |
| Warning | `#DCDCAA` | 警告（日志 WARNING） |
| Error | `#F44747` | 错误（日志 ERROR、破坏性操作） |
| Toast BG | `#2D2D30` | Toast 弹窗背景 |

Accent reserved for: 导航按钮选中态 background、ttk.Treeview selection。**非**用于所有可交互元素。

**约束**：
- 禁止引入第四种主要颜色（已有 Dominant / Secondary / Accent）
- 成功/信息/警告/错误仅用于状态指示，不做背景色
- Toast 背景使用 `#2D2D30`（介于 Dominant 和 Secondary 之间），不与其他区域共用

---

## 窗口组件树

```
MainWindow (Toplevel, 900×650, min 600×400)
├── PanedWindow (horizontal, orient)
│   ├── NavBar (ttk.Frame, width=200, style="Secondary.TFrame")
│   │   ├── Logo area (ttk.Frame, padx=12, pady=(16,8))
│   │   │   ├── "CapsWriter" (14pt bold, #FFFFFF)
│   │   │   └── "Offline" (10pt, #888888)
│   │   ├── Separator (horizontal, padx=12, pady=(0,8))
│   │   └── Nav buttons (text=page_title, style="Nav.TButton", anchor="w")
│   └── ContentArea (ttk.Frame)
│       └── Active Page (ttk.Frame, page_id + page_title)
└── StatusBar (ttk.Frame, style="Secondary.TFrame")
    ├── Role label (9pt, #888888, left)
    ├── Separator (vertical)
    ├── Status label (9pt, #888888, center-left)
    ├── Separator (vertical)
    └── Model label (9pt, #888888, right)
```

### 页面路由协议

```python
# 已在 util/ui/page.py 中实现
class Page(ttk.Frame):
    page_id: ClassVar[str]      # 唯一标识，如 "home", "history", "hotword"
    page_title: ClassVar[str]   # 导航栏显示文本，中文

    def on_enter(self) -> None: ...  # 切换到前台
    def on_leave(self) -> None: ...  # 切出到后台

# 已在 util/ui/main_window.py 中实现
class MainWindow:
    pages: Dict[str, Page]                # page_id → Page 实例
    def register_page(self, page) -> None: ...
    def navigate_to(self, page_id) -> None: ...
    def set_status(self, text) -> None: ...
```

**约束**：
- 页面注册在 `mainloop()` 之前一次性完成
- `on_enter` / `on_leave` 在主线程同步调用，**不可**做阻塞操作
- `navigate_to` 仅在用户点击导航按钮时调用，不在代码中自动切换
- 每次 `navigate_to` 保证 `old.on_leave()` → `new.on_enter()` 顺序

---

## 交互行为

### 窗口生命周期

| 动作 | 行为 |
|------|------|
| 程序启动 | 创建 MainWindow，显示窗口，注册页面 |
| 点击窗口 X（关闭） | 拦截 `WM_DELETE_WINDOW` → `withdraw()` 隐藏 → 不退出 |
| 双击托盘图标 | `deiconify()` 显示窗口 → `lift()` 置顶 |
| 托盘菜单"显示/隐藏" | 切换 `state()` / `withdraw()` |
| 托盘菜单"退出" | 触发 `lifecycle.request_shutdown()` → 优雅退出 |

### 导航交互

| 动作 | 行为 |
|------|------|
| 点击导航按钮 | 高亮当前按钮（`style="Nav.TButton.Active"`）→ 切换 ContentArea |
| 重复点击已选按钮 | 无操作（不做重新加载） |
| 首次加载页面 | 页面已在 register_page 时创建，首次 `on_enter` 时懒加载数据 |

### 状态栏更新

| 事件 | StatusBar 显示 |
|------|---------------|
| 空闲 | 状态: "空闲"，绿色指示 |
| 按住录音键 | 状态: "录音中..."，红色指示 |
| 识别进行中 | 状态: "识别中..."，黄色指示 |
| 模型加载中 | 模型: "模型加载中 N%" |
| 模型就绪 | 模型: "Fun-ASR-Nano (DML)" |
| 角色切换 | 角色: "翻译" |

### Toast 弹窗

| 事件 | 行为 |
|------|------|
| LLM 结果返回 | Toast 弹出（topmost，无边框，360×max450） |
| 用户点击 Toast | 激活编辑模式（现有功能，不变） |
| LLM 流式输出中 | Toast 实时更新 Markdown 渲染内容 |
| Toast 关闭 | 延迟 3 秒自动消失或用户主动关闭 |

---

## 注册的页面（Phase 1）

| page_id | page_title | 状态 | 说明 |
|---------|-----------|------|------|
| `home` | 首页 | ✓ 已实现 | 欢迎页 + 快速入门指引（util/ui/home_page.py） |
| `console` | 控制台 | ✓ 已实现 | 实时日志查看（util/ui/console_page.py） |

Phase 2 将注册：`history`（识别历史）、`hotword`（热词管理）、`role`（角色管理）
Phase 3 将注册：`settings`（设置）

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Window title | "CapsWriter Offline" |
| Nav logo primary | "CapsWriter" |
| Nav logo subtitle | "Offline" |
| Home page title | "首页" |
| Console page title | "控制台" |
| Status bar idle | "空闲" |
| Status bar recording | "录音中..." |
| Status bar recognizing | "识别中..." |
| Tray tooltip | "CapsWriter Offline" |
| Tray show/hide | "显示主窗口" / "隐藏主窗口" |
| Tray exit | "退出" |
| Empty state (home) | "欢迎使用 CapsWriter Offline" |
| Empty state body (home) | "按住 CapsLock 说话，松开即上屏" |
| Error state (model fail) | "模型加载失败 — 请检查 models/ 目录" |
| Destructive confirmation (exit) | "退出": "确定要退出 CapsWriter Offline 吗？录音中的内容将丢失。" |

**语言规则**：所有 UI 文案使用简体中文。技术术语（Fun-ASR-Nano、DML、LLM）保留英文。窗口标题保留英文 "CapsWriter Offline"（品牌名）。

---

## Registry Safety

无第三方 UI 组件注册。全部使用 Tkinter 标准库（`tkinter` + `ttk`）。无需安全门检查。

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| N/A (Tkinter stdlib) | tkinter, ttk | not required |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
