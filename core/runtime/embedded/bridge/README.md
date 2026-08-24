# ElainaQQ QQ 运行时

`elainaqq-runtime.mjs` 由 ElainaQQ 加载器载入 QQ 进程，通过 QQ 原生接口建立会话，
并使用本机回环 HTTP 向 ElainaQQ 上报事件与动作结果。

每个账号拥有独立的本机桥接端口，默认从 `30010` 开始依次分配。端口仅绑定
`127.0.0.1`，用于框架与 QQ 运行时通信，不作为公网 OneBot 接口。

Windows、Linux 和 macOS 共用同一套 ElainaQQ 运行时桥接协议。

内置 QQ 管理器直接暴露红包能力，不通过 OneBot 扩展动作或通知：

```python
manager = get_app().embedded_qq
manager.register_red_packet_listener('plugin_name', on_red_packet)
result = await manager.grab_red_packet(self_id, bill_no)
manager.unregister_red_packet_listener('plugin_name')
```

红包回调参数为 `(self_id, packet)`。`packet` 包含 `bill_no`、群与发送者信息、
红包类型、口令和祝福语；领取结果包含 `ok`、`amount`、`err_code` 和 `err_msg`。

消息监听优先使用 QQNT 的在线消息标记，并以每次登录后的监听注册时间作为兼容
边界。QQ 内核同步的历史消息、无有效实时依据的消息以及同一会话中的重复回调
不会上报到框架，也不会触发插件。
