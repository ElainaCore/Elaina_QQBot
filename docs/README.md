# ElainaQQ 开发文档

本文档目录汇总 ElainaQQ 的插件开发接口、OneBot v11 消息格式和 API 调用方式。

> 开始开发前，请先完成项目根目录 [README.md](../README.md) 中的运行配置，并确认至少一个机器人账号已经正常连接。

## 目录

- [1. 文档导航](#1-文档导航)
- [2. 快速开始](#2-快速开始)
- [3. 稳定接口边界](#3-稳定接口边界)
- [4. 默认端口](#4-默认端口)
- [5. 文档约定](#5-文档约定)

---

## 1. 文档导航

| 文档 | 内容 |
| --- | --- |
| [插件开发文档](PLUGIN_DEVELOPMENT.md) | 插件结构、公开导入、元数据、事件、处理器、生命周期、数据文件、Web 扩展和调试规范 |
| [OneBot API 参考](ONEBOT_API.md) | 账号路由、消息格式、通用动作、常用封装、响应结构和错误处理 |

推荐阅读顺序：先完成插件开发文档的快速开始与事件章节，再按业务需要查询 OneBot API 参考。

---

## 2. 快速开始

在 `plugins/hello/main.py` 中创建插件入口：

~~~python
from core.plugins import handler


@handler(r'^状态$', name='状态检查', cooldown=3)
async def status(event, match):
    await event.reply('运行正常')
~~~

框架只识别 `plugins/<插件名>/main.py`。保存插件包中的 Python 文件后，文件监视器会自动重载整个插件。

---

## 3. 稳定接口边界

插件应从 `core.plugins` 导入公开能力：

~~~python
from core.plugins import current_plugin, get_api, handler, on_load, on_unload
~~~

`core.plugins` 统一导出插件装饰器、上下文、OneBot API、异步文件工具、日志工具和 Web 扩展接口。`core.plugins._loader`、`core.plugins._dispatch`、`core.protocols.onebot.adapter` 等模块属于框架内部实现，不保证为插件保持兼容。

OneBot 动作能否成功取决于当前连接的底层实现、登录状态、账号权限和 QQ 客户端版本。文档列出某个动作，表示框架能够路由或提供封装，不表示每个 OneBot 实现都支持该动作。

---

## 4. 默认端口

| 端口 | 用途 |
| --- | --- |
| `5201` | Web 面板和主 OneBot 服务入口 |
| `30010` 起 | 内置 QQ 账号的本机桥接端口，按账号递增分配 |

桥接端口只用于框架内部通信，插件不应直接使用或将其暴露到公网。

---

## 5. 文档约定

- 示例均使用 Python 3.11+ 和 `async def`。
- QQ 号、群号与 `self_id` 均为示例值，实际类型以事件和底层响应为准。
- API 返回值遵循 OneBot 风格，扩展字段可能因实现不同而变化。
- 示例中的网络地址只适用于本机开发；公开部署应配置鉴权、TLS 和访问控制。
