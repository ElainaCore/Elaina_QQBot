# ElainaQQ OneBot v11 API 参考文档

本文档面向 ElainaQQ 插件开发者，说明 OneBot 动作的调用入口、账号路由、消息格式、响应结构和框架提供的常用封装。

> ElainaQQ 负责规范化并路由动作，但动作是否真正可用，仍取决于目标 OneBot 实现、QQ 登录状态、账号权限和客户端版本。本文列出封装或登记的动作，不代表每种连接都完整实现。

## 目录

- [1. 调用模型](#1-调用模型)
  - [1.1 显式封装](#11-显式封装)
  - [1.2 通用 call_api](#12-通用-call_api)
  - [1.3 动态方法](#13-动态方法)
- [2. 多账号路由](#2-多账号路由)
  - [2.1 传输选择](#21-传输选择)
- [3. 响应与错误处理](#3-响应与错误处理)
  - [3.1 常见框架错误](#31-常见框架错误)
- [4. 消息格式](#4-消息格式)
  - [4.1 常用消息段](#41-常用消息段)
  - [4.2 字符串与 CQ 码](#42-字符串与-cq-码)
  - [4.3 文件参数](#43-文件参数)
- [5. 发送与回复](#5-发送与回复)
- [6. 常用封装方法](#6-常用封装方法)
- [7. 通用与动态动作](#7-通用与动态动作)
- [8. 事件中的 API 调用](#8-事件中的-api-调用)
- [9. 合并转发与文件](#9-合并转发与文件)
- [10. 扩展动作与内联键盘](#10-扩展动作与内联键盘)
- [11. 出站 API 中间件](#11-出站-api-中间件)
- [12. 排错清单](#12-排错清单)

---

## 1. 调用模型

插件应从 `core.plugins` 获取 API 对象：

~~~python
from core.plugins import get_api

api = get_api()
result = await api.get_login_info(self_id='10001')
~~~

`get_api()` 返回连接到当前框架 OneBot 适配器的 `OneBotAPI`。通常不需要自行实例化 `OneBotAPI`。

有三种调用方式。

### 1.1 显式封装

对常用动作使用带参数签名的方法：

~~~python
result = await api.send_group_msg(
    123456,
    'Hello',
    self_id='10001',
)
~~~

显式封装会对常见 ID 执行整数转换，并按动作需要构造参数字典。

### 1.2 通用 call_api

`call_api()` 可以调用任何动作，不受登记动作清单限制：

~~~python
result = await api.call_api(
    'get_group_info',
    {'group_id': 123456, 'no_cache': True},
    self_id='10001',
)
~~~

签名：

~~~text
await api.call_api(
    action: str,
    params: dict | None = None,
    self_id: str | None = None,
)
~~~

### 1.3 动态方法

没有显式封装的方法可以直接按动作名调用，参数使用关键字传递：

~~~python
result = await api.get_recent_contact(
    count=20,
    self_id='10001',
)
~~~

这等价于：

~~~python
result = await api.call_api(
    'get_recent_contact',
    {'count': 20},
    self_id='10001',
)
~~~

动态方法不提供参数名校验。动作名或参数写错时，错误由目标实现返回。

---

## 2. 多账号路由

每次 API 调用只路由到一个机器人账号。框架按以下方式确定 `self_id`：

1. 调用中显式传入的 `self_id` 或兼容参数 `_self_id`。
2. 当前事件处理链已经固定的账号。
3. 适配器能够确定的默认账号。

在消息处理器中，`event.reply()` 和 `event.call_api()` 会自动使用 `event.self_id`：

~~~python
@handler(r'^资料$', name='群资料', group_only=True)
async def group_info(event, match):
    result = await event.call_api(
        'get_group_info',
        {'group_id': event.group_id},
    )
    await event.reply(str(result.get('data')))
~~~

在后台任务、插件 HTTP 路由、通知或请求处理器中，主动调用时应显式传入账号：

~~~python
await get_api().send_private_msg(
    20002,
    '任务完成',
    self_id='10001',
)
~~~

不要依赖“当前第一个在线账号”。多账号上线顺序变化后，默认路由可能不再符合业务预期。

### 2.1 传输选择

目标账号确定后，框架按以下顺序尝试动作：

1. 内置 QQ 为该账号注册的本地动作。
2. 该账号对应的 WebSocket 连接。
3. 匹配该账号的 HTTP API 客户端。

一次调用不会同时广播到多个传输。需要向多个账号发送时，应显式遍历账号并分别调用。

HTTP 客户端连接在多账号环境中应配置 `self_id`。否则框架可能无法把动作可靠地映射到正确客户端。

---

## 3. 响应与错误处理

框架把本地动作、WebSocket 和 HTTP 的结果统一为 OneBot 风格字典：

~~~python
{
    'status': 'ok',
    'retcode': 0,
    'data': {...},
    'message': '',
    'wording': '',
}
~~~

失败示例：

~~~python
{
    'status': 'failed',
    'retcode': 1404,
    'data': None,
    'message': '机器人未连接或接口不可用',
    'wording': '机器人未连接或接口不可用',
}
~~~

应同时检查 `status` 和 `retcode`：

~~~python
result = await api.set_group_ban(
    group_id=123456,
    user_id=20002,
    duration=600,
    self_id=event.self_id,
)

if result.get('status') != 'ok' or result.get('retcode') != 0:
    reason = result.get('message') or result.get('wording') or '未知错误'
    await event.reply(f'操作失败：{reason}')
~~~

不要假设 `data` 一定是字典。查询动作可能返回列表、标量或 `None`，具体结构由动作和底层实现决定。

### 3.1 常见框架错误

| 情况 | 结果 |
| --- | --- |
| OneBot 适配器尚未初始化 | 失败响应，通常为 `retcode=1500` |
| 没有可用机器人或接口 | 失败响应，通常为 `retcode=1404` |
| WebSocket 动作 30 秒未响应 | 超时失败响应 |
| 连接在等待过程中断 | 连接中断失败响应 |
| 底层抛出异常 | 异常文本被规范化为失败响应 |

底层 QQ 原生接口有时把真实错误放在 `data`、`rsp` 或 `payload` 中。框架会识别常见错误码和错误文本，并把它们提升为外层失败响应。

---

## 4. 消息格式

ElainaQQ 内部使用 OneBot 数组消息：

~~~python
[
    {'type': 'text', 'data': {'text': '你好，'}},
    {'type': 'at', 'data': {'qq': 20002}},
]
~~~

每个消息段包含：

- `type`：小写消息段类型。
- `data`：该类型的参数字典。

框架会保留未知消息段，是否能发送由目标实现决定。`voice` 和 `audio` 会规范化为 `record`。

### 4.1 常用消息段

| 类型 | 常用 data | 说明 |
| --- | --- | --- |
| `text` | `{'text': '内容'}` | 纯文本 |
| `at` | `{'qq': 20002}` | @成员；`qq='all'` 通常表示 @全体 |
| `reply` | `{'id': 123}` | 引用消息 |
| `image` | `{'file': '...'}` | 图片 URL、文件或 Base64，能力依赖实现 |
| `record` | `{'file': '...'}` | 语音 |
| `video` | `{'file': '...'}` | 视频 |
| `face` | `{'id': 1}` | QQ 表情 |
| `file` | `{'file': '...'}` | 文件段，部分实现只支持专用上传动作 |
| `json` | `{'data': '...'}` | JSON 卡片 |
| `xml` | `{'data': '...'}` | XML 卡片 |
| `markdown` | `{'content': '...'}` | Markdown 扩展段 |
| `music` | `{'type': 'qq', 'id': '...'}` | 音乐卡片 |
| `node` | `{'nickname': '...', 'content': [...]}` | 合并转发节点 |
| `forward` | `{'id': '...'}` | 已存在的合并转发 |

其他 QQ 扩展段如 `miniapp`、`mface`、`onlinefile`、`flashtransfer`、`contact`、`location`、`dice`、`rps` 和 `poke` 也会被规范化层保留，但参数和发送能力应以当前底层实现为准。

### 4.2 字符串与 CQ 码

直接调用发送动作并传入字符串时，框架默认解析其中的 CQ 码：

~~~python
await api.send_group_msg(
    123456,
    '你好 [CQ:at,qq=20002]',
    self_id='10001',
)
~~~

设置 `auto_escape=True` 会把整段字符串作为纯文本：

~~~python
await api.send_group_msg(
    123456,
    '[CQ:image,file=https://example.com/a.png]',
    auto_escape=True,
    self_id='10001',
)
~~~

`event.reply('...')` 会先把字符串包装为 `text` 段，因此其中的 CQ 码按普通文字发送。需要用 `event.reply()` 发送复杂内容时，直接传消息段数组：

~~~python
await event.reply([
    {'type': 'reply', 'data': {'id': event.message_id}},
    {'type': 'text', 'data': {'text': '收到'}},
])
~~~

### 4.3 文件参数

图片、语音、视频和文件通常使用以下形式之一：

~~~python
{'type': 'image', 'data': {'file': 'https://example.com/a.png'}}
{'type': 'image', 'data': {'file': 'file:///C:/images/a.png'}}
{'type': 'image', 'data': {'file': 'base64://...'}}
~~~

可接受的协议、路径可见性和大小限制由底层实现决定。外部 OneBot 运行在另一台机器或容器中时，本机文件路径通常不可见，应改用 URL、Base64 或上传动作。

---

## 5. 发送与回复

### 5.1 回复当前消息

只有 `MessageEvent` 提供回复便捷方法：

~~~python
await event.reply('普通文本')
await event.reply_text('普通文本')
await event.reply_image('https://example.com/image.png')
~~~

`reply()` 接受字符串或消息段数组，并自动选择群聊或私聊目标。额外关键字会继续传给 `send_group_msg` 或 `send_private_msg`。

### 5.2 发送群消息

~~~python
await api.send_group_msg(
    group_id=123456,
    message=[
        {'type': 'text', 'data': {'text': '构建完成'}},
        {'type': 'image', 'data': {'file': 'https://example.com/report.png'}},
    ],
    self_id='10001',
)
~~~

签名：`send_group_msg(group_id, message, **kwargs)`。

### 5.3 发送私聊消息

~~~python
await api.send_private_msg(
    user_id=20002,
    message='你好',
    self_id='10001',
)
~~~

签名：`send_private_msg(user_id, message, **kwargs)`。

### 5.4 通用发送

~~~python
await api.send_msg('group', 123456, '群消息', self_id='10001')
await api.send_msg('private', 20002, '私聊消息', self_id='10001')
~~~

签名：`send_msg(message_type, target_id, message, **kwargs)`。`message_type='group'` 时使用 `group_id`，其他值按私聊构造 `user_id`；推荐只传 `group` 或 `private`。

### 5.5 撤回和查询消息

~~~python
await api.delete_msg(message_id=123, self_id='10001')
detail = await api.get_msg(message_id=123, self_id='10001')
~~~

对应封装：

| 方法 | 动作 |
| --- | --- |
| `delete_msg(message_id)` | `delete_msg` |
| `get_msg(message_id)` | `get_msg` |
| `set_msg_emoji_like(message_id, emoji_id, enable=True)` | `set_msg_emoji_like` |
| `send_poke(user_id, group_id=None)` | `send_poke` |
| `mark_group_msg_as_read(group_id)` | `mark_group_msg_as_read` |
| `mark_private_msg_as_read(user_id)` | `mark_private_msg_as_read` |

---

## 6. 常用封装方法

以下方法由 `OneBotAPI` 提供显式封装。所有异步封装均可额外传入 `self_id` 或 `_self_id` 选择账号，即使签名表中省略该参数。

### 6.1 账号与联系人

| 方法 | 说明 |
| --- | --- |
| `get_login_info()` | 获取登录账号信息 |
| `get_stranger_info(user_id, **kwargs)` | 获取用户信息 |
| `get_friend_list(no_cache=False, **kwargs)` | 获取好友列表 |
| `get_unidirectional_friend_list()` | 获取单向好友列表 |
| `send_like(user_id, times=1)` | 给用户点赞 |
| `delete_friend(user_id)` | 删除好友 |
| `set_qq_avatar(file)` | 设置账号头像 |
| `set_qq_profile(**kwargs)` | 设置账号资料 |
| `ocr_image(image)` | 调用图片 OCR |

示例：

~~~python
friends = await api.get_friend_list(
    no_cache=True,
    self_id=event.self_id,
)
~~~

### 6.2 群信息与成员

| 方法 | 说明 |
| --- | --- |
| `get_group_list(no_cache=False, **kwargs)` | 获取群列表 |
| `get_group_info(group_id, **kwargs)` | 获取群信息 |
| `get_group_member_list(group_id, no_cache=False, **kwargs)` | 获取成员列表 |
| `get_group_member_info(group_id, user_id, no_cache=True, **kwargs)` | 获取成员信息 |
| `get_group_honor_info(group_id, honor_type='all')` | 获取群荣誉 |
| `get_group_at_all_remain(group_id)` | 获取 @全体剩余次数 |
| `get_group_system_msg()` | 获取群系统消息 |

### 6.3 群管理

| 方法 | 说明 |
| --- | --- |
| `set_group_kick(group_id, user_id, reject_add=False)` | 移出成员；`reject_add` 映射为拒绝再次申请参数 |
| `set_group_ban(group_id, user_id, duration=1800)` | 禁言，`duration=0` 通常表示解除 |
| `set_group_whole_ban(group_id, enable=True)` | 全群禁言开关 |
| `set_group_card(group_id, user_id, card='')` | 设置群名片 |
| `set_group_name(group_id, group_name)` | 设置群名 |
| `set_group_admin(group_id, user_id, enable=True)` | 设置或取消管理员 |
| `set_group_special_title(group_id, user_id, special_title='')` | 设置群头衔 |
| `set_group_leave(group_id, is_dismiss=False)` | 退群或解散群 |
| `set_group_portrait(group_id, file)` | 设置群头像 |
| `set_group_sign(group_id)` | 群签到 |

群管理动作需要机器人具备相应群权限。插件应在业务层验证调用者权限，不要只依赖 `owner_only` 或 QQ 返回错误。

### 6.4 请求处理

| 方法 | 说明 |
| --- | --- |
| `set_friend_add_request(flag, approve=True)` | 处理好友请求 |
| `set_group_add_request(flag, sub_type, approve=True)` | 处理加群申请或邀请 |

~~~python
@handler(r'.*', event_types=['request.group'])
async def approve_group_request(event, match):
    result = await get_api().set_group_add_request(
        flag=event.flag,
        sub_type=event.sub_type,
        approve=True,
        self_id=event.self_id,
    )
~~~

请求事件没有 `event.call_api()`，应使用 `get_api()`。

### 6.5 精华消息

| 方法 | 说明 |
| --- | --- |
| `get_essence_msg_list(group_id)` | 获取精华消息列表 |
| `set_essence_msg(message_id)` | 设置精华消息 |
| `delete_essence_msg(message_id)` | 移除精华消息 |

### 6.6 历史消息

| 方法 | 说明 |
| --- | --- |
| `get_group_msg_history(group_id, message_seq=0, count=20, reverse_order=False, **kwargs)` | 获取群历史 |
| `get_friend_msg_history(user_id, message_seq=0, count=20, reverse_order=False, **kwargs)` | 获取私聊历史 |

封装把 `reverse_order` 发送为扩展参数 `reverseOrder`。分页语义、最大 `count` 和起始序号由目标实现决定。

### 6.7 系统与凭据

| 方法 | 说明 |
| --- | --- |
| `get_version_info()` | 获取 OneBot 实现版本 |
| `get_status()` | 获取运行状态 |
| `can_send_image()` | 查询图片发送能力 |
| `can_send_record()` | 查询语音发送能力 |
| `get_cookies(domain='qun.qq.com')` | 获取指定域名 Cookie |
| `get_csrf_token()` | 获取 CSRF Token |
| `get_credentials(domain='qun.qq.com')` | 获取组合凭据 |
| `clean_cache()` | 请求清理缓存 |

Cookie、CSRF Token 和其他凭据属于敏感信息。不要写入普通日志、消息、插件页面或公开 API 响应。

---

## 7. 通用与动态动作

`call_api()` 不使用动作白名单。即使动作不在 `OneBotAPI.supported_actions()` 中，框架也会尝试发送：

~~~python
result = await api.call_api(
    'vendor_specific_action',
    {'option': True},
    self_id='10001',
)
~~~

登记动作清单可以用于调试或生成界面：

~~~python
actions = OneBotAPI.supported_actions()
~~~

该清单表示框架已知的 OneBot 标准动作和 QQ 扩展动作，不是当前账号的实时能力探测，也不是传输层白名单。

动作名会在发送前移除常见兼容后缀 `_async` 和 `_rate_limited`。发送动作中的消息会统一规范化为数组格式。

### 7.1 何时用显式封装

优先使用显式封装，因为它能：

- 统一常用参数名。
- 对 QQ 号、群号等 ID 做基础转换。
- 降低构造 OneBot 参数字典时的拼写错误。

以下场景使用 `call_api()` 或动态方法：

- 目标实现新增了框架尚未封装的动作。
- 需要传递封装未暴露的扩展参数。
- 插件本身要实现通用 OneBot 控制台或代理层。

动态方法只接受关键字参数。如果调用方式需要位置参数，应改用 `call_api()`。

---

## 8. 事件中的 API 调用

### 8.1 消息事件

`MessageEvent` 提供：

- `event.reply(message, **kwargs)`
- `event.reply_text(text, **kwargs)`
- `event.reply_image(file, **kwargs)`
- `event.call_api(action, params=None)`

它们都会绑定 `event.self_id`。

~~~python
@handler(r'^禁言\s+(\d+)\s+(\d+)$', owner_only=True, group_only=True)
async def ban_member(event, match):
    user_id = int(match.group(1))
    duration = int(match.group(2))
    result = await event.call_api('set_group_ban', {
        'group_id': event.group_id,
        'user_id': user_id,
        'duration': duration,
    })
    if result.get('status') == 'ok':
        await event.reply('操作完成')
    else:
        await event.reply(f"操作失败：{result.get('message', '未知错误')}")
~~~

### 8.2 通知、请求和元事件

`NoticeEvent`、`RequestEvent` 和 `MetaEvent` 没有回复与调用便捷方法。使用 `get_api()` 并传入事件账号：

~~~python
@handler(r'.*', event_types=['notice.group_increase'])
async def welcome(event, match):
    await get_api().send_group_msg(
        event.group_id,
        f'欢迎 {event.user_id}',
        self_id=event.self_id,
    )
~~~

### 8.3 后台任务

创建后台任务前复制业务需要的标量，不要长期持有完整事件：

~~~python
self_id = str(event.self_id)
group_id = int(event.group_id)

async def notify_later():
    await asyncio.sleep(10)
    await get_api().send_group_msg(
        group_id,
        '十秒已到',
        self_id=self_id,
    )

asyncio.create_task(notify_later())
~~~

插件仍需跟踪自己创建的任务，并在 `@on_unload` 中取消它们。

---

## 9. 合并转发与文件

### 9.1 合并转发

| 方法 | 说明 |
| --- | --- |
| `send_forward_msg(messages, **kwargs)` | 通用合并转发动作 |
| `send_group_forward_msg(group_id, messages, **kwargs)` | 发送群合并转发 |
| `send_private_forward_msg(user_id, messages, **kwargs)` | 发送私聊合并转发 |
| `get_forward_msg(message_id)` | 获取合并转发内容 |

示例：

~~~python
nodes = [
    {
        'type': 'node',
        'data': {
            'user_id': 10001,
            'nickname': 'Elaina',
            'content': [
                {'type': 'text', 'data': {'text': '第一条'}},
            ],
        },
    },
    {
        'type': 'node',
        'data': {
            'user_id': 10001,
            'nickname': 'Elaina',
            'content': '第二条',
        },
    },
]

await api.send_group_forward_msg(
    123456,
    nodes,
    self_id='10001',
)
~~~

节点字段和嵌套消息兼容性因实现而异。收到 `forward` 段后，通常把其中的 `id` 或实现提供的资源 ID 传给 `get_forward_msg`。

### 9.2 群文件与私聊文件

| 方法 | 说明 |
| --- | --- |
| `upload_group_file(group_id, file, name, folder='')` | 上传群文件 |
| `upload_private_file(user_id, file, name)` | 上传私聊文件 |
| `get_group_root_files(group_id)` | 获取群文件根目录 |
| `get_group_files_by_folder(group_id, folder_id)` | 获取文件夹内容 |
| `get_group_file_url(group_id, file_id, busid=None)` | 获取群文件 URL |
| `delete_group_file(group_id, file_id, busid=None)` | 删除群文件 |
| `create_group_file_folder(group_id, name)` | 创建群文件夹 |

~~~python
result = await api.upload_group_file(
    group_id=123456,
    file='C:/reports/daily.pdf',
    name='daily.pdf',
    self_id='10001',
)
~~~

文件路径必须对执行动作的 OneBot 实现可见。远程 HTTP 或 WebSocket 实现通常无法访问 ElainaQQ 主机上的本地路径。

---

## 10. 扩展动作与内联键盘

框架登记了大量 QQ 扩展动作，包括群公告、相册、闪传、在线文件、收藏、状态、原始发包和 AI 语音等。使用前应先在目标实现的文档或 `get_version_info` 中确认能力。

例如，调用扩展动作：

~~~python
result = await api.call_api(
    'get_group_notice',
    {'group_id': 123456},
    self_id='10001',
)
~~~

### 10.1 读取官方机器人内联键盘

`OneBotAPI` 提供高级辅助方法：

~~~python
buttons = await api.get_inline_keyboard_buttons(
    group_id=123456,
    message_id=789,
    real_seq=None,
    bot_appid='',
    self_id='10001',
)
~~~

该方法先尝试从 `get_msg` 响应读取框架附加的键盘数据；必要时通过 `send_packet` 获取群消息原始数据并解析按钮。目标实现必须支持相关原始发包能力，否则返回空列表。

参数：

| 参数 | 说明 |
| --- | --- |
| `group_id` | 群号 |
| `message_id` | 消息 ID |
| `real_seq` | 可选的真实消息序号；未提供时先查询消息 |
| `bot_appid` | 可选的官方机器人 AppID，用于补充按钮来源 |

此能力依赖 QQ 协议细节，不应作为跨 OneBot 实现的通用契约。

---

## 11. 出站 API 中间件

插件可使用 `@api_interceptor` 观察、修改或接管其他插件的出站调用。完整注册方式见[插件开发指南](PLUGIN_DEVELOPMENT.md#64-出站-api-中间件)。

中间件收到的 `ApiCallRequest` 已完成动作名和消息格式规范化：

~~~python
from core.plugins import api_interceptor


@api_interceptor(priority=50)
async def audit_send(request, call_next):
    if request.action in {'send_group_msg', 'send_private_msg'}:
        ctx.log.info(
            'plugin=%s self_id=%s action=%s',
            request.source_plugin,
            request.self_id,
            request.action,
        )
    return await call_next()
~~~

安全注意事项：

- 不要记录消息正文、Cookie、Token 或文件内容，除非业务明确需要且已有访问控制和保留策略。
- 修改 `request.self_id` 可能改变目标账号，应谨慎使用。
- 接管调用时返回规范的 OneBot 响应。
- 中间件调用 OneBot API 时使用 `bypass_api_interceptors()`，避免递归。
- `call_next()` 在同一个中间件中只能调用一次。

---

## 12. 排错清单

### 12.1 API 返回未连接或不可用

依次检查：

1. 目标 QQ 是否在线。
2. 调用中的 `self_id` 是否与面板显示的账号一致。
3. 对应 WebSocket 或 HTTP 客户端连接是否启用。
4. HTTP 客户端在多账号环境中是否填写 `self_id`。
5. 底层实现是否实现该动作。

### 12.2 能发文本，不能发图片或文件

检查目标实现支持的 `file` 形式、文件大小、路径可见性、URL 可访问性和账号权限。容器、远程主机与 Windows 服务账号常常看不到开发终端中的本地路径。

### 12.3 调用了错误账号

所有后台任务、通知、请求和 Web 路由中的主动调用都显式传入 `self_id`。消息处理器优先使用 `event.reply()` 或 `event.call_api()`。

### 12.4 动作返回 ok，但业务没有生效

检查 `data`、`rsp` 或 `payload` 中是否有底层错误字段，并确认账号权限。框架会提升常见原生错误，但无法识别每个第三方实现的所有私有响应结构。

### 12.5 动态调用参数错误

动态方法不做参数校验。对照目标实现的动作文档，或改用显式封装。调试日志中不要输出鉴权头和完整敏感响应。

### 12.6 选择动作的原则

- 回复当前消息：使用 `event.reply()`。
- 当前消息上下文中的任意动作：使用 `event.call_api()`。
- 后台任务、通知、请求和跨会话调用：使用 `get_api()` 并传入 `self_id`。
- 常用动作：优先显式封装。
- 厂商扩展动作：使用 `call_api()`，并针对失败响应做降级。

插件的加载、生命周期、数据文件和 Web 扩展请参阅[插件开发指南](PLUGIN_DEVELOPMENT.md)。
