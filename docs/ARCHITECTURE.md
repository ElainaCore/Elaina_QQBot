# ElainaQQ 架构规范

本文档定义框架内部模块职责、依赖方向和文件分布。新增代码应先选择所属边界，再扩展现有模块；不要把协议转换、持久化、进程控制或 Web 逻辑继续堆入应用编排器。

## 1. 分层与依赖方向

依赖只允许从上层指向下层：

```text
main.py
  -> core.runtime.application       应用装配与生命周期
       -> core.runtime.*            运行时、扩展、内置 QQ
       -> core.plugins              插件加载与分发
       -> core.protocols            OneBot 模型与适配
       -> core.services             可复用服务
       -> core.transport            网络传输
       -> web                       Web 面板装配

core.transport -> core.protocols -> core.foundation
core.services  -> core.protocols / core.foundation
core.foundation                         不依赖上层模块
```

`core.runtime.application` 是唯一允许装配 Web 面板的核心模块。`core.transport` 只维护 HTTP、WebSocket 和关闭回调，不导入 Web 或运行时实现。`core.foundation` 不依赖协议、服务、插件、运行时或 Web。
插件公开接口、Hook、Web 工具和更新器通过装配层绑定或回调获得运行时能力，不允许反向导入应用入口充当服务定位器。

## 2. 目录职责

| 目录 | 职责 | 不应包含 |
| --- | --- | --- |
| `core/foundation` | 配置、品牌文本、日志基础设施、安全路径工具 | 业务协议、运行时、Web |
| `core/protocols` | OneBot 事件、消息、动作和连接契约 | 进程启动、页面路由 |
| `core/services` | 日志存储、事件记录、文件与配置监视 | 应用装配、QQ 进程控制 |
| `core/transport` | HTTP 与 WebSocket 传输 | Web 页面装配、插件逻辑 |
| `core/runtime` | 应用生命周期、扩展和内置 QQ | 插件公开 API 实现 |
| `core/native` | 随核心发布的进程注入原生资源 | Python 业务逻辑、Web 页面 |
| `core/plugins` | 插件上下文、装载、分发和稳定公开接口 | QQ 安装与底层传输实现 |
| `web` | 面板路由、认证和管理工具 | 核心事件模型实现 |

## 3. 内置 QQ 边界

`core/runtime/embedded/manager.py` 负责编排账号状态、桥接服务和 QQ 生命周期。平台级进程树终止、内存采样与页面回收位于 `process_control.py`；输出过滤与崩溃段识别位于 `output_filter.py`。
JavaScript 账号实现只负责 QQ 会话与协议适配；`manager_channel.mjs` 独立维护本机控制长轮询、顺序事件上报和 HTTP 连接池。

底层包能力按职责分布：

```text
core/runtime/embedded/
├── packet.py                       Python 原始包契约、PB 与响应解析
├── bridge/
│   ├── packet_resources.mjs       平台资源注册与偏移表缓存
│   ├── packet_runtime.mjs         发送和事件钩子的生命周期
│   ├── packet_backend.mjs         发送钩子适配
│   ├── packet_event_backend.mjs   事件钩子与监听器
│   └── qq_platform.mjs            QQ 路径、版本、加载器与数据目录适配
└── native/
    ├── packet/                    packet_sender.*.node、packet_offsets.json 和同目录依赖
    └── events/                    packet_events.*.node 与 event_offsets.json
```

原始包的参数、PB 和响应契约由 Python 管理；JavaScript 仅保留 QQNT 进程内会话调用。原生资源必须随框架发布并从上述内部目录加载。平台和路径解析只放在 `packet_resources.mjs`，偏移表在进程内按文件缓存，避免多账号重复读取与解析。
迁入的通用协议实现、原生模块、偏移表和内部运行时入口使用职责型名称，不附加产品品牌；框架名称只用于产品界面、公共配置、日志命名空间和兼容环境变量。
QQ 安装路径与版本识别集中在 `qq_platform.mjs`；主运行时只消费解析结果，不复制平台分支。

## 4. 数据与性能约束

- `EventDispatcher` 对同一会话串行、不同会话并行，并使用有界待处理队列。
- `EventLogRecorder` 负责展示转换、消息去重、面板推送和持久化；去重表有固定上限且使用常数时间更新。
- `ProcessMemoryMonitor` 缓存短时间内的进程树采样，面板轮询不会重复遍历全部子进程。
- 文件和数据库阻塞操作应通过线程执行；网络、插件和事件接口保持异步。
- 资源表、版本目录和平台映射应集中维护，不在多个后端复制。

## 5. 变更规则

1. 新业务逻辑先进入最小职责模块，应用编排器只组合组件。
2. 跨层能力通过回调、协议对象或服务接口注入，不从底层反向导入上层。
3. 平台差异放入专用模块，调用方只消费统一结果。
4. 迁移现有代码时保持公开 API 和持久化格式兼容，并补充回归测试。
5. 提交前运行 `python -m ruff check .`，并检查 Python 与 JavaScript 模块语法。
