# QLinux 渠道 (Lagrange 协议端)

基于 Lagrange.Core 的 Linux 协议端，作为 ElainaQQ 的原生渠道运行。协议行为 100% 使用原版
Lagrange.Core（不重写协议栈），通过多 bot JSON-RPC runner 与框架桥接。

## 架构

```
ElainaQQ (Python, core/runtime/qlinux/)
  └─ RunnerRPC (stdin/stdout JSON-RPC)
      └─ runner 二进制 (C# Lagrange.Core, 自包含单文件)
          ├─ 多 BotContext (多账号并存, keystore 隔离)
          └─ SignProvider → 签名服务器 (默认 https://esign.linsur.cn/)
```

## 二进制分发

**编译产物不进仓库**。用户首次启用 QLinux 渠道时自动下载:

1. 从 `ElainaCore/lagrange-runner` GitHub Releases 下载对应平台压缩包
2. 失败时自动走镜像回退链 (ghproxy.cc / gh-proxy.com / gh.llkk.cc)
3. 解压到 `data/qlinux/bin/`

| 平台 | 产物 | 体积 |
|------|------|------|
| windows-x64 | lagrange-runner-vX-win-x64.zip | ~37 MB |
| linux-x64 | lagrange-runner-vX-linux-x64.tar.gz | ~38 MB |

## 配置 (`config/settings.yaml`)

```yaml
qlinux:
  enabled: true                                # 启用 QLinux 渠道
  sign_server: "https://esign.linsur.cn/"      # NTQQ 签名服务器 (可换任意兼容端)
```

## 支持的登录方式

| 方式 | API | 说明 |
|------|-----|------|
| 扫码 | `POST /api/qlinux/login/qr` | 面板轮询 `/api/qlinux/qr` 显示二维码 |
| 账密 | `POST /api/qlinux/login/password` | 触发滑块时提交 ticket (可能触发风控) |
| 短信 | `POST /api/qlinux/submit {type: sms}` | 账密流程中的短信验证码 |
| 滑块 | `POST /api/qlinux/submit {type: captcha}` | 账密流程中的人机验证 ticket |

## Web API 一览

```
GET  /api/qlinux/accounts            账号列表
POST /api/qlinux/create              创建账号实例 {bot_id}
POST /api/qlinux/login/qr            扫码登录 {bot_id}
POST /api/qlinux/login/password      账密登录 {bot_id, uin, password}
GET  /api/qlinux/qr?bot_id=x         获取当前二维码 (png_base64 + url + status)
POST /api/qlinux/submit              提交验证 {bot_id, type, ticket/randstr/code}
POST /api/qlinux/stop                下线 {bot_id} (保留 keystore)
POST /api/qlinux/delete              删除 {bot_id} (清 keystore)
```

## 支持的 OneBot 动作 (插件侧无感调用)

- `send_group_msg` / `send_private_msg` / `send_msg` — 支持 text / at / at_all / image(base64 或 URL) / json 段
- `get_login_info`
- `delete_msg` (群消息近期窗口撤回)

## 消息事件映射

runner 事件 `message` → OneBot v11 标准形状:

| runner 字段 | OneBot 字段 |
|-------------|-------------|
| `data.contact.group_uin` | `group_id` (有则为群消息) |
| `data.contact.uin/nickname/card` | `sender.user_id/nickname/card` |
| `data.contact.permission` | `sender.role` (Owner→owner / Admin→admin / 其余→member) |
| `data.entities[].type=text/mention/image/record/json/reply` | `message[]` text/at/image/record/json/reply |
| `data.sequence` | `message_id` (格式 `bot_id:g|p:seq`) |
| `data.time` | `time` |
| `data.self_uin` / 顶层 `uin` | `self_id` |

登录/离线/二维码状态机事件由 manager 内部消化 (`qr.code` 缓存供面板拉取),
`bot.online`/`bot.offline` 同时转换为 OneBot meta/notice 事件进管线。

## runner RPC 协议 (参考)

每行一个 JSON, stdin 请求 / stdout 响应+事件 / stderr 日志:

```
→ {"id":"1","method":"bot.create","params":{"bot_id":"a1"}}
← {"id":"1","result":{"bot_id":"a1","created":true}}
← {"event":"qr.code","bot_id":"a1","url":"https://txz.qq.com/p?k=...","png_base64":"..."}
← {"event":"qr.state","bot_id":"a1","state":"WaitingForScan"}
← {"event":"login.result","bot_id":"a1","success":true,"state":0}
← {"event":"bot.online","bot_id":"a1","uin":123456,"reason":"Login"}
← {"event":"message","bot_id":"a1","uin":123456,"data":{...}}
```

方法: `ping` / `bot.create` / `bot.login.qr` / `bot.login.password` /
`bot.submit.captcha` / `bot.submit.sms` / `bot.stop` / `bot.list` /
`msg.send.group` / `msg.send.private` / `msg.send.group.image` /
`msg.send.segments` (text/at/at_all/image/json) / `msg.recall`

## runner 源码与发布

源码在 `qqsign` 仓库的 `lagrange/runner-win/`。发布流程:

```powershell
dotnet publish runner-win.csproj -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true
# 同理 linux-x64; 打包 zip / tar.gz 上传 GitHub Releases, tag 对应 RUNNER_VERSION
```
