"""
示例插件 — 展示 v2 异步插件开发方式

插件使用 @handler 装饰器注册处理器, 所有处理函数均为 async def(event, match) 签名。
"""

from core.plugin.decorators import handler, on_load, on_unload


@on_load
async def init():
    """插件加载时执行"""
    pass


@on_unload
async def cleanup():
    """插件卸载时执行"""
    pass


@handler(r'^ping$', name='ping', desc='响应 ping 命令')
async def handle_ping(event, match):
    """响应 ping 命令"""
    await event.reply('pong')


@handler(r'^echo\s+(.+)$', name='echo', desc='回显用户输入')
async def handle_echo(event, match):
    """回显用户输入的内容"""
    text = match.group(1)
    await event.reply(text)


# 拦截示例：两个处理器注册同一规则，高优先级处理器设置 block=True 后会阻止低优先级处理器运行。
@handler(r'^拦截示例$', name='拦截示例-高优先级', desc='block=True 命中即拦截后续插件', priority=10, block=True)
async def block_demo_high(event, match):
    await event.reply('🛑 高优先级处理器 (block=True): 已拦截, 低优先级不会再触发')


@handler(r'^拦截示例$', name='拦截示例-低优先级', desc='被高优先级 block 拦截, 不会触发', priority=0)
async def block_demo_low(event, match):
    await event.reply('⬇️ 低优先级处理器: 你不应该看到这条 (已被 block 拦截)')
