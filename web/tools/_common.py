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
    """返回适配器统一维护的已连接账号标识。"""
    ad = adapter()
    if not ad:
        return []
    if hasattr(ad, 'connected_self_ids'):
        return list(ad.connected_self_ids())
    # 兼容旧版适配器，避免公共工具在热升级期间中断。
    ids = set(ad.local_actions.keys()) | set(ad.websockets.keys()) | set(ad.bots.keys())
    return sorted(i for i in ids if not str(i).startswith('forward:'))


def bot_ids() -> list:
    """返回适配器统一维护的账号标识，供面板查询使用。"""
    return connected_ids()


def resolve_bot_qq(value: str = '') -> str:
    """通过适配器统一解析账号别名到真实 self_id。"""
    requested = str(value or '')
    ad = adapter()
    if ad is not None:
        return str(ad.resolve_self_id(requested) or requested)
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
        from core.protocols.onebot.api import get_api

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
