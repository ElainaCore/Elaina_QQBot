# QLinux（Lagrange）渠道

QLinux 使用 Lagrange.Core runner 提供协议登录和消息收发，Python 只负责账号生命周期、JSON-RPC 和 OneBot 适配。

## 链路

```text
Python Manager -> RunnerRPC -> lagrange-runner -> Lagrange.Core
```

runner 首次使用时从固定 Release 下载到运行数据目录，并校验路径、链接、文件数量和解压大小。

## 登录接口

| 方法 | 用途 |
| --- | --- |
| `POST /api/qlinux/create` | 创建账号实例 |
| `POST /api/qlinux/login/qr` | 发起扫码登录 |
| `POST /api/qlinux/login/password` | 发起账密登录 |
| `POST /api/qlinux/submit` | 提交验证码或滑块票据 |
| `GET /api/qlinux/qr` | 获取二维码状态 |
| `POST /api/qlinux/stop` | 停止账号 |
| `POST /api/qlinux/delete` | 删除账号和 keystore |

## 事件

runner 消息会转换为标准 OneBot `message` 或 `message_sent`；在线、离线和生命周期事件会转换为 `meta_event` 或 `notice`。

支持文本、at、图片、语音、视频、文件、回复、JSON、XML 和未知扩展消息段。

## 动作

常用动作包括 `send_group_msg`、`send_private_msg`、`send_msg`、`get_login_info`、`get_group_list`、`get_group_info`、`delete_msg` 和 `get_msg`。

不支持的动作返回统一失败响应，不会静默成功。

## runner RPC

```text
请求: {"id":"q1","method":"bot.create","params":{"bot_id":"a1"}}
响应: {"id":"q1","result":{"created":true}}
事件: {"event":"message","bot_id":"a1","data":{}}
```

每行一个 JSON；stdout 只传协议数据，stderr 传诊断日志。

## 安全边界

- runner 归档只允许普通文件和目录，拒绝路径穿越与链接。
- 远程图片下载限制协议和大小，并在线程中执行。
- 登录密码和签名地址只通过受保护的面板接口传入。
