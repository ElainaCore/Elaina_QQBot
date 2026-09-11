# 插件开发

插件是可热重载的异步 Python 包，稳定接口统一从 `core.plugins` 导入。

## 入口

框架只加载 `plugins/<name>/main.py`，以 `_` 或 `.` 开头的目录会被忽略。

```text
plugins/weather/
├── main.py
├── handlers.py
├── assets/
├── data/
└── requirements.txt
```

入口需要显式导入包含注册逻辑的子模块：

```python
from . import handlers  # noqa: F401
```

## 最简示例

```python
from core.plugins import handler


@handler(r'^你好$', name='打招呼', cooldown=2)
async def say_hello(event, match):
    await event.reply('你好！')
```

处理器使用 `re.DOTALL` 和 `search()` 匹配 `event.content`，命令正则建议使用 `^` 与 `$`。

## 元数据

```python
__plugin_meta__ = {
    'name': '天气',
    'version': '1.0.0',
    'author': 'YourName',
    'description': '查询天气',
    'license': 'MIT',
}
```

元数据必须是静态字典，面板不会执行代码来读取它。

## 插件上下文

```python
from core.plugins import current_plugin

ctx = current_plugin()
DATA_FILE = ctx.get_data_path('state.json')
ASSET_FILE = ctx.get_resource_path('assets/panel.html')
ctx.log.info('插件已加载')
```

运行数据写入插件 `data/`，资源路径通过上下文解析，不依赖当前工作目录。

## handler

```text
@handler(
    pattern,
    name='',
    desc='',
    priority=0,
    owner_only=False,
    group_only=False,
    private_only=False,
    event_types=None,
    cooldown=0,
    block=False,
    fallback=False,
)
```

| 参数 | 含义 |
| --- | --- |
| `priority` | 数字越大越先执行 |
| `owner_only` | 仅主人消息 |
| `group_only` | 仅群消息 |
| `private_only` | 仅私聊消息 |
| `event_types` | 精确订阅事件类型 |
| `cooldown` | 按插件、账号、会话和用户限流 |
| `block` | 命中后停止收集低优先级处理器 |
| `fallback` | 普通匹配均失败后执行 |

`group_only` 与 `private_only` 不应同时启用。

## 事件类型

| 类型 | 示例 |
| --- | --- |
| 消息 | `message`、`message_sent` |
| 通知 | `notice.group_increase`、`notice.notify` |
| 请求 | `request.friend`、`request.group` |
| 元事件 | `meta_event.lifecycle`、`meta_event.heartbeat` |

```python
from core.plugins import handler


@handler(r'.*', event_types=['notice.group_increase'])
async def welcome(event, match):
    await event.call_api('send_group_msg', {
        'group_id': event.group_id,
        'message': f'欢迎 {event.user_id}',
    })
```

非消息事件没有正文时会使用事件类型参与正则匹配。

## Event

所有渠道提供相同的固定字段：

| 字段 | 含义 |
| --- | --- |
| `raw_data` | 规范化后的完整事件 |
| `time` | Unix 时间戳 |
| `self_id` | 当前机器人账号 |
| `post_type` | OneBot 事件大类 |
| `event_type` | 完整分发类型 |
| `source` | 诊断来源，不用于业务分支 |
| `extra` | 非固定扩展字段 |

消息事件额外提供 `message_type`、`message_id`、`user_id`、`group_id`、`message`、`raw_message`、`sender`、`content`、`is_group` 和 `is_private`。

扩展字段使用 `getattr(event, 'field', default)`，不要根据 `source` 写四套逻辑。

## 回复与调用

```python
await event.reply('文本')
await event.reply_image('https://example.com/a.png')
result = await event.call_api('get_group_info', {'group_id': event.group_id})
```

后台任务或非消息事件使用全局 API，并显式传入 `self_id`：

```python
from core.plugins import get_api

await get_api().send_private_msg(
    event.user_id,
    '处理完成',
    self_id=event.self_id,
)
```

完整动作与消息段见 [OneBot API](ONEBOT_API.md)。

## 生命周期

```python
import asyncio
from contextlib import suppress

from core.plugins import on_load, on_unload

worker = None


@on_load
async def start():
    global worker
    worker = asyncio.create_task(background())


@on_unload
async def stop():
    if worker:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
```

卸载时必须取消任务并关闭 HTTP 客户端、数据库连接和文件句柄。

## 中间件

```python
from core.plugins import api_interceptor, interceptor


@interceptor(priority=100)
async def reject(event):
    return event.post_type == 'message' and '禁用词' in event.content


@api_interceptor(priority=100)
async def tag_request(request, call_next):
    return await call_next()
```

拦截器返回 `True` 时停止事件分发，API 中间件必须且只能调用一次 `call_next()`。

## 文件与阻塞操作

```python
from core.plugins import read_json, run_sync, write_json

state = await read_json(DATA_FILE, default={})
await write_json(DATA_FILE, state)
result = await run_sync(blocking_function, argument)
```

并发修改同一文件时，使用 `asyncio.Lock` 保护完整的读改写事务。

## Web 扩展

```python
from aiohttp import web
from core.plugins import register_page, register_route

register_page(
    key='weather-panel',
    label='天气',
    html_file=ctx.get_resource_path('assets/panel.html'),
)


@register_route('GET', '/api/ext/weather/status')
async def status(request):
    return web.json_response({'ok': True})
```

扩展路由必须位于 `/api/ext/`；默认启用面板鉴权，公开路由需自行验证签名、请求大小和速率。

## 发布检查

- 所有回调使用 `async def`，同步 I/O 已移出事件循环。
- 多账号主动调用明确传入 `self_id`。
- 后台资源在 `@on_unload` 中释放。
- 密钥、Cookie、账号和日志未进入发布包。
- 群聊、私聊、通知、请求、重载和退出均已测试。
