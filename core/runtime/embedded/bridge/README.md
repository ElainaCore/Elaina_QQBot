# 内置 QQ 桥接

该目录是 QQNT 进程内 JavaScript 与 Python 管理器之间的内部桥接，不属于插件 API。

## 组件

| 文件 | 责任 |
| --- | --- |
| `qq_runtime.mjs` | QQNT 会话、登录和运行状态 |
| `manager_channel.mjs` | 本机控制轮询、事件上报和连接复用 |
| `onebot_data.mjs` | QQNT 数据到 OneBot 字段转换 |
| `onebot_message.mjs` | 消息段转换 |
| `onebot_action_contract.mjs` | 动作名称和参数契约 |
| `packet_*.mjs` | 原生包 Hook 生命周期 |
| `qq_platform.mjs` | 平台、路径和版本适配 |

## 启动隔离

每个账号使用独立 QQ 进程、数据目录和本机桥接端口；端口只监听回环地址。

## 内部端点

| 方法 | 用途 |
| --- | --- |
| `POST /api/embedded/events` | 上报状态和 OneBot 事件 |
| `POST /api/embedded/red-packets` | 上报红包事件 |
| `GET /api/embedded/control/poll` | 拉取控制命令 |
| `POST /api/embedded/control/result` | 返回控制结果 |

端点仅接受当前账号 `bot_id`，不要将桥接端口暴露给其他主机。

## 事件边界

JavaScript 只处理 QQNT 会话和进程内能力；Python 负责 OneBot 字段规范化、事件去重、顺序和插件分发。

消息、通知、请求和元事件必须保持 OneBot 形状，未知消息段不得静默丢弃。

## 修改检查

- 登录、二维码、退出和异常关闭。
- 群聊、私聊、自身消息和系统事件。
- 动作成功、失败、超时和断线。
- 多账号端口、控制请求和结果不串号。
- 原生 Hook 在缺少偏移时安全降级。
