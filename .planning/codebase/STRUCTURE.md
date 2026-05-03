# CapsWriter-Offline 目录结构

**日期:** 2026-05-03
**版本:** 2.4.19

---

## 根目录

```
CapsWriter-Offline/
├── core_client.py          # 客户端入口（源码运行）
├── core_server.py          # [废弃] 服务端入口
├── config_client.py        # 客户端配置
├── config_server.py        # 服务端配置
├── build.spec              # PyInstaller 打包配置（单 EXE）
├── build-client.spec       # 仅客户端打包
├── build_hook.py           # PyInstaller 运行时钩子
├── readme.md               # 项目说明
├── hot.txt                 # 热词库（音素匹配）
├── hot-server.txt          # 服务端热词（CTC 检索）
├── hot-rule.txt            # 规则替换（正则）
├── hot-rectify.txt         # 纠错历史
├── hot-shortcut.txt        # 快捷键热词
├── requirements-client.txt # 客户端依赖
├── requirements-server.txt # 服务端依赖
├── LLM/                    # LLM 角色配置
│   ├── __init__.py         # 角色模板与文档
│   ├── default.py          # 默认角色（润色）
│   ├── 翻译.py             # 翻译角色
│   ├── 高级翻译.py         # 高级翻译
│   ├── Python.py           # Python 编程助手
│   ├── 命令.py             # 命令执行
│   ├── 大助理.py           # 大助理
│   └── 小助理.py           # 小助理
├── models/                 # ASR 模型文件
│   ├── Fun-ASR-Nano/       # Fun-ASR-Nano GGUF 模型
│   ├── SenseVoice-Small/   # SenseVoice 模型
│   └── Paraformer/         # Paraformer 模型
├── assets/                 # 静态资源
│   └── icon.ico            # 应用图标
├── logs/                   # 日志输出
├── dist/                   # 打包输出
└── util/                   # 核心逻辑
```

## util/ 子目录

```
util/
├── __init__.py
├── app_state.py            # 全局状态单例（AppState）
├── audio_segmenter.py      # 音频切片工具
├── constants.py            # 全局常量
├── logger.py               # 日志系统
├── protocol.py             # [废弃] 旧协议定义
├── recognition_bridge.py   # Recognizer 子进程桥接层
├── recognition_protocol.py # 识别协议（AudioTask/RecognitionOutput）
│
├── client/                 # 客户端逻辑
│   ├── cleanup.py          # 客户端资源清理
│   ├── startup.py          # 客户端组件初始化
│   ├── audio/              # 音频采集
│   │   ├── stream.py       # AudioStreamManager（麦克风管理）
│   │   └── recorder.py     # AudioRecorder（录音与重采样）
│   ├── clipboard/          # 剪贴板操作
│   │   └── clipboard.py
│   ├── output/             # 结果输出
│   │   ├── result_processor.py  # ResultProcessor（识别结果处理）
│   │   └── text_output.py       # 文本输出（打字/粘贴）
│   ├── shortcut/           # 快捷键管理
│   │   ├── shortcut_manager.py  # ShortcutManager
│   │   └── task.py              # 快捷键任务调度
│   ├── transcribe/         # 文件转录
│   │   ├── file_transcriber.py  # FileTranscriber
│   │   └── srt_adjuster.py      # SRT 字幕调整
│   ├── udp/                # UDP 通信
│   │   └── udp_control.py       # UDP 录音控制
│   └── ui/                 # 客户端 UI 组件
│       ├── recording_indicator.py        # 录音指示灯（主进程）
│       ├── recording_indicator_worker.py # 录音指示灯（子进程）
│       ├── context_menu_handler.py       # 上下文菜单
│       ├── hotword_menu_handler.py       # 热词菜单
│       └── rectify_menu_handler.py       # 纠错菜单
│
├── server/                 # 服务端逻辑（在子进程中运行）
│   ├── cleanup.py          # 服务端资源清理
│   ├── server_init_recognizer.py  # Recognizer 初始化
│   ├── text_merge.py       # 文本拼接算法
│   ├── service.py          # [废弃] WebSocket 服务
│   ├── server_ws_send.py   # [废弃]
│   ├── server_ws_recv.py   # [废弃]
│   └── server_cosmic.py    # [废弃]
│
├── llm/                    # LLM 集成
│   ├── llm_handler.py      # LLMHandler（编排器）
│   ├── llm_processor.py    # LLMProcessor（流式 API 调用）
│   ├── llm_client_pool.py  # ClientPool（客户端缓存）
│   ├── llm_role_loader.py  # RoleLoader（角色动态加载）
│   ├── llm_role_config.py  # RoleConfig（角色配置 dataclass）
│   ├── llm_message_builder.py  # MessageBuilder（上下文组装）
│   ├── llm_role_detector.py    # RoleDetector（角色匹配）
│   ├── llm_constants.py    # API 配置常量
│   ├── llm_watcher.py      # LLM 角色文件监控
│   ├── llm_stop_monitor.py # LLM 中断监听
│   ├── llm_get_selection.py    # 获取选中文字
│   ├── llm_output_typing.py    # LLM 结果打字输出
│   └── llm_clipboard.py        # LLM 剪贴板操作
│
├── hotword/                # 热词系统
│   └── manager.py          # HotwordManager（RAG 检索与替换）
│
├── ui/                     # 通用 UI 组件
│   ├── main_window.py      # MainWindow（主窗口框架）
│   ├── page.py             # Page 基类
│   ├── console_page.py     # ConsolePage（控制台输出页面）
│   ├── tray_manager.py     # TrayManager（系统托盘）
│   ├── tray.py             # 托盘底层实现
│   ├── toast.py            # Toast 弹窗
│   ├── toast_base.py       # Toast 基类
│   ├── toast_constants.py  # Toast 常量
│   ├── toast_manager.py    # Toast 管理器
│   ├── dialogs.py          # 对话框工具
│   └── __init__.py
│
├── common/                 # 通用工具
│   └── lifecycle.py        # LifecycleManager（生命周期管理）
│
├── concurrency/            # 并发工具
│   └── daemon_executor.py  # SimpleDaemonExecutor
│
├── tools/                  # 系统工具
│   ├── windows_privilege.py    # Windows 管理员提权
│   ├── startup_manager.py      # 开机启动管理
│   └── window_detector.py      # 窗口检测
│
├── fun_asr_gguf/           # Fun-ASR-Nano GGUF 引擎（vendored）
│   ├── __init__.py
│   ├── nano_ctc.py         # CTC 热词检索
│   ├── display.py          # 进度显示
│   ├── convert_hf_to_gguf.py   # HF 模型转换（~11400 行）
│   ├── core/               # 核心引擎
│   │   └── model_manager.py
│   ├── gguf/               # GGUF 格式库
│   │   ├── constants.py
│   │   ├── gguf_reader.py
│   │   ├── gguf_writer.py
│   │   ├── lazy.py
│   │   ├── metadata.py
│   │   ├── tensor_mapping.py
│   │   ├── utility.py
│   │   └── vocab.py
│   └── hotword/            # 服务端热词
│       └── manager.py
│
├── zhconv/                 # 简繁转换
│   └── zhconv.py
│
└── debug/                  # 调试工具
```

## 代码规模

| 范围 | 行数（估算） |
|------|------------|
| 自有代码（排除 vendored） | ~26,500 |
| Vendored GGUF 库 | ~31,000 |
| 总计 | ~57,500 |
