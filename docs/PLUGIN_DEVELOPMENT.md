# ElainaQQ 插件开发文档

本文档说明如何为 ElainaQQ 编写可热重载的异步插件。所有示例均以 `core.plugins` 公开接口和当前 OneBot v11 事件模型为准。

> 开发前请先按项目根目录的 [README](../README.md) 启动框架、登录至少一个 QQ 账号，并确认该账号能正常收发消息。

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 插件结构与元数据](#2-插件结构与元数据)
  - [2.1 唯一入口](#21-唯一入口)
  - [2.2 热重载](#22-热重载)
  - [2.3 第三方依赖](#23-第三方依赖)
- [3. 公开 API 与插件上下文](#3-公开-api-与插件上下文)
  - [3.1 统一导入入口](#31-统一导入入口)
  - [3.2 插件元数据](#32-插件元数据)
  - [3.3 插件上下文](#33-插件上下文)
- [4. 事件与处理器](#4-事件与处理器)
  - [4.1 handler 装饰器](#41-handler-装饰器)
  - [4.2 消息匹配顺序](#42-消息匹配顺序)
  - [4.3 优先级、阻断与冷却](#43-优先级阻断与冷却)
  - [4.4 事件类型](#44-事件类型)
- [5. Event 事件对象](#5-event-事件对象)
  - [5.1 MessageEvent](#51-messageevent)
  - [5.2 NoticeEvent](#52-noticeevent)
  - [5.3 RequestEvent](#53-requestevent)
  - [5.4 MetaEvent](#54-metaevent)
- [6. 生命周期与中间件](#6-生命周期与中间件)
  - [6.1 加载与卸载](#61-加载与卸载)
  - [6.2 消息拦截器](#62-消息拦截器)
  - [6.3 目标插件过滤器](#63-目标插件过滤器)
  - [6.4 出站 API 中间件](#64-出站-api-中间件)
- [7. 消息发送与 OneBot 调用](#7-消息发送与-onebot-调用)
- [8. 配置、日志与阻塞操作](#8-配置日志与阻塞操作)
- [9. Web 面板扩展](#9-web-面板扩展)
- [10. 多账号与插件绑定](#10-多账号与插件绑定)
- [11. 完整示例](#11-完整示例)
- [12. 调试与发布检查](#12-调试与发布检查)

---

## 1. 快速开始

创建以下目录和入口文件：

~~~text
plugins/
└── hello/
    └── main.py
~~~

`plugins/hello/main.py`：

~~~python
from core.plugins import handler


@handler(r'^你好$', name='打招呼', desc='回复一句问候')
async def say_hello(event, match):
    await event.reply('你好！')
~~~

框架会在启动时加载该插件。运行期间保存插件包中的 Python 文件，文件监视器通常会在数秒内重载整个插件。

处理器使用正则表达式的 `search()` 匹配 `event.content`。示例使用 `^` 和 `$` 限制整条消息，避免在普通聊天中误触发。

---

## 2. 插件结构与元数据

### 2.1 唯一入口

框架只发现符合以下结构的插件：

~~~text
plugins/<插件目录名>/main.py
~~~

`index.py`、`app.py`、`plugins/` 根目录中的单个 Python 文件，以及没有 `main.py` 的目录都不会作为插件加载。目录名以 `_` 或 `.` 开头时也会被忽略。

一个实用的包式插件可以这样组织：

~~~text
plugins/
└── weather/
    ├── main.py
    ├── handlers.py
    ├── client.py
    ├── assets/
    │   └── panel.html
    ├── data/
    │   └── state.json
    └── requirements.txt
~~~

框架只主动执行 `main.py`。需要注册子模块中的处理器时，在入口中显式导入：

~~~python
# plugins/weather/main.py
from . import handlers  # noqa: F401
~~~

插件以 `plugins.<目录名>` 包加载，因此可以使用相对导入。不要修改 `sys.path`，也不要依赖当前工作目录解析资源。

### 2.2 热重载

文件监视器递归检查已加载插件目录中的 Python 文件：

- 修改已有的非下划线 Python 文件会触发重载。
- 新增非下划线 Python 文件会触发重载。
- 重载前执行旧插件的 `@on_unload`，随后重新导入整个包。
- HTML、JSON、图片等资源变化本身不会触发 Python 热重载。
- 新建插件目录后，最可靠的加载方式是在 Web 面板操作或重启框架。

重载会丢弃模块级内存状态。需要跨重载保留的数据应写入插件 `data/` 目录。

### 2.3 第三方依赖

可以在插件目录放置 `requirements.txt` 供安装器和插件市场使用，但当前插件加载器不会因为手动复制了插件目录就自动执行 `pip install`。本地开发时应在框架使用的 Python 环境中显式安装依赖：

~~~bash
python -m pip install -r plugins/weather/requirements.txt
~~~

发布插件时固定合理的版本范围，并避免把密钥、Cookie、账号数据或生成文件打包进仓库。

---

## 3. 公开 API 与插件上下文

### 3.1 统一导入入口

插件应从 `core.plugins` 导入稳定的公开能力：

| 分类 | 公开名称 |
| --- | --- |
| 注册 | `handler`、`interceptor`、`handler_filter`、`api_interceptor`、`on_load`、`on_unload` |
| 上下文 | `current_plugin`、`PluginContext`、`get_app` |
| OneBot | `get_api`、`OneBotAPI`、`ApiCallRequest`、`bypass_api_interceptors` |
| 文件 | `ensure_dir`、`read_text`、`write_text`、`read_json`、`write_json`、`run_sync` |
| 日志 | `PLUGIN`、`get_logger`、`report_error` |
| Web | `register_page`、`unregister_page`、`register_route`、`unregister_route` |
| 配置 | `config` |

不要从 `core.plugins._loader`、`core.plugins._dispatch` 或 OneBot 适配器内部模块导入对象。以下划线开头的模块和成员属于实现细节。

所有注册回调都必须使用 `async def`。同步处理器、生命周期函数、中间件或插件 HTTP 路由会在加载阶段直接报错。

### 3.2 插件元数据

在 `main.py` 顶层声明 `__plugin_meta__`：

~~~python
__plugin_meta__ = {
    'name': '天气查询',
    'author': 'YourName',
    'description': '查询城市天气并发送预报',
    'version': '1.0.0',
    'github': 'https://github.com/example/elaina-weather',
    'homepage': 'https://example.com/weather',
    'license': 'MIT',
}
~~~

框架只读取 `name`、`author`、`description`、`version`、`github`、`homepage` 和 `license`。这些值会转换为字符串并显示在 Web 面板；其他字段会被忽略。

插件必须至少通过装饰器注册一项能力，或注册一个 Web 页面/路由。处理器、生命周期钩子、拦截器、过滤器和 API 中间件都计入注册能力；完全没有注册能力的包会被判定为加载失败。

### 3.3 插件上下文

插件导入、处理器、生命周期以及插件路由执行期间都存在当前插件上下文：

~~~python
from core.plugins import current_plugin

ctx = current_plugin()
STATE_FILE = ctx.get_data_path('state.json')
PANEL_FILE = ctx.get_resource_path('assets/panel.html')
~~~

| 成员 | 说明 |
| --- | --- |
| `ctx.name` | 插件目录名 |
| `ctx.plugin_dir` / `ctx.root` | 插件根目录，分别为字符串和 `Path` |
| `ctx.data_dir` / `ctx.data` | 插件 `data/` 目录，分别为字符串和 `Path` |
| `ctx.get_data_path(name)` | 返回 `data/` 下的路径 |
| `ctx.get_resource_path(name)` | 返回插件根目录下的资源路径 |
| `ctx.log` | 以插件名命名的 logger |

框架在加载插件前创建 `data/`。路径方法只负责拼接路径，不会校验传入文件名是否越过插件目录；插件应只使用自己控制的相对文件名。

异步读写 JSON：

~~~python
from core.plugins import current_plugin, read_json, write_json

ctx = current_plugin()
STATE_FILE = ctx.get_data_path('state.json')


async def increment(user_id: int) -> int:
    data = await read_json(STATE_FILE, default={})
    key = str(user_id)
    data[key] = int(data.get(key, 0)) + 1
    await write_json(STATE_FILE, data)
    return data[key]
~~~

`write_text` 和 `write_json` 会创建父目录；`write_text` 默认使用临时文件替换目标文件。若多个处理器可能同时修改同一文件，仍应使用 `asyncio.Lock` 保护“读取、修改、写入”这一整个事务。

---

## 4. 事件与处理器

### 4.1 handler 装饰器

`handler` 的签名为：

~~~text
@handler(
    pattern,
    *,
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
~~~

| 参数 | 说明 |
| --- | --- |
| `pattern` | 使用 `re.DOTALL` 编译的正则表达式，通过 `search()` 匹配 |
| `name` | 面板和日志中的名称，默认使用函数名 |
| `desc` | 命令说明 |
| `priority` | 数字越大越先匹配、先执行 |
| `owner_only` | 仅消息发送者在 `owner.ids` 中时执行 |
| `group_only` | 仅群消息执行 |
| `private_only` | 仅私聊消息执行 |
| `event_types` | 订阅指定事件类型；不传时默认处理普通消息 |
| `cooldown` | 冷却秒数，按插件、处理器、机器人、会话和用户隔离 |
| `block` | 命中后不再收集后续低优先级处理器 |
| `fallback` | 只在普通命令和斜杠兼容匹配均失败后参与；也可传同步判断函数 |

`group_only` 和 `private_only` 不应同时设置。`owner_only`、会话限制和冷却只在消息分发路径上应用；通知和请求事件需要在处理器内自行进行权限和字段校验。

### 4.2 消息匹配顺序

对于 `message` 和 `message_sent`，框架按以下顺序匹配：

1. 普通处理器匹配原始 `event.content`。
2. 如果没有命中，自动尝试增加或移除开头的 `/`。
3. 仍未命中时，运行 `fallback=True` 的处理器。

因此 `r'^帮助$'` 同时兼容“帮助”和“/帮助”。宽泛的自然语言处理器应设置 `fallback=True`：

~~~python
@handler(r'(?s)^(.+)$', name='自然对话', priority=-50, fallback=True)
async def chat(event, match):
    answer = await ask_model(match.group(1))
    await event.reply(answer)
~~~

`fallback` 也可以是接收事件的同步函数：

~~~python
def fallback_enabled(event):
    return event.is_private


@handler(r'(?s)^(.+)$', fallback=fallback_enabled)
async def private_chat(event, match):
    await event.reply('私聊兜底回复')
~~~

### 4.3 优先级、阻断与冷却

默认 `block=False`，所以多个匹配的处理器会按优先级依次执行。设置 `block=True` 后，匹配阶段停止收集后续处理器：

~~~python
@handler(r'^状态$', priority=100, block=True)
async def authoritative_status(event, match):
    await event.reply('运行正常')
~~~

冷却命中时框架会静默跳过该处理器，不自动发送提示。需要显示剩余时间或持久化限流时，应在插件中实现业务级限流。

### 4.4 事件类型

消息事件使用：

- `message`：收到的群聊或私聊消息。
- `message_sent`：机器人自身发出的消息；必须显式写入 `event_types` 才会收到。

非消息事件使用带分类前缀的名称：

| 类别 | 写法 | 示例 |
| --- | --- | --- |
| 通知 | `notice.<notice_type>` | `notice.group_increase`、`notice.group_ban`、`notice.notify` |
| 请求 | `request.<request_type>` | `request.friend`、`request.group` |
| 元事件 | `meta_event.<meta_event_type>` | `meta_event.lifecycle`、`meta_event.heartbeat` |

`event_types` 必须精确包含目标类型：

~~~python
@handler(r'.*', event_types=['notice.group_increase'])
async def welcome(event, match):
    await get_api().send_group_msg(
        event.group_id,
        f'欢迎新成员 {event.user_id}',
        self_id=event.self_id,
    )
~~~

非消息事件没有文本正文时，正则匹配对应的事件类型字符串，所以通常使用 `r'.*'`。不传 `event_types` 的处理器不会接收通知、请求和元事件。

---

## 5. Event 事件对象

所有事件都继承自 `OneBotEvent`，公共字段如下：

| 字段 | 说明 |
| --- | --- |
| `event.raw_data` | 规范化后的完整事件字典 |
| `event.time` | Unix 时间戳 |
| `event.self_id` | 接收或产生事件的机器人账号 |
| `event.post_type` | `message`、`message_sent`、`notice`、`request` 或 `meta_event` |
| `event.event_type` | 上游提供的扩展事件标识；缺省时等于 `post_type` |
| `event.content` | 消息纯文本；其他事件为空字符串 |
| `event.to_dict()` | 返回 `raw_data` |

上游提供但未列为固定属性的字段可以通过 `event.<字段名>` 访问；缺失字段会抛出 `AttributeError`。对扩展字段应使用 `getattr(event, 'field', default)`。

### 5.1 MessageEvent

| 字段或属性 | 说明 |
| --- | --- |
| `message_type` | `group` 或 `private` |
| `sub_type` | 消息子类型 |
| `message_id` | 消息 ID |
| `message_seq` / `real_seq` | 消息序号，具体含义由实现决定 |
| `user_id` | 发送者 QQ 号 |
| `group_id` / `group_name` | 群号和群名，私聊可能为空 |
| `target_id` | 部分自身消息事件中的目标账号 |
| `message` | 规范化后的 OneBot 消息段数组 |
| `raw_message` | CQ 字符串表示 |
| `sender` | 发送者原始字典 |
| `sender_nickname` / `sender_card` | 昵称和群名片便捷属性 |
| `content` | 拼接所有 `text` 段并去除首尾空白后的文本 |
| `is_group` / `is_private` | 会话类型判断 |
| `is_sent` | 是否为机器人自身发出的消息 |

消息事件提供：

~~~python
await event.reply('文本')
await event.reply_text('文本')
await event.reply_image('https://example.com/image.png')
await event.call_api('get_group_info', {'group_id': event.group_id})
~~~

`reply()` 会保持当前事件的 `self_id`，群消息调用 `send_group_msg`，私聊调用 `send_private_msg`。发送能力和消息段格式见 [OneBot API 参考](ONEBOT_API.md)。

### 5.2 NoticeEvent

固定字段包括 `notice_type`、`sub_type`、`user_id`、`group_id` 和 `operator_id`。不同通知还可能在 `raw_data` 中提供 `message_id`、`duration`、`target_id` 等扩展字段。

### 5.3 RequestEvent

固定字段包括 `request_type`、`sub_type`、`user_id`、`group_id`、`comment`、`flag`、`approve` 和 `reason`。

处理请求时使用全局 API，并明确传入当前机器人账号：

~~~python
from core.plugins import get_api, handler


@handler(r'.*', event_types=['request.friend'])
async def friend_request(event, match):
    await get_api().set_friend_add_request(
        event.flag,
        approve=True,
        self_id=event.self_id,
    )
~~~

只有 `MessageEvent` 定义 `reply()` 和 `call_api()`。通知、请求和元事件应使用 `get_api()`。

### 5.4 MetaEvent

固定字段包括 `meta_event_type`、`status` 和 `interval`。心跳事件频率较高，不应在处理器中执行耗时操作或写入大量日志。

---

## 6. 生命周期与中间件

### 6.1 加载与卸载

~~~python
import asyncio
from contextlib import suppress

from core.plugins import on_load, on_unload

worker = None


async def background_worker():
    while True:
        await asyncio.sleep(60)


@on_load
async def start_worker():
    global worker
    worker = asyncio.create_task(background_worker(), name='my-plugin-worker')


@on_unload
async def stop_worker():
    if worker is None:
        return
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
~~~

`@on_load` 在插件导入并完成注册收集后执行。任一加载钩子失败会回滚本次加载，执行已注册的卸载钩子并清理插件 Web 资源。

`@on_unload` 在禁用、重载和框架退出时执行。每个插件必须在这里取消任务并关闭 HTTP 客户端、数据库连接、文件句柄等资源。

### 6.2 消息拦截器

拦截器在处理器匹配前按优先级运行。返回值严格为 `True` 时停止本次事件分发：

~~~python
from core.plugins import interceptor


@interceptor(priority=100)
async def reject_keyword(event):
    if event.post_type == 'message' and '禁用词' in event.content:
        await event.reply('该内容不可用')
        return True
    return False
~~~

拦截器会收到所有分发事件，因此访问 `is_group`、`reply` 等消息专有成员前应先检查 `post_type`。

### 6.3 目标插件过滤器

`handler_filter` 在处理器匹配前决定是否跳过某个目标插件：

~~~python
from core.plugins import handler_filter


@handler_filter(priority=100)
async def restrict_admin_tools(event, target_plugin):
    return target_plugin == 'admin_tools' and str(getattr(event, 'user_id', '')) != '123456'
~~~

返回 `True` 只会阻止当前目标插件，不会阻止其他插件。结果按“当前事件 + 目标插件”缓存，因此过滤逻辑不应依赖某个具体处理器。

### 6.4 出站 API 中间件

`api_interceptor` 可以检查、修改或接管插件发起的 OneBot 调用：

~~~python
from core.plugins import api_interceptor


@api_interceptor(priority=100)
async def append_source(request, call_next):
    if request.action == 'send_group_msg':
        request.params['message'].append({
            'type': 'text',
            'data': {'text': ' [weather]'},
        })
    return await call_next()
~~~

`ApiCallRequest` 的主要字段：

| 字段 | 说明 |
| --- | --- |
| `action` | 规范化后的 OneBot 动作名 |
| `params` | 可原地修改的参数字典 |
| `self_id` | 目标机器人账号，可能为空 |
| `source_plugin` | 发起调用的插件目录名 |
| `context` | 来源事件中的账号、用户、群和消息类型 |
| `local` | 目标是否由内置 QQ 本地动作处理 |

只有调用并返回 `await call_next()` 才会继续后续中间件和传输层。同一个中间件不能重复调用 `call_next()`。直接返回 OneBot 风格字典可以接管调用。

中间件内部如需调用原始 API，应绕过中间件链，避免递归：

~~~python
from core.plugins import bypass_api_interceptors, get_api


async def raw_status(self_id):
    with bypass_api_interceptors():
        return await get_api().get_status(self_id=self_id)
~~~

---

## 7. 消息发送与 OneBot 调用

回复当前消息优先使用 `event.reply()`。后台任务、通知/请求处理器或跨会话发送使用 `get_api()`：

~~~python
from core.plugins import get_api

api = get_api()

await api.send_group_msg(
    123456,
    [{'type': 'text', 'data': {'text': '定时通知'}}],
    self_id='10001',
)
~~~

调用未封装的动作：

~~~python
result = await get_api().call_api(
    'custom_action',
    {'key': 'value'},
    self_id=event.self_id,
)
~~~

也可用动态关键字调用：

~~~python
result = await get_api().custom_action(
    key='value',
    self_id=event.self_id,
)
~~~

成功与否应检查 `status` 和 `retcode`，不要只判断返回值是否为真：

~~~python
if result.get('status') != 'ok' or result.get('retcode') != 0:
    ctx.log.warning('调用失败: %s', result.get('message'))
~~~

完整说明见 [OneBot API 参考](ONEBOT_API.md)。

---

## 8. 配置、日志与阻塞操作

### 8.1 读取框架配置

`core.plugins.config` 是全局配置对象：

~~~python
from core.plugins import config

port = config.get('settings', 'server.port', 5201)
owners = config.get('settings', 'owner.ids', [])
connections = config.get_raw('connections')
~~~

`config.get(file, 'a.b.c', default)` 使用点路径读取 YAML。插件通常只应读取框架配置；插件自己的可变数据应保存在插件 `data/`，以免与框架升级和其他插件冲突。

### 8.2 日志与错误上报

~~~python
from core.plugins import PLUGIN, get_logger, report_error

log = get_logger(PLUGIN, '天气查询')


async def update_cache():
    try:
        log.info('开始更新天气缓存')
        await fetch_weather()
    except Exception as exc:
        report_error(PLUGIN, '天气查询', exc, context={'phase': 'update_cache'})
~~~

处理器未捕获的异常会由框架记录到错误日志。只有在插件需要补充业务上下文、进行降级处理或继续运行时才自行捕获异常。

### 8.3 不要阻塞事件循环

网络请求应使用异步客户端；文件读写使用公开的异步文件工具。无法替换的同步库通过 `run_sync` 执行：

~~~python
from core.plugins import run_sync

result = await run_sync(blocking_library_call, argument)
~~~

框架为每次处理器执行设置 300 秒超时。超时后任务被取消并记录错误，但这不是用来代替正常的网络超时和资源清理的。

---

## 9. Web 面板扩展

### 9.1 注册页面

~~~python
from core.plugins import current_plugin, register_page

ctx = current_plugin()

register_page(
    key='weather-panel',
    label='天气配置',
    source='plugin',
    source_name=ctx.name,
    html_file=ctx.get_resource_path('assets/panel.html'),
    icon='cloud-sun',
)
~~~

`html` 与 `html_file` 二选一，`html` 优先。`key` 必须在所有插件中唯一，后注册的同名页面会覆盖先注册的页面。

插件卸载或加载回滚时，框架会按所有者自动清理页面和路由。也可以使用 `unregister_page(key)` 提前注销。

### 9.2 注册 HTTP 路由

~~~python
from aiohttp import web
from core.plugins import register_route


@register_route('GET', '/api/ext/weather/status')
async def weather_status(request):
    return web.json_response({'ok': True, 'provider': 'example'})
~~~

约束如下：

- 路径必须以 `/api/ext/` 开头，建议包含插件目录名。
- 路由按“HTTP 方法 + 完整路径”精确匹配，不支持路径参数。
- 可变参数放在查询字符串或请求体中。
- 处理函数必须使用 `async def` 并返回 `aiohttp.web.StreamResponse`。
- `HEAD` 未单独注册时会回退到同路径的 `GET`。
- 默认 `auth=True`，要求有效的面板登录会话。

公开回调可以关闭面板鉴权：

~~~python
@register_route('POST', '/api/ext/weather/callback', auth=False)
async def callback(request):
    body = await request.json()
    return web.json_response({'received': bool(body)})
~~~

`auth=False` 表示任何能访问该端口的人都可调用。此时插件必须自行验证签名、限制请求体大小、校验内容并配置速率限制。

页面脚本调用受保护路由时，浏览器会携带面板的 HttpOnly 会话 Cookie。不要把面板密码或 Token 写入页面源码。

---

## 10. 多账号与插件绑定

消息处理器中的 `event.reply()` 和 `event.call_api()` 自动使用事件的 `self_id`。使用全局 API 时应显式传入：

~~~python
await get_api().send_private_msg(
    event.user_id,
    '处理完成',
    self_id=event.self_id,
)
~~~

没有 `self_id` 时，适配器可能选择默认账号；没有可确定的唯一账号或连接时，调用可能失败。

Web 面板可以把整个插件或插件子模块绑定到指定机器人。绑定在处理器、拦截器、过滤器和 API 中间件分发前生效。插件代码不应读取或修改内部的 `data/plugin_bots.yaml`，应由面板维护绑定关系。

后台任务如果服务多个账号，应在创建任务时复制必要的 `self_id`，不要依赖之后可能变化的默认路由。

---

## 11. 完整示例

下面的 `plugins/checkin/main.py` 展示元数据、并发安全的数据文件、两个命令、生命周期和页面路由：

~~~python
import asyncio
import time

from aiohttp import web

from core.plugins import (
    current_plugin,
    handler,
    on_load,
    on_unload,
    read_json,
    register_page,
    register_route,
    write_json,
)

__plugin_meta__ = {
    'name': '签到',
    'author': 'YourName',
    'description': '每日签到计数示例',
    'version': '1.0.0',
    'license': 'MIT',
}

ctx = current_plugin()
DATA_FILE = ctx.get_data_path('checkin.json')
data_lock = asyncio.Lock()


async def load_data():
    data = await read_json(DATA_FILE, default={})
    return data if isinstance(data, dict) else {}


@on_load
async def setup():
    register_page(
        key='checkin-stats',
        label='签到统计',
        source='plugin',
        source_name=ctx.name,
        html='<main><h1>签到统计</h1><p id="total">加载中</p></main>',
    )
    ctx.log.info('签到插件已加载')


@on_unload
async def teardown():
    ctx.log.info('签到插件已卸载')


@handler(r'^签到$', name='签到', desc='每天签到一次', cooldown=2)
async def check_in(event, match):
    today = time.strftime('%Y-%m-%d')
    key = str(event.user_id)

    async with data_lock:
        data = await load_data()
        record = data.get(key, {'last': '', 'total': 0})
        if record['last'] == today:
            total = record['total']
            already = True
        else:
            record = {'last': today, 'total': int(record['total']) + 1}
            data[key] = record
            await write_json(DATA_FILE, data)
            total = record['total']
            already = False

    if already:
        await event.reply(f'今天已经签到，累计 {total} 天')
    else:
        await event.reply(f'签到成功，累计 {total} 天')


@handler(r'^签到次数$', name='签到次数')
async def checkin_total(event, match):
    async with data_lock:
        data = await load_data()
    total = int(data.get(str(event.user_id), {}).get('total', 0))
    await event.reply(f'累计签到 {total} 天')


@register_route('GET', '/api/ext/checkin/stats')
async def stats(request):
    async with data_lock:
        data = await load_data()
    return web.json_response({
        'users': len(data),
        'checkins': sum(int(item.get('total', 0)) for item in data.values()),
    })
~~~

这个页面示例只注册了 HTML 和数据接口。实际前端应处理接口失败、转义动态文本，并遵守面板现有样式和交互约定。

---

## 12. 调试与发布检查

### 12.1 常见加载失败

| 现象 | 检查项 |
| --- | --- |
| 面板找不到插件 | 路径是否为 `plugins/<name>/main.py`，目录名是否以 `_` 或 `.` 开头 |
| 装饰器报上下文错误 | 是否从 `core.plugins` 导入，是否在插件加载期间注册 |
| 提示没有注册能力 | 是否实际导入了包含装饰器的子模块 |
| 相对导入失败 | 是否使用包内相对导入，是否手动修改了 `sys.path` |
| 修改后未重载 | 修改的是否为 Python 文件，插件当前是否已加载 |
| API 返回未连接 | 目标账号是否在线，`self_id` 是否正确，连接是否启用 |
| 通知处理器不触发 | `event_types` 是否使用 `notice.*`、`request.*` 等精确类型 |

### 12.2 发布前清单

- 所有回调使用 `async def`，同步 I/O 已移出事件循环。
- 正则尽量使用 `^`、`$`，宽泛处理器使用 `fallback=True`。
- 后台任务、客户端和句柄在 `@on_unload` 中释放。
- 多账号主动调用明确传入 `self_id`。
- `data/`、密钥、Cookie、账号信息和日志未进入发布包。
- `requirements.txt` 只包含必要依赖和合理版本范围。
- Web 公开路由具备独立鉴权、输入校验和限流。
- 在群聊、私聊、重载、禁用和框架退出场景完成测试。

OneBot 动作、消息段和响应处理请继续阅读 [OneBot API 参考](ONEBOT_API.md)。
