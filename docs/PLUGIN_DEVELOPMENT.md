# ElainaQQ 插件开发文档

> 面向开发者的完整插件开发指南 — 从最简单的 "Hello World" 到多文件插件、主动消息推送、Web 面板扩展、生命周期钩子等。本框架基于 **OneBot v11** 协议，纯异步架构。

---

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 插件目录结构](#2-插件目录结构)
- [3. 核心装饰器](#3-核心装饰器)
  - [3.1 `@handler` 消息处理器](#31-handler-消息处理器)
  - [3.2 `@on_load` / `@on_unload` 生命周期钩子](#32-on_load--on_unload-生命周期钩子)
  - [3.3 `@interceptor` 消息拦截器](#33-interceptor-消息拦截器)
  - [3.4 `@handler_filter` 目标插件过滤器](#34-handler_filter-目标插件过滤器)
  - [3.5 `@api_interceptor` 出站 API 中间件](#35-api_interceptor-出站-api-中间件)
- [4. Event 事件对象](#4-event-事件对象)
- [5. 消息发送 API](#5-消息发送-api)
- [6. OneBot API 调用](#6-onebot-api-调用)
- [7. 插件上下文 `ctx`](#7-插件上下文-ctx)
- [8. 插件元数据 `__plugin_meta__`](#8-插件元数据-__plugin_meta__)
- [9. Web 面板扩展](#9-web-面板扩展)
- [10. 配置读取与日志](#10-配置读取与日志)
- [11. 调试与最佳实践](#11-调试与最佳实践)
- [12. 完整示例](#12-完整示例)

---

## 1. 快速开始

在 `plugins/` 下新建文件 `plugins/hello/main.py`：

```python
"""Hello 插件 — 最小示例"""
from core.plugin.decorators import handler


@handler(r'^你好$', name='打招呼', desc='回复一句问候')
async def say_hello(event, match):
    await event.reply("你好!")
```

**完成。** 框架启动时会自动扫描 `plugins/` 目录加载插件，文件改动会触发热重载，无需重启。

| 元素 | 说明 |
| --- | --- |
| `@handler(r'^你好$')` | 正则匹配用户消息文本 |
| `event` | 当前消息事件对象 (`core.onebot.event.MessageEvent`) |
| `match` | `re.Match` 对象 (匹配结果) |
| `event.reply(...)` | 回复当前会话 (自动判断群聊/私聊) |

> 处理函数签名固定为 `async def func(event, match)`，也支持同步函数 (会自动跑在线程池中)。

---

## 2. 插件目录结构

每个插件是 `plugins/` 下的一个**子目录**，框架会导入目录内的入口文件 (推荐 `main.py`)。以 `_` 或 `.` 开头的目录会被忽略。

### 2.1 简单插件 (单文件)

```
plugins/
└── hello/
    ├── main.py            # 入口文件
    └── data/              # 持久化数据 (可选, 由 ctx 自动创建)
```

### 2.2 大型插件 (多文件 + 子模块)

```
plugins/
└── my_plugin/
    ├── main.py            # 入口 (在此 import 子模块即可生效)
    ├── app/               # 子模块目录
    │   └── core.py
    ├── data/              # 数据存储 (ctx 管理)
    └── requirements.txt   # 依赖 (可选, 框架可自动 pip install)
```

> **子目录访问**：`from .app.core import xxx` (相对导入)。
> **自由组织**：框架只导入入口文件，内部结构、文件数量和命名完全自由，只需在入口文件中 import 即可生效。

---

## 3. 核心装饰器

所有装饰器都从 `core.plugin.decorators` 导入：

```python
from core.plugin.decorators import handler, on_load, on_unload, interceptor
```

### 3.1 `@handler` 消息处理器

**签名**：

```python
@handler(pattern, *, name='', desc='', priority=0,
         owner_only=False, group_only=False, private_only=False,
         event_types=None, cooldown=0, block=False, fallback=False)
```

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `pattern` | `str` | — | 正则表达式 (使用 `re.DOTALL` 编译, 对消息文本做 `search`) |
| `name` | `str` | 函数名 | 处理器显示名称 (Web 面板 / 日志) |
| `desc` | `str` | `''` | 功能描述 |
| `priority` | `int` | `0` | 优先级 (数字越大越先匹配) |
| `owner_only` | `bool` | `False` | 仅主人可触发 (主人 QQ 配置于 `settings.yaml` 的 `owner.ids`) |
| `group_only` | `bool` | `False` | 仅群聊 |
| `private_only` | `bool` | `False` | 仅私聊 |
| `event_types` | `list[str]` | `None` | 仅响应指定事件类型 (见下表) |
| `cooldown` | `int` | `0` | 同一用户冷却时间 (秒, 0 = 无冷却) |
| `block` | `bool` | `False` | 命中后是否拦截后续处理器 (见 3.1.1) |
| `fallback` | `bool \| Callable[[Event], bool]` | `False` | 仅在普通处理器完成原文和加/去 `/` 匹配后仍未命中时参与 |

**事件类型常量** (`event_types` 可选值)：

| 取值 | 含义 |
| --- | --- |
| `message` | 消息事件 (群聊 + 私聊) |
| `notice.<notice_type>` | 通知事件, 如 `notice.group_increase` (入群)、`notice.group_decrease` (退群)、`notice.group_ban` (禁言)、`notice.friend_add` 等 |
| `request.<request_type>` | 请求事件, 如 `request.friend` (加好友)、`request.group` (加群) |
| `meta_event.lifecycle` | OneBot 连接生命周期事件 |

> 不传 `event_types` 时默认只处理消息事件。处理通知/请求事件时需显式指定，且正则会对 `event_type` 字符串匹配，常用 `r'.*'` 全匹配。

**示例**：

```python
@handler(r'^/?菜单$', name='主菜单', desc='显示功能列表', priority=10)
async def menu(event, match):
    await event.reply("📋 功能列表:\n1. 签到\n2. 抽卡")


@handler(r'^踢\s+(\d+)$', name='踢人', owner_only=True, group_only=True)
async def kick(event, match):
    await event.call_api('set_group_kick', {
        'group_id': event.group_id, 'user_id': int(match.group(1))})
    await event.reply("✅ 已踢出")


@handler(r'.*', name='入群欢迎', event_types=['notice.group_increase'])
async def welcome(event, match):
    await event.call_api('send_group_msg', {
        'group_id': event.group_id,
        'message': f"欢迎新成员 {event.user_id}!"})


@handler(r'(?s)^(.+)$', name='自然对话', priority=-50, fallback=True)
async def chat(event, match):
    await event.reply(await ask_model(match.group(1)))
```

`fallback=True` 用于 AI 对话等真正的兜底正则。框架先匹配普通指令的原文与加/去 `/` 兼容文本，最后才让兜底处理器匹配原始消息，避免宽泛正则阻止其他插件触发。

娱乐聚合器等需要与其他插件同时执行的逻辑应使用 `@interceptor`，处理完成后返回 `False`。这样无需注册宽泛正则，也不会阻断普通处理器：

```python
@interceptor(priority=-40)
async def entertainment(event):
    await try_handle_entertainment(event)
    return False
```

#### 3.1.1 `block` 放行 / 拦截

多个插件注册相同指令时, `block=False` (默认) 放行让所有命中处理器按 `priority` 顺序执行, `block=True` 命中即拦截后续低优先级处理器。

```python
@handler(r'^状态$', name='系统状态', priority=10, block=True)  # 命中即拦截, 只有它响应
async def status(event, match):
    await event.reply("✅ 系统正常")


@handler(r'^状态$', name='天气状态', priority=0)  # 被上面 block 拦截, 不会触发
async def weather(event, match):
    await event.reply("☀️ 今天晴")
```

### 3.2 `@on_load` / `@on_unload` 生命周期钩子

```python
from core.plugin.decorators import on_load, on_unload


@on_load
async def init():
    """插件加载完成时执行 (支持 async/sync)"""
    print("插件已加载")


@on_unload
def cleanup():
    """插件卸载/重载时执行 — 清理资源"""
    print("插件已卸载")
```

> **使用场景**：启动后台任务、连接数据库、注册 Web 页面、注销定时器等。热重载会先执行旧实例的 `on_unload` 再加载新代码。

### 3.3 `@interceptor` 消息拦截器

拦截器在所有 handler 之前执行，可用于全局过滤、黑名单、统计等。

```python
@interceptor(priority=100)
async def filter_keywords(event):
    """返回 True 阻止后续 handler 匹配, 否则继续"""
    if '违禁词' in (event.content or ''):
        await event.reply("⛔ 消息包含违禁词")
        return True
    return False
```

| 参数 | 说明 |
| --- | --- |
| `priority` | 拦截器优先级 (数字越大越先执行, 默认 100) |
| 返回值 | `True` 阻止后续处理, 其他值继续 |

### 3.4 `@handler_filter` 目标插件过滤器

目标插件过滤器在 handler 匹配前执行，适合按目标插件实现租户隔离、权限策略或审计规则。返回 `True` 时只跳过当前目标插件，不影响其他插件处理同一事件。

```python
from core.plugin.decorators import handler_filter


@handler_filter(priority=100)
async def restrict_plugin(event, target_plugin):
    if target_plugin == 'admin_tools' and str(event.user_id) != '123456':
        return True
    return False
```

框架会按目标插件缓存一次事件中的过滤结果，因此过滤器不应依赖具体 handler。

### 3.5 `@api_interceptor` 出站 API 中间件

API 中间件在插件调用到达 OneBot 适配器前执行，可以修改参数、接管调用或放行到下一个中间件。只有调用并返回 `await call_next()` 时，调用才会继续发送。

```python
from core.onebot.api import bypass_api_interceptors, get_api
from core.plugin.decorators import api_interceptor


@api_interceptor(priority=100)
async def append_source(request, call_next):
    if request.action == 'send_group_msg':
        request.params['message'] = str(request.params.get('message', '')) + ' [plugin]'
    return await call_next()


async def send_without_interception(group_id, message, self_id):
    with bypass_api_interceptors():
        return await get_api().call_api(
            'send_group_msg',
            {'group_id': group_id, 'message': message},
            self_id=self_id,
        )
```

`request` 是可变的 `ApiCallRequest`，常用字段如下：

| 字段 | 说明 |
| --- | --- |
| `action` | OneBot action 名称 |
| `params` | 可直接修改的参数字典 |
| `self_id` | 本次调用路由到的 QQ 账号 |
| `source_plugin` | 发起调用的插件目录名；框架外调用为空 |
| `context` | 来源事件中的账号、用户、群和事件类型 |
| `local` | 目标是否为框架内置 QQ |

中间件可直接返回 OneBot 风格结果以接管调用。调用原始 API 时应使用 `bypass_api_interceptors()`，避免递归进入自身。

框架会自动标记消息处理器、插件导入与生命周期钩子、由这些入口创建的异步后台任务，以及 `/api/ext/` 插件路由中的 API 调用。中间件可据此使用 `source_plugin` 按插件目录名拦截框架内插件发送；只有框架执行上下文之外的调用才会留空。

---

## 4. Event 事件对象

`event` 是所有 handler 的第一个参数。框架根据 `post_type` 解析为不同子类。

### 4.1 消息事件 `MessageEvent` (`post_type == 'message'`)

| 字段 / 属性 | 类型 | 说明 |
| --- | --- | --- |
| `event.user_id` | `int` | 发送者 QQ 号 |
| `event.group_id` | `int` / `None` | 群号 (仅群聊) |
| `event.message_type` | `str` | `'group'` / `'private'` |
| `event.sub_type` | `str` | 子类型 (如 `normal` / `friend`) |
| `event.message_id` | `int` | 消息 ID (用于撤回/引用) |
| `event.message` | `list[dict]` | 消息段数组 (OneBot 标准, 见 5.3) |
| `event.raw_message` | `str` | 原始消息 (CQ 码形式) |
| `event.content` | `str` | 提取出的纯文本 (已拼接所有 text 段并 strip) |
| `event.sender` | `dict` | 发送者信息原始字典 |
| `event.sender_nickname` | `str` | 发送者昵称 |
| `event.sender_card` | `str` | 群名片 |
| `event.self_id` | `int` | 收到该消息的机器人 QQ 号 |
| `event.time` | `int` | 事件时间戳 |
| `event.raw_data` | `dict` | 完整原始事件字典 |

**场景判断**：

| 属性 | 说明 |
| --- | --- |
| `event.is_group` | 是否群聊 |
| `event.is_private` | 是否私聊 |

### 4.2 其他事件类型

| 类 | `post_type` | 关键字段 |
| --- | --- | --- |
| `NoticeEvent` | `notice` | `notice_type` / `sub_type` / `user_id` / `group_id` / `operator_id` |
| `RequestEvent` | `request` | `request_type` / `sub_type` / `user_id` / `group_id` / `comment` / `flag` |
| `MetaEvent` | `meta_event` | `meta_event_type` (心跳/生命周期, 一般无需处理) |

> 通知/请求事件没有 `content`，handler 用 `event_types` 精确订阅，并通过 `event.call_api(...)` 进行处理 (如同意加群)。

---

## 5. 消息发送 API

### 5.1 回复当前会话

`event.reply()` 自动根据来源选择 `send_group_msg` / `send_private_msg`。

```python
# 纯文本
await event.reply("Hello!")
await event.reply_text("等价写法")

# 图片 (URL / 本地路径 / base64, 取决于 OneBot 实现的支持)
await event.reply_image("https://i.elaina.vin/1.png")
await event.reply_image("file:///path/to/local.png")
await event.reply_image("base64://...")

# 消息段数组 (混合文本/图片/@等)
await event.reply([
    {'type': 'text', 'data': {'text': '看图: '}},
    {'type': 'image', 'data': {'file': 'https://i.elaina.vin/1.png'}},
])
```

### 5.2 主动发送 / 发往指定目标

通过 `event.call_api`(见第 6 节) 或框架 API 对象向任意群/用户推送 (不依赖当前消息)：

```python
# 发往指定群
await event.call_api('send_group_msg', {
    'group_id': 123456, 'message': '定时通知'})

# 发往指定用户 (私聊)
await event.call_api('send_private_msg', {
    'user_id': 10001, 'message': '私信内容'})
```

没有 `event` 时 (定时任务、`@on_load` 后台循环)，取全局 API 对象直接调用：

```python
from core.onebot.api import get_api

api = get_api()
await api.send_group_msg(123456, "后台推送")
await api.send_private_msg(10001, "后台私信")
```

### 5.3 消息段 (CQ 数组格式)

OneBot v11 的消息是「消息段」数组，常用类型：

| `type` | `data` 字段 | 说明 |
| --- | --- | --- |
| `text` | `{'text': '...'}` | 纯文本 |
| `image` | `{'file': 'url/path/base64'}` | 图片 |
| `at` | `{'qq': 10001}` 或 `{'qq': 'all'}` | @某人 / @全体 |
| `face` | `{'id': 1}` | QQ 表情 |
| `reply` | `{'id': message_id}` | 引用回复 |
| `record` | `{'file': '...'}` | 语音 |
| `video` | `{'file': '...'}` | 视频 |
| `file` / `onlinefile` | `{'file': '...'}` | 文件 / 在线文件 |
| `json` / `miniapp` | `{'data': '...'}` | Ark JSON / 小程序 Ark 数据 |
| `xml` | `{'data': '...'}` | XML 长消息 |
| `markdown` | `{'content': '...'}` | Markdown |
| `music` | `{'type': 'qq', 'id': '...'}` | 音乐卡片；可用 `ELAINAQQ_MUSIC_SIGN_URL` 配置签名服务 |
| `mface` | `{'emoji_package_id': 1, 'emoji_id': '...', 'key': '...', 'summary': '...'}` | 商城表情 |
| `dice` / `rps` | `{'result': '...'}` | 骰子 / 猜拳 |
| `contact` | `{'type': 'qq', 'id': '10001'}` | 好友或群联系人卡片 |
| `location` | `{'lat': 31.2, 'lon': 121.5}` | 位置 |
| `flashtransfer` | `{'fileSetId': '...'}` | QQ 闪传 |
| `node` | `{'nickname': '...', 'content': [...]}` | 合并转发节点；一条消息必须全部为 `node` |
| `forward` | `{'id': 'res_id'}` | 已有合并转发卡片；收到的段同时提供 `res_id` |
| `poke` | `{'type': '...', 'id': '...'}` | 接收解析；发送应调用 `send_poke`，依赖协议能力 |

内置 QQ 会把收到的 `poke`、`onlinefile`、`flashtransfer` 和合并转发解析为独立消息段。收到合并转发后，可把 `forward.data.id` 传给 `get_forward_msg` 读取节点；发送已有转发卡片时优先使用 `forward.data.res_id`。

```python
# @发送者 + 文本
await event.reply([
    {'type': 'at', 'data': {'qq': event.user_id}},
    {'type': 'text', 'data': {'text': ' 你被点名了'}},
])

# 引用回复
await event.reply([
    {'type': 'reply', 'data': {'id': event.message_id}},
    {'type': 'text', 'data': {'text': '收到'}},
])
```

> `reply()` 传入字符串时框架会自动包装为一个 `text` 段；需要图文混排或 @ 时请直接传消息段数组。

---

## 6. OneBot API 调用

任何 OneBot v11 标准动作都可通过 `event.call_api(action, params)` 调用 (无 event 时用 `get_api().call_api(...)`)：

```python
# 获取群成员信息
info = await event.call_api('get_group_member_info', {
    'group_id': event.group_id, 'user_id': event.user_id})

# 禁言 30 分钟
await event.call_api('set_group_ban', {
    'group_id': event.group_id, 'user_id': 10001, 'duration': 1800})

# 同意加好友请求 (在 request.friend 事件中)
await event.call_api('set_friend_add_request', {
    'flag': event.flag, 'approve': True})
```

框架在 `core.onebot.api.OneBotAPI` 中封装了常用动作 (经 `event.call_api` 或 `get_api()` 间接使用)：

| 方法 | 对应动作 |
| --- | --- |
| `send_group_msg` / `send_private_msg` / `send_msg` | 发送消息 |
| `delete_msg` / `get_msg` | 撤回 / 获取消息 |
| `get_login_info` / `get_stranger_info` | 账号 / 陌生人信息 |
| `get_friend_list` / `get_group_list` / `get_group_info` | 列表与信息 |
| `get_group_member_list` / `get_group_member_info` | 群成员 |
| `set_group_kick` / `set_group_ban` / `set_group_whole_ban` | 群管理 |
| `set_group_card` / `set_group_name` / `set_group_admin` / `set_group_special_title` / `set_group_leave` | 群资料/成员管理 |
| `set_group_portrait` / `set_group_sign` / `get_group_at_all_remain` / `get_group_honor_info` / `get_group_system_msg` | 群扩展 |
| `get_essence_msg_list` / `set_essence_msg` / `delete_essence_msg` | 群精华消息 |
| `set_friend_add_request` / `set_group_add_request` | 处理请求 |
| `send_forward_msg` / `send_group_forward_msg` / `send_private_forward_msg` / `get_forward_msg` | 合并转发 |
| `get_group_msg_history` / `get_friend_msg_history` / `mark_group_msg_as_read` / `mark_private_msg_as_read` | 历史/已读 |
| `set_msg_emoji_like` / `send_poke` | 表情回应 / 戳一戳 |
| `send_like` / `delete_friend` / `set_qq_avatar` / `set_qq_profile` / `get_unidirectional_friend_list` / `ocr_image` | 用户/账号 |
| `upload_group_file` / `upload_private_file` / `get_group_root_files` / `get_group_files_by_folder` / `get_group_file_url` / `delete_group_file` / `create_group_file_folder` | 文件 |
| `get_version_info` / `get_status` / `can_send_image` / `can_send_record` / `get_cookies` / `get_csrf_token` / `clean_cache` | 系统 |

> 表中为通用动作名 (各 OneBot v11 实现普遍支持)；个别实现可能未实现某动作。任何未封装的动作都可用 `call_api(action, params)` 直接调用。API 调用默认 30 秒超时，无可用连接时返回 `None`。

---

## 7. 插件上下文 `ctx`

`ctx` 在插件加载时由框架注入，提供 **data/ 目录读写与日志**。在模块顶层捕获：

```python
import os
import core.plugin.context as _ctx_mod

ctx = _ctx_mod.ctx  # 模块顶层捕获 (加载期间有效)

# data/ 下文件的绝对路径 (目录已自动创建)
path = ctx.get_data_path('counter.json')

# 插件根目录下的资源文件
res = ctx.get_resource_path('template.html')

# 读写示例
import json
data = {}
if os.path.exists(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
data['count'] = data.get('count', 0) + 1
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
```

| 成员 | 说明 |
| --- | --- |
| `ctx.name` | 插件名 (目录名) |
| `ctx.plugin_dir` | 插件根目录绝对路径 |
| `ctx.data_dir` | `data/` 目录绝对路径 (自动创建) |
| `ctx.get_data_path(filename)` | 返回 `data/` 下文件路径 |
| `ctx.get_resource_path(filename)` | 返回插件根目录下文件路径 |
| `ctx.log` | 该插件的 logger |

---

## 8. 插件元数据 `__plugin_meta__`

在入口模块顶层声明，**Web 面板将展示这些信息**：

```python
__plugin_meta__ = {
    'name': '我的插件',
    'author': 'YourName',
    'description': '插件功能说明',
    'version': '1.0.0',
    'github': 'https://github.com/xxx/repo',
    'homepage': 'https://example.com',
    'license': 'MIT',
}
```

仅 `name` / `author` / `description` / `version` / `github` / `homepage` / `license` 这几个字段会被读取，其余忽略。

---

## 9. Web 面板扩展

### 9.1 注册侧边栏页面

```python
from core.plugin.web_pages import register_page, unregister_page
from core.plugin.decorators import on_unload


# 内联 HTML
register_page(
    key='my-page',            # 唯一标识 (路由 /custom/<key>)
    label='我的页面',          # 侧边栏显示名
    source='plugin',
    source_name='my_plugin',
    html='<h1>Hello Panel</h1>',
)

# 或指定 HTML 文件
register_page(key='my-page', label='我的页面',
              html_file='/abs/path/to/page.html')


@on_unload
def _cleanup():
    unregister_page('my-page')
```

### 9.2 注册自定义 HTTP 路由

路径**必须以 `/api/ext/` 开头** (建议 `/api/ext/{插件名}/` 避免冲突)。默认 `auth=True` 复用后台登录 token；设 `auth=False` 则免验证 (如对外回调、健康检查)。插件卸载时框架会自动注销其全部路由。

```python
from aiohttp import web
from core.plugin.web_pages import register_route


# 免验证路由
@register_route('GET', '/api/ext/myplugin/ping', auth=False)
async def ping(request):
    return web.json_response({'ok': True})


# 默认要求已经登录 Web 面板；插件页面会自动携带 HttpOnly 会话 Cookie
@register_route('POST', '/api/ext/myplugin/echo')
async def echo(request):
    from web.protocol import json_body, ok

    body = await json_body(request)
    return ok(you_sent=body)
```

| 参数 | 说明 |
| --- | --- |
| `method` | `'GET'` / `'POST'` / `'PUT'` / `'DELETE'` 等 |
| `path` | 必须以 `/api/ext/` 开头 (精确匹配, 不支持路径参数; 可变部分走查询串/请求体) |
| `handler` | `async def handler(request)`, 返回 `web.json_response(...)` |
| `auth` | 是否要求登录 token, 默认 `True` |

> 也可非装饰器写法：`register_route('POST', '/api/ext/x/do', handler)`。路由热重载即时生效。

---

## 10. 配置读取与日志

### 10.1 读取框架配置

框架配置在 `config/settings.yaml`，通过全局 `cfg` 读取 (支持热加载)：

```python
from core.base.config import cfg

# cfg.get(文件名, '点路径', 默认值)
port = cfg.get('settings', 'server.port', 5201)
owner_ids = cfg.get('settings', 'owner.ids', [])
```

`server.port` 是 Web 面板和公开 OneBot 入口端口。内置 QQ 的账号桥接端口由框架管理，默认从 `embedded_qq.bridge_port_start=30010` 开始递增，并且只监听 `127.0.0.1`。插件不应连接或占用这些内部端口；调用 QQ 能力时始终使用 `event.reply(...)` 或 `core.onebot.api.get_api()`。

### 10.2 日志与异常上报

```python
from core.base.logger import get_logger, PLUGIN, report_error

log = get_logger(PLUGIN, '我的插件')


@handler(r'^风险操作$')
async def risky(event, match):
    try:
        log.info('开始处理')
        await do_something()
    except Exception as e:
        report_error(PLUGIN, '我的插件', e)   # 上报到面板错误日志
        await event.reply("❌ 操作失败")
```

---

## 11. 调试与最佳实践

### 11.1 超时与异步

- 框架对每个 handler 强制 **300 秒超时**，超时会自动取消并记录错误。
- 推荐全程 `async def` + `await`；同步函数会被自动放进线程池执行，但**同步函数内无法 `await event.reply`**，应避免。
- 不要在 async handler 里做同步阻塞 IO，用 `asyncio.to_thread(...)` 包装。

### 11.2 命名与正则

| 规则 | 推荐 |
| --- | --- |
| handler 函数名 | snake_case, 体现功能 |
| `name=` 参数 | 中文短名, 用于面板/日志展示 |
| `desc=` 参数 | 一句话描述功能 |
| 正则锚定 | 尽量使用 `^` / `$` 避免误匹配 (pattern 用 `search` 匹配) |
| 资源清理 | 在 `@on_unload` 中关闭文件/连接/页面/定时器 |

### 11.3 性能

- **延迟导入**：体积大的依赖在 handler 内 `import`，加快插件加载。
- **冷却限流**：高频指令加 `cooldown=N`。
- **大型插件**：子模块放到 `app/` 等子目录，按需 import。

---

## 12. 完整示例

一个具备 **元数据 + 数据持久化 + 多 handler + 生命周期 + Web 页面** 的签到插件 `plugins/checkin/main.py`：

```python
"""签到插件 — 积分 + 数据持久化 + Web 页面"""

import json
import os
import random
import time

import core.plugin.context as _ctx_mod
from core.plugin.decorators import handler, on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page
from core.base.logger import get_logger, PLUGIN

__plugin_meta__ = {
    'name': '签到插件',
    'author': 'YourName',
    'description': '每日签到 + 积分系统',
    'version': '1.0.0',
    'license': 'MIT',
}

log = get_logger(PLUGIN, '签到')
ctx = _ctx_mod.ctx
_DATA = ctx.get_data_path('checkin.json')


def _load():
    if os.path.exists(_DATA):
        with open(_DATA, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save(d):
    with open(_DATA, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)


@on_load
async def init():
    log.info("签到插件已加载")
    register_page(
        key='checkin-stats', label='签到统计',
        source='plugin', source_name='checkin',
        html='<h1>签到统计</h1><p>开发中...</p>',
    )


@on_unload
def cleanup():
    unregister_page('checkin-stats')
    log.info("签到插件已卸载")


@handler(r'^签到$', name='签到', desc='每日签到领积分')
async def check_in(event, match):
    data = _load()
    uid = str(event.user_id)
    today = time.strftime('%Y-%m-%d')
    rec = data.get(uid, {'last': '', 'points': 0})
    if rec['last'] == today:
        await event.reply(f"今天已签到啦, 当前积分: {rec['points']}")
        return
    gain = random.randint(10, 100)
    rec['points'] += gain
    rec['last'] = today
    data[uid] = rec
    _save(data)
    await event.reply(f"✅ 签到成功! +{gain} 积分, 共 {rec['points']} 分")


@handler(r'^积分$', name='查积分')
async def my_points(event, match):
    rec = _load().get(str(event.user_id), {'points': 0})
    await event.reply(f"你的积分: {rec['points']}")
```

---

更多问题欢迎加入交流群 **[164178653](https://qm.qq.com/q/nepv1UcwRE)** 讨论。
