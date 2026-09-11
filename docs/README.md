# ElainaQQ 开发文档

本文档只记录稳定接口和架构约束，配置字段请直接查看 `config/*.yaml`。

## 导航

| 文档 | 内容 |
| --- | --- |
| [架构边界](ARCHITECTURE.md) | 分层、事件管线、依赖方向和性能约束 |
| [插件开发](PLUGIN_DEVELOPMENT.md) | 插件入口、事件、处理器、生命周期和 Web 扩展 |
| [OneBot API](ONEBOT_API.md) | 账号路由、消息段、动作调用和响应格式 |

## 稳定边界

- 插件只从 `core.plugins` 导入公开能力。
- 四种渠道统一输出 OneBot 固定字段和消息段。
- 渠道差异只允许存在于入口适配器和本地动作执行器。
- 内部模块、桥接端口和运行时对象不承诺插件兼容性。

## 验证

```bash
python -m unittest discover -s tests -q
python -m compileall -q core modules plugins web tests
python -m ruff check .
```
