# ElainaQQ 内置 QQ 桥接开发文档

本目录包含 ElainaQQ 内置 QQ 运行时的 JavaScript 桥接层。它由 `EmbeddedQQManager` 启动，用于在独立 QQNT 进程与 Python 框架之间传递事件、OneBot 动作、运行状态和控制结果。

> 这里描述的是框架内部协议，不是插件稳定 API，也不是可公开访问的 OneBot 服务。插件应使用 `core.plugins`、事件对象和 `get_api()`，不要直接连接桥接端口或导入桥接实现。

## 目录

- [1. 组件](#1-组件)
- [2. 启动与隔离](#2-启动与隔离)
- [3. 通信流程](#3-通信流程)
- [4. 事件与消息边界](#4-事件与消息边界)
- [5. 红包事件](#5-红包事件)
- [6. 修改要求](#6-修改要求)

---

## 1. 组件

| 文件 | 职责 |
| --- | --- |
| `qq_runtime.mjs` | 运行时入口，加载 QQNT 包装器、维护账号会话并与 Python 管理器通信 |
| `onebot_action_contract.mjs` | OneBot 动作契约与动作名称处理 |
| `onebot_message.mjs` | 消息段转换与消息发送辅助 |
| `inline_keyboard.mjs` | QQNT 内联键盘元素与官方机器人回调参数规范化 |
| `onebot_data.mjs` | OneBot 数据结构转换 |
| `../packet.py` | OneBot 原始包参数、PB 构造与响应规范化 |
| `packet_config.mjs` | 原始包 Hook 配置解析与默认值 |
| `packet_resources.mjs` | 内置原生资源注册、平台匹配与偏移表缓存 |
| `packet_runtime.mjs` | 发包与收包 Hook 的统一生命周期 |
| `packet_backend.mjs` | 原始发包后端选择与加载 |
| `packet_event_backend.mjs` | 原始包收发事件 Hook 与监听器管理 |
| `qq_platform.mjs` | QQ 路径、版本、加载器与数据目录适配 |
| `message_gate.mjs` | 实时消息准入与重复消息过滤 |
| `message_identity.mjs` | 消息身份与序列标识处理 |
| `session_adapters.mjs` | QQ 会话接口的版本兼容适配 |
| `../native/packet/packet_sender.*.node` | 各平台原始发包模块 |
| `../native/events/packet_events.*.node` | 各平台原始包事件模块 |
| `../native/packet/packet_offsets.json` | 原始发包版本偏移表 |
| `../native/events/event_offsets.json` | 原始包事件版本偏移表 |

---

## 2. 启动与隔离

框架为每个内置 QQ 账号启动独立运行时，并通过环境变量传入账号和运行目录。主要变量包括：

| 变量 | 说明 |
| --- | --- |
| `ELAINAQQ_EMBEDDED` | 必须为 `1`，表明进程由框架管理 |
| `ELAINAQQ_BOT_ID` | 框架内的账号标识 |
| `ELAINAQQ_BOT_UIN` | 已知的 QQ 号，登录前可能为空 |
| `ELAINAQQ_MANAGER_URL` | 当前账号专用的本机桥接地址 |
| `ELAINAQQ_DATA_DIR` | 当前账号的独立数据目录 |
| `ELAINAQQ_HEADLESS` | 是否使用无界面运行方式 |
| `ELAINAQQ_ONEBOT_ACTIONS` | 框架登记的动作名称列表 |
| `ELAINAQQ_PACKET_BACKEND` | 原始包 Hook 模式，设置为 `off` 可禁用 |
| `ELAINAQQ_PACKET_VERBOSE` | 是否输出原生 Hook 详细日志 |
| `ELAINAQQ_PACKET_O3_HOOK` | 是否启用 O3 原始包事件 Hook |
| `ELAINAQQ_PACKET_BYPASS` | 六类原生检测兼容选项的 JSON 对象 |

Windows 下，框架还会为每个账号设置独立的 `APPDATA`、`LOCALAPPDATA` 和 `USERPROFILE`。Linux 下可能附加数据包后端和资源控制相关环境变量。

原始发包后端采用两阶段初始化顺序：QQ session 创建前加载
原始发包模块并启用 native bypass，session 初始化完成后再安装版本对应的
收发包 Hook。两步不能合并到 session 初始化之后，否则 QQ 原生接口会把
protobuf Buffer 当成普通请求体解析并返回 `request body decode failed`。
原始包事件观察器仅在内置偏移表含当前 QQ 构建的安全偏移时启用；
缺少偏移时会自动降级，不影响登录和普通 QQNT 回调事件。
原生模块与版本偏移表随 ElainaQQ 一同发布，并且只从框架内部目录加载。
原始包参数校验、PB 构造、动作编排和响应解析位于 Python 的
`core/runtime/embedded/packet.py`；JavaScript 只调用已经登录的 QQNT
会话。QQNT 会话与登录密钥位于 Electron 进程内，因此最后的进程内
Hook 不能由进程外 Python 代码直接替代。
事件后端支持按收发方向、命令字或两者组合注册监听器，也支持一次性监听；
运行时只订阅自身需要处理的命令，停止账号时会统一清理监听器。

---

## 3. 通信流程

每个账号拥有一个只监听 `127.0.0.1` 的桥接服务。端口默认从 `embedded_qq.bridge_port_start=30010` 开始分配，并避开主服务端口和其他账号已使用的端口。

运行时使用以下内部端点：

| 方法与路径 | 方向 | 用途 |
| --- | --- | --- |
| `POST /api/embedded/events` | 运行时到框架 | 上报运行状态和 OneBot 事件 |
| `POST /api/embedded/red-packets` | 运行时到框架 | 上报红包事件 |
| `GET /api/embedded/control/poll` | 运行时到框架 | 长轮询下一条控制命令 |
| `POST /api/embedded/control/result` | 运行时到框架 | 返回动作、扫码刷新或红包领取结果 |

控制调用使用随机 `request_id` 关联请求和结果。普通 OneBot 动作默认等待 30 秒；控制队列、断线与关闭由 Python 管理器统一处理。

桥接服务只校验请求中的 `bot_id` 是否与当前账号端口一致，并依赖回环监听实现访问隔离。不要把桥接端口通过端口映射、反向代理或防火墙规则暴露到其他主机。

---

## 4. 事件与消息边界

运行时把 QQNT 数据转换为 OneBot 风格事件后上报。Python 侧再次执行字段规范化、账号别名解析、日志记录和插件分发。

消息准入优先使用 QQNT 的在线消息标记，并以本次登录后的监听注册时间为兼容边界。历史同步消息、缺少有效实时依据的消息以及同一会话中的重复回调不会作为新消息分发。

内部桥接传输不改变插件契约：插件收到的仍是 `MessageEvent`、`NoticeEvent`、`RequestEvent` 或 `MetaEvent`，发送动作仍应通过 `event.reply()`、`event.call_api()` 或 `get_api()`。

---

## 5. 红包事件

内置运行时识别红包后，Python 管理器先生成标准通知事件：

~~~text
post_type: notice
notice_type: elaina_red_packet
sub_type: receive
~~~

红包详情位于 `event.red_packet` 或 `event.raw_data['red_packet']`。普通插件可以显式订阅：

~~~python
from core.plugins import handler


@handler(r'.*', event_types=['notice.elaina_red_packet'])
async def on_red_packet(event, match):
    packet = event.red_packet
    event_id = packet.get('bill_no', '')
    event_group = packet.get('group_id')
~~~

框架还保留了内置 QQ 管理器的原生监听与领取接口：

~~~python
from core.plugins import get_app

manager = get_app().embedded_qq
manager.register_red_packet_listener('plugin_name', on_red_packet)
result = await manager.grab_red_packet(self_id, bill_no)
manager.unregister_red_packet_listener('plugin_name')
~~~

原生监听回调接收 `(self_id, packet)`。领取结果包含 `ok`、`amount`、`err_code` 和 `err_msg`。

这些管理器方法属于内置 QQ 专用能力，不适用于外部 OneBot 连接，也不属于 `core.plugins` 的稳定兼容接口。使用监听器的插件必须在 `@on_unload` 中注销自己的 owner，避免热重载后遗留回调。

---

## 6. 修改要求

修改桥接层时应同时验证：

- Windows、Linux 和 macOS 的 QQ 路径与账号数据隔离。
- 登录、二维码刷新、退出和异常关闭流程。
- 群聊、私聊、自身消息、通知和请求的字段规范化。
- OneBot 动作成功、失败、超时和连接中断响应。
- 消息重复过滤不会吞掉实时消息，也不会重放历史消息。
- 多账号桥接端口、控制请求和动作结果不会串号。
- 红包通知与原生回调不会重复领取或泄露敏感数据。

桥接协议变更必须同步检查 `core/runtime/embedded/manager.py` 和 `core/protocols/onebot/`，避免 JavaScript 与 Python 两侧契约不一致。
