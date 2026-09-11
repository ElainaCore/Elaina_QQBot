# 架构边界

## 分层

```text
main.py
  -> core.runtime.application
      -> core.runtime      运行时与生命周期
      -> core.plugins      插件加载与分发
      -> core.protocols    OneBot 契约
      -> core.services     文件、日志和监视
      -> core.transport    HTTP 与 WebSocket
      -> web               管理面板
```

依赖只能从上层指向下层；`core.foundation` 不依赖其他业务层，`core.transport` 不负责页面装配，插件不反向导入应用入口。

## 目录职责

| 目录 | 责任 |
| --- | --- |
| `core/foundation` | 配置、日志、品牌和安全路径 |
| `core/protocols` | OneBot 事件、消息、动作和连接模型 |
| `core/services` | 文件、日志存储和配置监视 |
| `core/runtime` | 应用生命周期、QQ 运行时和扩展 |
| `core/plugins` | 插件上下文、加载、分发和公开 API |
| `core/transport` | HTTP、WebSocket 和连接关闭 |
| `web` | 面板路由、鉴权和管理工具 |

## 统一事件管线

```text
内置 QQ ─┐
QQ 注入 ─┼─> OneBot 固定字段 -> EventPipeline -> EventDispatcher -> PluginManager
OneBot  ─┤
Lagrange─┘
```

`core/protocols/onebot/contract.py` 是字段、渠道、排序键和幂等键的唯一契约；入口兼容别名只在这里读取一次。

`EventPipeline` 提供有界短期去重和会话顺序；同一会话串行，不同会话并行；队列满时拒绝新事件并记录指标。

## QQ 运行时

- 内置 QQ 负责 QQNT 进程、桥接端口和本地动作。
- QQ 注入只负责已运行进程的接管，不启动或重启目标 QQ。
- Lagrange 通过 JSON-RPC runner 管理多账号，事件仍进入同一管线。
- 原生资源、偏移表和平台路径集中在运行时专用目录。

## 资源规则

- 网络、插件和事件接口保持异步。
- 文件、SQLite 和进程查询通过线程或异步子进程执行。
- 下载、解压、JSON 请求和 OneBot 响应必须有大小上限。
- 账号、Token、Cookie、日志和缓存不进入源码包。

## 变更规则

1. 新逻辑放入最小职责模块，应用层只做编排。
2. 跨层能力通过回调、协议对象或服务接口注入。
3. 平台差异放入专用适配器，调用方只消费统一结果。
4. 修改公开契约时补充回归测试并保持兼容别名。
