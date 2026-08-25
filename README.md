<p>
<img src="https://download.nature.qq.com/SnsShare/SocialProfile/1779098988_1264b08a.png" width="200" align="left" style="border-radius:50%; margin-right:16px" />

<h1>ElainaQQ</h1>

ElainaQQ 是一个基于 Python 的异步 QQ 机器人框架，内置 QQNT 启动与扫码登录，支持多账号隔离、OneBot v11 网络接入、插件热重载和 Web 面板管理。

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org) [![License](https://img.shields.io/badge/License-MIT-green)](LICENSE) [![QQ群](https://img.shields.io/badge/QQ交流群-164178653-blue)](https://qm.qq.com/q/nepv1UcwRE)

- **纯异步架构** — 基于 aiohttp，事件分发、网络连接和插件接口均采用异步模型
- **内置 QQ 运行时** — 支持 QQ 安装、扫码登录、版本选择和多账号数据隔离
- **OneBot v11 接入** — 支持反向 / 正向 WebSocket、HTTP 上报和 HTTP API 客户端
- **Web 管理面板** — 提供账号、网络、插件、配置、日志、消息记录和框架更新管理

</p>
<br clear="left" />

> 项目仅供学习交流使用，请遵守所在地法律、QQ 平台规则及相关服务条款。交流群：[164178653](https://qm.qq.com/q/nepv1UcwRE)。

## 🚀 快速开始

要求：Python 3.11+、Git、可运行 QQNT 的系统环境。

```bash
git clone https://github.com/ElainaCore/Elaina_QQBot.git ElainaQQ
cd ElainaQQ
python -m pip install -r requirements.txt
python main.py
```

首次启动会从 `config/*.example.yaml` 生成 `config/settings.yaml` 和 `config/connections.yaml`。启动后访问 [Web 面板](http://localhost:5201/web/) 完成配置，默认密码为 `admin`。

内置 QQ 可直接在面板中创建账号并扫码登录；使用外部 OneBot 实现时，在“网络配置”中创建对应连接。

## 📁 框架结构

```
ElainaQQ/
├── main.py          # 主程序入口
├── config/          # 框架与 OneBot 网络配置
├── core/            # 核心框架
│   ├── foundation/  # 配置、日志与基础设施
│   ├── plugins/     # 插件加载、分发与公开 API
│   ├── protocols/   # OneBot v11 事件、消息和动作
│   ├── runtime/     # 应用、模块与内置 QQ 运行时
│   ├── services/    # 文件、日志和配置监视服务
│   └── transport/   # HTTP / WebSocket 传输
├── plugins/         # 插件目录（运行时按需创建）
├── modules/         # 模块目录（运行时按需创建）
├── data/            # 账号、日志、媒体和运行数据
├── web/             # Web 面板后端与 dist 构建产物
└── docs/            # 开发文档
```

`plugins/`、`modules/` 和 `data/` 可能在首次运行或安装扩展后生成。不要提交账号数据、Token、Cookie、日志或插件私有数据。

## 🔗 机器人接入

- **内置 QQ** — 保持 `embedded_qq.enabled: true`，在 Web 面板创建机器人并扫码登录。每个账号使用独立数据目录和本机桥接端口。
- **反向 WebSocket** — 框架作为服务端，默认主入口为 `ws://127.0.0.1:5201/OneBotv11`；必须先在面板启用对应连接。
- **正向 WebSocket** — 框架主动连接外部 OneBot WebSocket 服务。
- **HTTP 接入** — 支持接收 OneBot HTTP 事件上报，以及调用外部 OneBot HTTP API。

内置 QQ 桥接端口默认从 `30010` 开始，只监听 `127.0.0.1`，属于框架内部通信端口，不应暴露到公网或由插件直接连接。生产环境应为网络连接配置 Token / Secret，并通过可信反向代理启用 TLS。

## 🔌 开发与扩展

- **开发文档** — [文档目录](docs/README.md)汇总插件开发、事件模型、消息发送和 OneBot API。
- **架构规范** — [架构文档](docs/ARCHITECTURE.md)定义内部模块职责、依赖方向、资源布局和性能约束。
- **插件开发** — [插件开发文档](docs/PLUGIN_DEVELOPMENT.md)包含插件结构、上下文、处理器、生命周期、中间件、多账号和 Web 扩展。
- **OneBot API** — [API 参考文档](docs/ONEBOT_API.md)包含账号路由、消息段、常用动作、响应结构与错误处理。
- **Web 前端** — 前端源码位于 [Elaina_QQBot_web](https://github.com/ElainaCore/Elaina_QQBot_web)，本仓库保留可直接运行的 `web/dist` 构建产物。

最简插件入口为 `plugins/hello/main.py`：

```python
from core.plugins import handler


@handler(r'^你好$', name='打招呼', desc='回复一句问候')
async def say_hello(event, match):
    await event.reply('你好！')
```

框架只识别包含 `main.py` 的 `plugins/<插件名>/` 目录。保存插件包中的 Python 文件后，文件监视器会自动热重载。

## 🛒 插件市场

框架从 [Elaina-plugins](https://github.com/ElainaCore/Elaina-plugins) 的 `onebot_plugins.json` 获取插件和模块列表，支持在 Web 面板中浏览、安装、更新、卸载和镜像加速；插件开发者可向该仓库提交 PR，将插件加入市场。

## ⚙️ 常用配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `server.host` | `0.0.0.0` | Web 面板与主 OneBot 服务监听地址 |
| `server.port` | `5201` | Web 面板与主 OneBot 服务端口 |
| `web.admin_password` | `admin` | 面板管理员密码，部署后必须修改 |
| `owner.ids` | 空列表 | `owner_only=True` 处理器允许的 QQ 号 |
| `embedded_qq.enabled` | `true` | 是否启用内置 QQ 管理 |
| `embedded_qq.bridge_port_start` | `30010` | 内置账号桥接端口起点 |
| `logging.retention_days` | `30` | 日志保留天数 |

`config/settings.yaml` 和 `config/connections.yaml` 支持运行时热加载。修改监听地址、端口或底层 QQ 启动参数后，应观察控制台与面板状态，确认相关服务是否需要重启。

## 🤝 反馈与贡献

遇到问题或有功能建议，请前往 [Issues](https://github.com/ElainaCore/Elaina_QQBot/issues) 提交 Issue；欢迎通过 [Pull Requests](https://github.com/ElainaCore/Elaina_QQBot/pulls) 提交 PR，参与项目改进。

提交问题时请附上 Python 版本、操作系统、连接类型、相关日志和最小复现步骤，并先删除 QQ 号、Token、Cookie 等敏感信息。

## 📄 开源协议

本项目采用 MIT 协议开源，详见 [LICENSE](LICENSE) 文件。
