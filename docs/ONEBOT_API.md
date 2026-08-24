# OneBot v11 API 完整参考文档

## 📖 概述

ElainaQQ 框架已完全暴露 OneBot v11 标准 API 及常见扩展接口。所有方法均可通过 `OneBotAPI` 类调用。

**文件位置：** `core/protocols/onebot/api.py`

---

## 🚀 快速开始

### 基础用法

```python
from core.plugins import OneBotAPI

# 创建 API 实例
api = OneBotAPI()

# 调用方法
result = await api.send_group_msg(group_id=123456, message="Hello World")
print(result)  # {'status': 'ok', 'retcode': 0, 'data': {...}}
```

### 高级用法

```python
# 1. 使用 call_api 调用任意 action
result = await api.call_api('get_group_info', {'group_id': 123456})

# 2. 动态调用（任意 OneBot action）
result = await api.some_custom_action(param1='value1', param2='value2')

# 3. 指定 self_id（多账号场景）
result = await api.call_api('send_group_msg', {'group_id': 123456, 'message': 'Hi'}, self_id='10001')
```

---

## 📋 API 方法列表

### 1️⃣ 消息相关 (Message)

#### `send_group_msg(group_id, message, **kwargs)`
发送群消息

**参数：**
- `group_id` (int): 群号
- `message` (str | list): 消息内容（文本或消息段数组）
- `**kwargs`: 额外参数（如 `auto_escape`）

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {'message_id': 123456}
}
```

**示例：**
```python
# 发送文本
await api.send_group_msg(123456, "Hello")

# 发送图片
await api.send_group_msg(123456, [
    {"type": "text", "data": {"text": "图片："}},
    {"type": "image", "data": {"file": "file:///path/to/image.jpg"}}
])
```

---

#### `send_private_msg(user_id, message, **kwargs)`
发送私聊消息

**参数：**
- `user_id` (int): 用户 QQ 号
- `message` (str | list): 消息内容
- `**kwargs`: 额外参数

**示例：**
```python
await api.send_private_msg(10001, "你好")
```

---

#### `send_msg(message_type, target_id, message, **kwargs)`
发送消息（通用）

**参数：**
- `message_type` (str): 消息类型 `'group'` 或 `'private'`
- `target_id` (int): 目标 ID（群号或 QQ 号）
- `message` (str | list): 消息内容

**示例：**
```python
await api.send_msg('group', 123456, "Hello")
await api.send_msg('private', 10001, "Hi")
```

---

#### `delete_msg(message_id)`
撤回消息

**参数：**
- `message_id` (int): 消息 ID

**示例：**
```python
await api.delete_msg(123456)
```

---

#### `get_msg(message_id)`
获取消息详情

**参数：**
- `message_id` (int): 消息 ID

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'message_id': 123456,
        'real_id': 123456,
        'sender': {...},
        'message': [...]
    }
}
```

---

#### `send_forward_msg(messages, **kwargs)`
发送合并转发消息

**参数：**
- `messages` (list): 消息节点列表

**示例：**
```python
await api.send_forward_msg([
    {'type': 'node', 'data': {'user_id': 10001, 'nickname': 'Alice', 'content': 'Hello'}},
    {'type': 'node', 'data': {'user_id': 10002, 'nickname': 'Bob', 'content': 'Hi'}}
], group_id=123456)
```

---

#### `send_group_forward_msg(group_id, messages, **kwargs)`
发送群合并转发

**参数：**
- `group_id` (int): 群号
- `messages` (list): 消息节点列表

---

#### `send_private_forward_msg(user_id, messages, **kwargs)`
发送私聊合并转发

**参数：**
- `user_id` (int): 用户 QQ 号
- `messages` (list): 消息节点列表

---

#### `get_forward_msg(message_id)`
获取合并转发内容

**参数：**
- `message_id` (str): 合并转发 ID

---

#### `get_group_msg_history(group_id, message_seq=0, count=20, reverse_order=False)`
获取群消息历史

**参数：**
- `group_id` (int): 群号
- `message_seq` (int): 起始消息序号（0 表示最新）
- `count` (int): 获取数量
- `reverse_order` (bool): 是否倒序

**示例：**
```python
history = await api.get_group_msg_history(123456, count=50)
```

---

#### `get_friend_msg_history(user_id, message_seq=0, count=20, reverse_order=False)`
获取私聊消息历史

**参数：**
- `user_id` (int): 用户 QQ 号
- `message_seq` (int): 起始消息序号
- `count` (int): 获取数量
- `reverse_order` (bool): 是否倒序

---

#### `mark_group_msg_as_read(group_id)`
标记群消息已读

**参数：**
- `group_id` (int): 群号

---

#### `mark_private_msg_as_read(user_id)`
标记私聊消息已读

**参数：**
- `user_id` (int): 用户 QQ 号

---

#### `set_msg_emoji_like(message_id, emoji_id, enable=True)`
设置消息表情回应

**参数：**
- `message_id` (int): 消息 ID
- `emoji_id` (str): 表情 ID
- `enable` (bool): 是否添加（False 为移除）

**示例：**
```python
# 点赞消息
await api.set_msg_emoji_like(123456, '128077', True)
```

---

#### `send_poke(user_id, group_id=None)`
发送戳一戳

**参数：**
- `user_id` (int): 目标 QQ 号
- `group_id` (int, 可选): 群号（群聊戳一戳）

**示例：**
```python
# 私聊戳一戳
await api.send_poke(10001)

# 群聊戳一戳
await api.send_poke(10001, group_id=123456)
```

---

### 2️⃣ 账号信息 (Account)

#### `get_login_info()`
获取登录账号信息

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'user_id': 10001,
        'nickname': 'Bot昵称'
    }
}
```

---

#### `get_stranger_info(user_id)`
获取陌生人信息

**参数：**
- `user_id` (int): 用户 QQ 号

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'user_id': 10001,
        'nickname': '昵称',
        'sex': 'male',
        'age': 20
    }
}
```

---

#### `get_friend_list()`
获取好友列表

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': [
        {'user_id': 10001, 'nickname': 'Alice', 'remark': '备注'},
        {'user_id': 10002, 'nickname': 'Bob', 'remark': ''}
    ]
}
```

---

#### `get_unidirectional_friend_list()`
获取单向好友列表

**返回：** 同 `get_friend_list()`

---

### 3️⃣ 群组管理 (Group)

#### `get_group_list()`
获取群列表

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': [
        {'group_id': 123456, 'group_name': '群名称', 'member_count': 100},
        {'group_id': 789012, 'group_name': '另一个群', 'member_count': 50}
    ]
}
```

---

#### `get_group_info(group_id)`
获取群信息

**参数：**
- `group_id` (int): 群号

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'group_id': 123456,
        'group_name': '群名称',
        'member_count': 100,
        'max_member_count': 200
    }
}
```

---

#### `get_group_member_list(group_id)`
获取群成员列表

**参数：**
- `group_id` (int): 群号

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': [
        {'user_id': 10001, 'nickname': 'Alice', 'card': '群名片', 'role': 'owner'},
        {'user_id': 10002, 'nickname': 'Bob', 'card': '', 'role': 'member'}
    ]
}
```

---

#### `get_group_member_info(group_id, user_id)`
获取群成员信息

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'group_id': 123456,
        'user_id': 10001,
        'nickname': 'Alice',
        'card': '群名片',
        'role': 'admin',
        'join_time': 1609459200
    }
}
```

---

#### `set_group_kick(group_id, user_id, reject_add=False)`
踢出群成员

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号
- `reject_add` (bool): 是否拒绝再次加群

**示例：**
```python
# 踢出成员
await api.set_group_kick(123456, 10001)

# 踢出并拒绝再次加群
await api.set_group_kick(123456, 10001, reject_add=True)
```

---

#### `set_group_ban(group_id, user_id, duration=1800)`
禁言群成员

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号
- `duration` (int): 禁言时长（秒），0 为解除禁言

**示例：**
```python
# 禁言 30 分钟
await api.set_group_ban(123456, 10001, duration=1800)

# 解除禁言
await api.set_group_ban(123456, 10001, duration=0)
```

---

#### `set_group_whole_ban(group_id, enable=True)`
全群禁言

**参数：**
- `group_id` (int): 群号
- `enable` (bool): 是否开启全群禁言

**示例：**
```python
# 开启全群禁言
await api.set_group_whole_ban(123456, enable=True)

# 关闭全群禁言
await api.set_group_whole_ban(123456, enable=False)
```

---

#### `set_group_card(group_id, user_id, card='')`
设置群名片

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号
- `card` (str): 群名片（空字符串表示删除）

**示例：**
```python
await api.set_group_card(123456, 10001, card="新名片")
```

---

#### `set_group_name(group_id, group_name)`
设置群名

**参数：**
- `group_id` (int): 群号
- `group_name` (str): 新群名

**示例：**
```python
await api.set_group_name(123456, "新群名称")
```

---

#### `set_group_admin(group_id, user_id, enable=True)`
设置群管理员

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号
- `enable` (bool): True 为设置，False 为取消

**示例：**
```python
# 设置管理员
await api.set_group_admin(123456, 10001, enable=True)

# 取消管理员
await api.set_group_admin(123456, 10001, enable=False)
```

---

#### `set_group_special_title(group_id, user_id, special_title='')`
设置群头衔

**参数：**
- `group_id` (int): 群号
- `user_id` (int): 用户 QQ 号
- `special_title` (str): 头衔（空字符串表示删除）

**示例：**
```python
await api.set_group_special_title(123456, 10001, special_title="最佳贡献")
```

---

#### `set_group_leave(group_id, is_dismiss=False)`
退出群聊

**参数：**
- `group_id` (int): 群号
- `is_dismiss` (bool): 是否解散（仅群主可用）

**示例：**
```python
# 退出群聊
await api.set_group_leave(123456)

# 解散群（群主）
await api.set_group_leave(123456, is_dismiss=True)
```

---

#### `set_group_portrait(group_id, file)`
设置群头像

**参数：**
- `group_id` (int): 群号
- `file` (str): 图片文件路径或 URL

**示例：**
```python
await api.set_group_portrait(123456, file="file:///path/to/avatar.jpg")
```

---

#### `set_group_sign(group_id)`
群签到

**参数：**
- `group_id` (int): 群号

---

#### `get_group_honor_info(group_id, honor_type='all')`
获取群荣誉信息

**参数：**
- `group_id` (int): 群号
- `honor_type` (str): 荣誉类型 `'all'` | `'talkative'` | `'performer'` | `'legend'` | `'strong_newbie'` | `'emotion'`

**示例：**
```python
# 获取所有荣誉
await api.get_group_honor_info(123456, honor_type='all')

# 获取龙王
await api.get_group_honor_info(123456, honor_type='talkative')
```

---

#### `get_group_at_all_remain(group_id)`
获取 @全体成员 剩余次数

**参数：**
- `group_id` (int): 群号

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'can_at_all': True,
        'remain_at_all_count_for_group': 10,
        'remain_at_all_count_for_uin': 5
    }
}
```

---

#### `get_group_system_msg()`
获取群系统消息

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'invited_requests': [...],
        'join_requests': [...]
    }
}
```

---

#### `get_essence_msg_list(group_id)`
获取精华消息列表

**参数：**
- `group_id` (int): 群号

---

#### `set_essence_msg(message_id)`
设置精华消息

**参数：**
- `message_id` (int): 消息 ID

---

#### `delete_essence_msg(message_id)`
删除精华消息

**参数：**
- `message_id` (int): 消息 ID

---

### 4️⃣ 请求处理 (Request)

#### `set_friend_add_request(flag, approve=True)`
处理好友请求

**参数：**
- `flag` (str): 请求 flag（从事件中获取）
- `approve` (bool): 是否同意

**示例：**
```python
# 同意好友请求
await api.set_friend_add_request(flag="abc123", approve=True)

# 拒绝好友请求
await api.set_friend_add_request(flag="abc123", approve=False)
```

---

#### `set_group_add_request(flag, sub_type, approve=True)`
处理加群请求

**参数：**
- `flag` (str): 请求 flag
- `sub_type` (str): 请求类型 `'add'` 或 `'invite'`
- `approve` (bool): 是否同意

**示例：**
```python
# 同意加群请求
await api.set_group_add_request(flag="abc123", sub_type="add", approve=True)

# 拒绝加群邀请
await api.set_group_add_request(flag="abc123", sub_type="invite", approve=False)
```

---

### 5️⃣ 用户操作 (User)

#### `send_like(user_id, times=1)`
点赞

**参数：**
- `user_id` (int): 用户 QQ 号
- `times` (int): 点赞次数（1-10）

**示例：**
```python
# 点赞 10 次
await api.send_like(10001, times=10)
```

---

#### `delete_friend(user_id)`
删除好友

**参数：**
- `user_id` (int): 用户 QQ 号

---

#### `set_qq_avatar(file)`
设置 QQ 头像

**参数：**
- `file` (str): 图片文件路径或 URL

**示例：**
```python
await api.set_qq_avatar(file="file:///path/to/avatar.jpg")
```

---

#### `set_qq_profile(**kwargs)`
设置 QQ 资料

**参数：**
- `**kwargs`: 资料字段（如 `nickname`, `personal_note` 等）

**示例：**
```python
await api.set_qq_profile(nickname="新昵称", personal_note="这是签名")
```

---

#### `ocr_image(image)`
图片 OCR 识别

**参数：**
- `image` (str): 图片文件路径或 URL

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'texts': [
            {'text': '识别的文字', 'confidence': 0.98}
        ]
    }
}
```

---

### 6️⃣ 文件操作 (File)

#### `upload_group_file(group_id, file, name, folder='')`
上传群文件

**参数：**
- `group_id` (int): 群号
- `file` (str): 文件路径
- `name` (str): 文件名
- `folder` (str): 父目录 ID（可选）

**示例：**
```python
await api.upload_group_file(123456, file="/path/to/file.pdf", name="文档.pdf")
```

---

#### `upload_private_file(user_id, file, name)`
上传私聊文件

**参数：**
- `user_id` (int): 用户 QQ 号
- `file` (str): 文件路径
- `name` (str): 文件名

---

#### `get_group_root_files(group_id)`
获取群根目录文件列表

**参数：**
- `group_id` (int): 群号

---

#### `get_group_files_by_folder(group_id, folder_id)`
获取群文件夹内文件列表

**参数：**
- `group_id` (int): 群号
- `folder_id` (str): 文件夹 ID

---

#### `get_group_file_url(group_id, file_id, busid=None)`
获取群文件下载链接

**参数：**
- `group_id` (int): 群号
- `file_id` (str): 文件 ID
- `busid` (int, 可选): 文件类型

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'url': 'https://...'
    }
}
```

---

#### `delete_group_file(group_id, file_id, busid=None)`
删除群文件

**参数：**
- `group_id` (int): 群号
- `file_id` (str): 文件 ID
- `busid` (int, 可选): 文件类型

---

#### `create_group_file_folder(group_id, name)`
创建群文件夹

**参数：**
- `group_id` (int): 群号
- `name` (str): 文件夹名

---

### 7️⃣ 系统相关 (System)

#### `get_version_info()`
获取版本信息

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'app_name': 'OneBot实现名称',
        'app_version': '1.0.0',
        'protocol_version': 'v11'
    }
}
```

---

#### `get_status()`
获取运行状态

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'online': True,
        'good': True
    }
}
```

---

#### `can_send_image()`
检查是否可以发送图片

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {'yes': True}
}
```

---

#### `can_send_record()`
检查是否可以发送语音

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {'yes': True}
}
```

---

#### `get_cookies(domain='')`
获取 Cookies

**参数：**
- `domain` (str): 域名（可选）

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'cookies': 'cookie_string'
    }
}
```

---

#### `get_csrf_token()`
获取 CSRF Token

**返回：**
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {
        'token': 123456
    }
}
```

---

#### `clean_cache()`
清理缓存

---

## 🔧 动态调用

### 使用 `call_api()` 调用任意 action

```python
# 调用任意 OneBot action
result = await api.call_api('custom_action', {
    'param1': 'value1',
    'param2': 'value2'
})
```

### 使用 `__getattr__()` 动态调用

```python
# 自动将方法名转换为 action
result = await api.custom_action(param1='value1', param2='value2')

# 等价于
result = await api.call_api('custom_action', {'param1': 'value1', 'param2': 'value2'})
```

**示例：QQ 扩展 action**
```python
# QQ 的自定义 action
result = await api.nc_get_robot_uin_range()
result = await api.nc_get_user_status(user_id=10001)
result = await api.ArkSharePeer(group_id=123456, app_name='com.tencent.miniapp')
```

---

## 📊 响应格式

所有 API 调用统一返回格式：

### 成功响应
```python
{
    'status': 'ok',
    'retcode': 0,
    'data': {...}  # 具体数据
}
```

### 失败响应
```python
{
    'status': 'failed',
    'retcode': 1404,  # 错误码
    'message': '错误信息',
    'wording': '用户可读的错误描述'
}
```

### 空响应
```python
None  # 连接失败或超时
```

---

## 🔌 连接方式

### 1. 内置 QQ Bridge（推荐）
通过 `EmbeddedQQManager` 启动本地 QQ 子进程，API 调用直接走本地 HTTP。

```python
# 框架自动路由到本地 bridge
api = OneBotAPI()
result = await api.send_group_msg(123456, "Hello")
```

### 2. 外部 OneBot WebSocket
连接到外部 OneBot 实现。

```python
# 自动路由到 WebSocket 连接
api = OneBotAPI()
result = await api.send_group_msg(123456, "Hello")
```

### 3. 外部 OneBot HTTP
通过 HTTP POST 调用外部 OneBot API。

```python
# 自动回退到 HTTP 客户端
api = OneBotAPI()
result = await api.send_group_msg(123456, "Hello")
```

**优先级：** 本地 Bridge > WebSocket > HTTP

---

## 💡 最佳实践

### 1. 错误处理

```python
result = await api.send_group_msg(123456, "Hello")
if result and result.get('status') == 'ok':
    print("发送成功")
else:
    print(f"发送失败: {result.get('message')}")
```

### 2. 多账号场景

```python
# 指定 self_id
result = await api.call_api('send_group_msg', {
    'group_id': 123456,
    'message': 'Hello'
}, self_id='10001')
```

### 3. 批量操作

```python
import asyncio

# 并发发送消息
tasks = [
    api.send_group_msg(123456, "消息1"),
    api.send_group_msg(789012, "消息2"),
    api.send_private_msg(10001, "消息3")
]
results = await asyncio.gather(*tasks)
```

### 4. 使用消息段

```python
# CQ 码格式（字符串）
await api.send_group_msg(123456, "[CQ:image,file=https://...]")

# 消息段格式（数组）
await api.send_group_msg(123456, [
    {"type": "text", "data": {"text": "图片："}},
    {"type": "image", "data": {"file": "https://..."}}
])
```

---

## 📚 相关文档

- [OneBot v11 标准](https://github.com/botuniverse/onebot-11)
- [消息段 (CQ 码) 规范](https://github.com/botuniverse/onebot-11/blob/master/message/segment.md)

---

## 🎯 总结

- ✅ **完全暴露** OneBot v11 标准 API
- ✅ **60+ 预封装方法** 开箱即用
- ✅ **动态调用** 支持任意 OneBot action
- ✅ **多连接支持** 本地 Bridge / WebSocket / HTTP
- ✅ **类型提示** 完整的参数和返回值说明
- ✅ **零学习成本** 与 OneBot 标准完全一致

**文件路径：** `core/protocols/onebot/api.py`
**作者：** ElainaQQ 团队  
**更新日期：** 2026-08-21
