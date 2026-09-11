<p>
<img src="https://download.nature.qq.com/SnsShare/SocialProfile/1779098988_1264b08a.png" width="160" align="left" />

# ElainaQQ

面向多账号场景的异步 QQ 机器人框架，统一支持内置 QQ、QQ 注入、OneBot v11 和 Lagrange。

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org) [![License](https://img.shields.io/badge/License-MIT-green)](LICENSE) [![QQ群](https://img.shields.io/badge/QQ交流群-164178653-blue)](https://qm.qq.com/q/nepv1UcwRE)

</p>
<br clear="left" />

> 项目仅供学习交流，请遵守所在地法律、QQ 平台规则及相关服务条款。

## 特性

- 四种接入统一进入同一事件管线，插件不再感知渠道差异。
- 支持群聊、私聊、自身消息、通知、请求和元事件。
- 支持多账号路由、插件热重载、Web 管理和日志持久化。
- 对消息字段、消息段、动作响应、顺序和幂等进行统一规范化。

## 快速开始

环境要求：Python 3.11+、Git，以及当前系统可运行的 QQ 环境。

```bash
git clone https://github.com/ElainaCore/Elaina_QQBot.git ElainaQQ
cd ElainaQQ
python -m pip install -r requirements.txt
python main.py
```

启动后访问 [http://localhost:5201/web/](http://localhost:5201/web/)，首次管理密码会写入 `config/settings.yaml`。

配置文件由 `config/*.example.yaml` 自动生成，字段说明只保留在对应 YAML 中。

## 接入链路

```text
内置 QQ ─┐
QQ 注入 ─┼─> 渠道适配 ─> EventPipeline ─> EventDispatcher ─> 插件
OneBot  ─┤
Lagrange─┘
```

所有入口先锁定 OneBot 固定字段，再执行短期幂等和会话有序分发；渠道差异只存在于入口转换与动作执行器。

## 目录

```text
core/foundation   配置、日志和安全基础设施
core/protocols    OneBot 事件、消息、动作和连接契约
core/runtime      应用生命周期与 QQ 运行时
core/plugins      插件加载、分发和公开接口
core/services     文件、日志和监视服务
core/transport    HTTP 与 WebSocket 传输
web               Web 面板后端与构建产物
plugins           插件
modules           模块
tests             回归测试
docs              开发参考
```

## 最简插件

创建 `plugins/hello/main.py`：

```python
from core.plugins import handler


@handler(r'^你好$', name='打招呼')
async def say_hello(event, match):
    await event.reply('你好！')
```

插件只应从 `core.plugins` 导入公开能力，保存 Python 文件后会自动热重载。

## 文档

- [开发文档索引](docs/README.md)
- [架构边界](docs/ARCHITECTURE.md)
- [插件开发](docs/PLUGIN_DEVELOPMENT.md)
- [OneBot API](docs/ONEBOT_API.md)

Web 前端源码位于 [Elaina_QQBot_web](https://github.com/ElainaCore/Elaina_QQBot_web)，插件市场索引位于 [Elaina-plugins](https://github.com/ElainaCore/Elaina-plugins)。

## 安全

- 公网部署必须配置强密码、OneBot Token/Secret、TLS 和访问控制。
- 不要提交账号目录、Token、Cookie、二维码、日志或插件私有数据。
- 插件和模块属于可执行代码，只安装可信来源。

## 反馈

请通过 [Issues](https://github.com/ElainaCore/Elaina_QQBot/issues) 提交问题，并附带系统、Python 版本、接入渠道、日志和复现步骤。

本项目采用 [MIT License](LICENSE)。
