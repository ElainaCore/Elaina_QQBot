# ElainaQQ QQ 运行时

`elainaqq-runtime.mjs` 由 ElainaQQ 加载器载入 QQ 进程，通过 QQ 原生接口建立会话，
并使用本机回环 HTTP 向 ElainaQQ 上报事件与动作结果。

每个账号拥有独立的本机桥接端口，默认从 `30010` 开始依次分配。端口仅绑定
`127.0.0.1`，用于框架与 QQ 运行时通信，不作为公网 OneBot 接口。

Windows、Linux 和 macOS 共用同一套 ElainaQQ 运行时桥接协议。
