"""QLinux OneBot 管理动作映射。"""

from __future__ import annotations


def admin_action(action: str, params: dict) -> tuple[str, dict]:
    """映射常用 OneBot 管理动作。"""
    group_id = int(params.get('group_id', 0) or 0)
    user_id = int(params.get('user_id', 0) or 0)
    mapping = {
        'set_group_kick': ('bot.group.kick', {
            'group_uin': group_id, 'member_uin': user_id,
            'reject_add': bool(params.get('reject_add_request', False)),
            'reason': str(params.get('reason') or ''),
        }),
        'set_group_ban': ('bot.group.ban', {
            'group_uin': group_id, 'member_uin': user_id,
            'duration': max(0, int(params.get('duration', 1800))),
        }),
        'set_group_whole_ban': ('bot.group.whole_ban', {
            'group_uin': group_id, 'enable': bool(params.get('enable', True)),
        }),
        'set_group_card': ('bot.group.card', {
            'group_uin': group_id, 'member_uin': user_id,
            'card': str(params.get('card') or ''),
        }),
        'set_group_special_title': ('bot.group.special_title', {
            'group_uin': group_id, 'member_uin': user_id,
            'title': str(params.get('special_title') or ''),
        }),
        'set_group_name': ('bot.group.name', {
            'group_uin': group_id, 'name': str(params.get('group_name') or ''),
        }),
        'set_group_leave': ('bot.group.leave', {'group_uin': group_id}),
        'group_poke': ('bot.group.poke', {
            'group_uin': group_id, 'member_uin': user_id,
        }),
        'friend_poke': ('bot.friend.poke', {'user_uin': user_id}),
    }
    try:
        return mapping[action]
    except KeyError as exc:
        raise ValueError(f'QLinux 暂不支持动作: {action}') from exc
