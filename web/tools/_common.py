"""工具模块共享辅助"""

import time

_app = None
_base_dir = ''


def set_app(app_instance, base_dir=''):
    global _app, _base_dir
    _app = app_instance
    if base_dir:
        _base_dir = base_dir


def get_app():
    return _app


def base_dir():
    return _base_dir


def adapter():
    return getattr(_app, 'adapter', None) if _app else None


def log_service():
    return getattr(_app, 'log_service', None) if _app else None


def connected_ids() -> list:
    """已连接的 self_id 列表 (即机器人 QQ); 过滤正向连接的临时占位 id"""
    ad = adapter()
    if not ad:
        return []
    ids = set(ad.websockets.keys()) | set(ad.bots.keys())
    ids = {i for i in ids if not str(i).startswith('forward:')}
    return sorted(ids)


def bot_ids() -> list:
    """返回已连接账号与内置账号编号，供面板查询使用。"""
    ids = set(connected_ids())
    manager = getattr(_app, 'embedded_qq', None)
    if manager:
        ids.update(str(bot.uin or bot.bot_id) for bot in manager.bots.values())
    return sorted(item for item in ids if item)


def resolve_bot_qq(value: str = '') -> str:
    """将内置 QQ 的配置编号解析为实际 QQ，避免查询到错误的日志分库。"""
    requested = str(value or '')
    manager = getattr(_app, 'embedded_qq', None)
    if manager:
        for bot in manager.bots.values():
            actual = str(bot.uin or bot.bot_id or '')
            if requested in (str(bot.bot_id or ''), str(bot.uin or '')):
                return actual
    return requested


def primary_bot_qq() -> str:
    """当前主要连接的机器人 QQ (用于按 QQ 分库的消息/事件记录)"""
    ids = bot_ids()
    return ids[0] if ids else ''


async def query_log(log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
    svc = log_service()
    if not svc:
        return []
    return await svc.query(log_type, sql, params, bot_qq=resolve_bot_qq(bot_qq))


# ── 昵称缓存 (通过 OneBot get_stranger_info) ──

_nick_cache: dict[tuple[str, str], tuple[float, str]] = {}
_NICK_TTL = 600


async def get_nickname(user_id: str, bot_qq: str = '') -> str:
    uid = str(user_id)
    if not uid:
        return ''
    bot_id = resolve_bot_qq(bot_qq)
    cache_key = (bot_id, uid)
    now = time.time()
    c = _nick_cache.get(cache_key)
    if c and now - c[0] < _NICK_TTL:
        return c[1]

    name = ''
    try:
        from core.onebot.api import get_api

        resp = await get_api().get_stranger_info(uid, self_id=bot_id or None)
        if resp and resp.get('retcode') == 0:
            name = (resp.get('data') or {}).get('nickname', '') or ''
    except Exception:
        name = ''
    if not name:
        name = f'用户{uid[-6:]}' if len(uid) >= 6 else f'用户{uid}'
    _nick_cache[cache_key] = (now, name)
    return name


async def batch_nicknames(user_ids, bot_qq: str = '') -> dict:
    result = {}
    for uid in {str(u) for u in user_ids if u}:
        result[uid] = await get_nickname(uid, bot_qq)
    return result
