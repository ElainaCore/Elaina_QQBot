# OneBot v11 API

本文档只记录框架统一后的调用边界；动作最终是否可用取决于目标账号、权限和底层实现。

## 获取 API

```python
from core.plugins import get_api

api = get_api()
result = await api.get_login_info(self_id='10001')
```

也可以使用通用调用或动态方法：

```python
await api.call_api('get_group_info', {'group_id': 123456}, self_id='10001')
await api.get_group_info(group_id=123456, self_id='10001')
```

## 账号路由

`self_id` 选择顺序为：显式参数、当前事件账号、唯一可确定账号；多账号且无法确定时拒绝随机路由。

四种渠道都使用同一动作入口：

```text
内置 QQ / QQ 注入 / OneBot / Lagrange
              -> OneBotAPI -> 本地动作或网络传输
```

事件中的 `event.reply()` 和 `event.call_api()` 自动携带当前 `self_id`。

## 响应

成功响应通常为：

```json
{"status":"ok","retcode":0,"data":{}}
```

失败响应通常为：

```json
{"status":"failed","retcode":1400,"data":null,"message":"...","wording":"..."}
```

判断成功必须同时检查 `status` 和 `retcode`：

```python
if result.get('status') != 'ok' or result.get('retcode') != 0:
    logger.warning('调用失败: %s', result.get('message'))
```

## 消息段

文本可以直接传字符串，也可以使用标准消息段数组：

```python
message = [
    {'type': 'text', 'data': {'text': '你好'}},
    {'type': 'at', 'data': {'qq': '123456'}},
    {'type': 'image', 'data': {'file': 'https://example.com/a.png'}},
]
await api.send_group_msg(123456, message, self_id='10001')
```

常用段：

| 类型 | 关键字段 |
| --- | --- |
| `text` | `text` |
| `at` | `qq` 或 `all` |
| `image` | `file`、`url`、`summary` |
| `record` | `file` |
| `video` | `file` |
| `file` | `file`、`name` |
| `reply` | `id` |
| `json` | `data` |
| `xml` | `data` |

框架会保留未知消息段；渠道只负责把自身格式转换为标准段。

## 常用动作

| 动作 | 主要参数 |
| --- | --- |
| `send_private_msg` | `user_id`, `message` |
| `send_group_msg` | `group_id`, `message` |
| `send_msg` | `message_type`, `user_id` 或 `group_id`, `message` |
| `delete_msg` | `message_id` |
| `get_msg` | `message_id` |
| `get_login_info` | 无 |
| `get_status` | 无 |
| `get_friend_list` | 无 |
| `get_group_list` | 无 |
| `get_group_info` | `group_id` |
| `get_group_member_info` | `group_id`, `user_id` |
| `set_group_kick` | `group_id`, `user_id` |
| `set_group_ban` | `group_id`, `user_id`, `duration` |
| `set_friend_add_request` | `flag`, `approve`, `remark` |

未列出的动作可以通过 `call_api()` 透传到目标 OneBot 实现。

## 回复事件

```python
@handler(r'^状态$')
async def status(event, match):
    await event.reply('运行正常')
```

群聊回复使用 `send_group_msg`，私聊回复使用 `send_private_msg`；自身消息、通知、请求和元事件仍沿用同一 API。

## 文件参数

- `base64://...` 支持内联二进制。
- `http://` 和 `https://` 支持远程资源。
- 本地路径应只用于可信的本地动作，公开接口不要接受任意路径。

远程图片和归档下载均有大小限制，失败时返回统一的 OneBot 错误响应。

## 事件模型

事件固定字段包括：

```text
time, self_id, post_type, event_type, source, channel, raw_data, extra
```

消息事件再提供：

```text
message_type, sub_type, message_id, message_seq, real_seq,
user_id, group_id, message, raw_message, sender, content
```

事件类型使用精确名称：`message`、`message_sent`、`notice.<type>`、`request.<type>` 和 `meta_event.<type>`。

## 排错

1. 检查账号是否在线。
2. 多账号调用明确传入 `self_id`。
3. 检查动作参数类型和消息段格式。
4. 检查目标渠道是否实现该动作。
5. 查看 Web 面板日志和统一响应中的 `retcode`、`message`。
