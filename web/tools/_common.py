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


def primary_bot_qq() -> str:
    """当前主要连接的机器人 QQ (用于按 QQ 分库的消息/事件记录)"""
    ids = connected_ids()
    return ids[0] if ids else ''


async def query_log(log_type: str, sql: str, params=None, bot_qq: str = '') -> list:
    svc = log_service()
    if not svc:
        return []
    return await svc.query(log_type, sql, params, bot_qq=bot_qq)


# ── 昵称缓存 (通过 OneBot get_stranger_info) ──

_nick_cache: dict[str, tuple[float, str]] = {}
_NICK_TTL = 600


async def get_nickname(user_id: str) -> str:
    uid = str(user_id)
    if not uid:
        return ''
    now = time.time()
    c = _nick_cache.get(uid)
    if c and now - c[0] < _NICK_TTL:
        return c[1]

    name = ''
    try:
        from core.onebot.api import get_api

        resp = await get_api().get_stranger_info(uid)
        if resp and resp.get('retcode') == 0:
            name = (resp.get('data') or {}).get('nickname', '') or ''
    except Exception:
        name = ''
    if not name:
        name = f'用户{uid[-6:]}' if len(uid) >= 6 else f'用户{uid}'
    _nick_cache[uid] = (now, name)
    return name


async def batch_nicknames(user_ids) -> dict:
    result = {}
    for uid in {str(u) for u in user_ids if u}:
        result[uid] = await get_nickname(uid)
    return result
