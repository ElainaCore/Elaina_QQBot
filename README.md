# ElainaQQ

ElainaQQ 是一个基于 Python 的异步 QQ 机器人框架，内置 QQNT 启动、扫码登录、多账号隔离、插件热重载和 Web 面板管理，并提供 OneBot v11 协议兼容接口。

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![QQ群](https://img.shields.io/badge/QQ交流群-164178653-blue)](https://qm.qq.com/q/nepv1UcwRE)

- **纯异步架构**：基于 aiohttp，支持 WebSocket 与 HTTP 网络接入。
- **内置 QQ**：直接管理 QQ 安装、扫码登录、版本切换与多账号会话。
- **插件系统**：支持插件热重载、模块扩展、机器人绑定和在线配置。
- **Web 管理面板**：提供运行监控、消息记录、插件管理和框架配置。

> 项目仅供学习交流使用，严禁用于非法行为。

## 交流群

**ElainaQQ 框架交流群：[164178653](https://qm.qq.com/q/nepv1UcwRE)**

## 快速开始

### 环境要求

- Python 3.11+
- Git
- QQNT 内置运行时，所有账号共用一份 QQ 安装文件

运行框架和内置 QQ 不需要服务器预装 Node.js。只有开发或重新构建 Web 前端时才需要 Node.js。

### 安装

```bash
git clone https://github.com/ElainaCore/Elaina_QQBot.git ElainaQQ
cd ElainaQQ
pip install -r requirements.txt
python main.py
```

首次启动会自动从 `config/*.example.yaml` 生成 `config/settings.yaml` 与 `config/connections.yaml`。配置文件均支持**热加载**，修改后无需重启。

启动后访问 Web 面板完成配置：

```
http://localhost:5201/web/
```

> 默认端口为 `5201`，首次登录使用 `config/settings.yaml` 中的 `web.admin_password`。主人 QQ 号填在 `owner.ids`。

内置 QQ 为每个账号分配独立的本机桥接端口，默认从 `30010` 开始递增。桥接端口只绑定 `127.0.0.1`，无需在防火墙或安全组中开放；可通过 `embedded_qq.bridge_port_start` 修改起始值。主面板和公开 OneBot 入口仍使用 `server.port`。

### 网络接入

框架在主服务端口提供 OneBot v11 反向 WebSocket 入口 `/OneBotv11`：

```
ws://127.0.0.1:5201/OneBotv11
```

其他网络连接可直接在 Web 面板中创建和维护。

## Web 管理面板

启动框架后访问：

```
http://localhost:5201/web/
```

面板提供：实时消息与日志、系统状态监控、插件启停/热重载、插件市场、配置编辑、网络连接管理等。

前端源码独立维护在 [Elaina_QQBot_web](https://github.com/ElainaCore/Elaina_QQBot_web)。后端仓库保留可直接运行的 `web/dist` 构建产物。

前端仓库设置 `ELAINAQQ_BACKEND_DIR` 后，构建产物会直接写入后端的 `web/dist`。后端也可通过 `ELAINAQQ_WEB_DIST` 加载外部构建目录。

## 项目结构

```
ElainaQQ/
├── main.py          # 主程序入口
├── config/          # 配置文件 (settings.yaml / connections.yaml)
├── core/            # 核心框架
│   ├── base/        #   配置、日志、上下文
│   ├── onebot/      #   OneBot v11 适配器 / API / 连接
│   ├── plugin/      #   插件加载、分发、热重载、装饰器
│   ├── module/      #   模块系统
│   ├── server/      #   HTTP / WS 服务器
│   └── storage/     #   日志数据库等存储
├── plugins/         # 插件目录 (热加载)
└── web/             # Web 面板 (后端 + 前端 dist)
```

## 开发文档

- [插件开发指南](docs/PLUGIN_DEVELOPMENT.md)
- [OneBot API 参考](docs/ONEBOT_API.md)

最简插件 `plugins/hello/main.py`：

```python
from core.plugin.decorators import handler


@handler(r'^你好$', name='打招呼', desc='回复一句问候')
async def say_hello(event, match):
    await event.reply("你好!")
```

## 插件市场

框架内置插件市场，从 [ElainaCore/Elaina-plugins](https://github.com/ElainaCore/Elaina-plugins) 的 `onebot_plugins.json` 获取插件列表。

- **Web 面板** — 在线浏览、搜索、一键安装/更新
- **镜像加速** — 自动选用可用的 GitHub 镜像下载

**插件开发者** 可前往 [Elaina-plugins](https://github.com/ElainaCore/Elaina-plugins) 提交 PR，将你的插件加入市场。

## 开源协议

本项目采用 MIT 协议开源，详见 [LICENSE](LICENSE) 文件。

## 免责声明

本项目仅供学习交流使用，使用本框架所产生的一切后果由使用者自行承担，与开发者无关。请勿将本框架用于任何违法违规用途。

---

如果这个项目对你有帮助，欢迎 Star。

ElainaQQ 团队
