"""Compare member overlap across multiple QQ groups from the Web panel."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from aiohttp import ContentTypeError, web

from core.plugins import current_plugin, get_api, register_page, register_route

__plugin_meta__ = {
    'name': '重复群成员查询',
    'version': '1.0.0',
    'author': 'ElainaQQ',
    'description': '在 Web 面板选择多个群，查询并汇总同时存在于多个群的成员。',
}

_ctx = current_plugin()
_MAX_GROUPS = 50
_FETCH_CONCURRENCY = 4
_MAX_KICK_TARGETS = 200
_KICK_CONCURRENCY = 4

register_page(
    key='group-member-overlap',
    label='重复群成员',
    source='plugin',
    source_name=_ctx.name,
    html_file=_ctx.get_resource_path('panel.html'),
    icon='people',
)


def _error(message: str, *, status: int = 400, **fields: Any) -> web.Response:
    return web.json_response(
        {'success': False, 'message': message, 'error': message, **fields},
        status=status,
    )


def _onebot_data(response: Any, action_label: str) -> Any:
    if not isinstance(response, dict):
        raise RuntimeError(f'{action_label}未返回有效响应')
    if response.get('status') != 'ok' or str(response.get('retcode', -1)) != '0':
        detail = response.get('wording') or response.get('message') or 'OneBot 接口调用失败'
        raise RuntimeError(f'{action_label}失败：{detail}')
    return response.get('data')


def _identity(value: Any, label: str) -> str:
    text = str(value or '').strip()
    if not text or not text.isdigit() or len(text) > 20:
        raise ValueError(f'{label}格式无效')
    return text


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def _json_object(request: web.Request) -> dict[str, Any]:
    if request.content_length is not None and request.content_length > 64 * 1024:
        raise ValueError('请求正文不能超过 64 KB')
    try:
        body = await request.json()
    except (ContentTypeError, ValueError) as exc:
        raise ValueError('请求正文必须是 JSON 对象') from exc
    if not isinstance(body, dict):
        raise ValueError('请求正文必须是 JSON 对象')
    return body


@register_route('GET', '/api/ext/group-member-overlap/groups', timeout=45)
async def list_groups(request: web.Request) -> web.Response:
    try:
        self_id = _identity(request.query.get('self_id'), '机器人账号')
        response = await get_api().get_group_list(no_cache=True, self_id=self_id)
        raw_groups = _onebot_data(response, '获取群列表')
        if not isinstance(raw_groups, list):
            raise RuntimeError('获取群列表未返回数组')
    except ValueError as exc:
        return _error(str(exc))
    except RuntimeError as exc:
        return _error(str(exc), status=502)

    groups = []
    for item in raw_groups:
        if not isinstance(item, dict):
            continue
        group_id = str(item.get('group_id') or '').strip()
        if not group_id:
            continue
        groups.append(
            {
                'group_id': group_id,
                'group_name': str(item.get('group_name') or group_id),
                'member_count': _integer(item.get('member_count')),
                'max_member_count': _integer(item.get('max_member_count')),
            }
        )
    groups.sort(key=lambda item: (item['group_name'].casefold(), item['group_id']))
    return web.json_response({'success': True, 'groups': groups})


def _member_name(member: dict[str, Any]) -> str:
    return str(member.get('card') or member.get('nickname') or member.get('user_id') or '')


def _member_entry(member: dict[str, Any], group_id: str) -> dict[str, Any]:
    return {
        'group_id': group_id,
        'card': str(member.get('card') or ''),
        'nickname': str(member.get('nickname') or ''),
        'role': str(member.get('role') or 'member'),
        'join_time': _integer(member.get('join_time')),
        'last_sent_time': _integer(member.get('last_sent_time')),
    }


async def _fetch_members(
    self_id: str,
    group_id: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[dict[str, Any]] | None, str]:
    try:
        async with semaphore:
            response = await get_api().get_group_member_list(
                int(group_id),
                no_cache=True,
                self_id=self_id,
            )
        data = _onebot_data(response, f'获取群 {group_id} 成员')
        if not isinstance(data, list):
            raise RuntimeError(f'群 {group_id} 的成员数据不是数组')
        return group_id, [item for item in data if isinstance(item, dict)], ''
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _ctx.log.warning('获取群 %s 成员失败: %s', group_id, exc)
        return group_id, None, str(exc)


@register_route('POST', '/api/ext/group-member-overlap/compare', timeout=180)
async def compare_members(request: web.Request) -> web.Response:
    try:
        body = await _json_object(request)
        self_id = _identity(body.get('self_id'), '机器人账号')
        raw_group_ids = body.get('group_ids')
        if not isinstance(raw_group_ids, list):
            raise ValueError('group_ids 必须是数组')
        group_ids = list(dict.fromkeys(_identity(value, '群号') for value in raw_group_ids))
        if len(group_ids) < 2:
            raise ValueError('请至少选择两个不同的群')
        if len(group_ids) > _MAX_GROUPS:
            raise ValueError(f'一次最多对比 {_MAX_GROUPS} 个群')
        exclude_self = body.get('exclude_self', True) is not False
    except ValueError as exc:
        return _error(str(exc))

    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
    fetched = await asyncio.gather(
        *(_fetch_members(self_id, group_id, semaphore) for group_id in group_ids)
    )
    successful: dict[str, list[dict[str, Any]]] = {}
    failed: list[dict[str, str]] = []
    for group_id, members, error in fetched:
        if members is None:
            failed.append({'group_id': group_id, 'message': error})
        else:
            successful[group_id] = members

    if len(successful) < 2:
        return _error(
            '成功获取的群不足两个，无法进行对比',
            status=502,
            failed_groups=failed,
        )

    appearances: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str, str] = {}
    total_members = 0
    for group_id, members in successful.items():
        seen_in_group: set[str] = set()
        for member in members:
            user_id = str(member.get('user_id') or '').strip()
            if not user_id or user_id in seen_in_group:
                continue
            seen_in_group.add(user_id)
            if exclude_self and user_id == self_id:
                continue
            total_members += 1
            appearances[user_id].append(_member_entry(member, group_id))
            candidate = _member_name(member)
            if candidate and (user_id not in names or member.get('card')):
                names[user_id] = candidate

    duplicates = [
        {
            'user_id': user_id,
            'display_name': names.get(user_id, user_id),
            'group_count': len(groups),
            'groups': groups,
        }
        for user_id, groups in appearances.items()
        if len(groups) >= 2
    ]
    duplicates.sort(
        key=lambda item: (
            -item['group_count'],
            item['display_name'].casefold(),
            item['user_id'],
        )
    )

    return web.json_response(
        {
            'success': True,
            'duplicates': duplicates,
            'failed_groups': failed,
            'stats': {
                'requested_groups': len(group_ids),
                'compared_groups': len(successful),
                'member_records': total_members,
                'unique_members': len(appearances),
                'duplicate_members': len(duplicates),
            },
        }
    )


async def _kick_member(
    self_id: str,
    user_id: str,
    group_id: str,
    reject_add: bool,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    try:
        async with semaphore:
            response = await get_api().set_group_kick(
                int(group_id),
                int(user_id),
                reject_add=reject_add,
                self_id=self_id,
            )
        _onebot_data(response, f'从群 {group_id} 移出用户 {user_id}')
        return {'user_id': user_id, 'group_id': group_id, 'success': True, 'message': ''}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _ctx.log.warning('从群 %s 移出用户 %s 失败: %s', group_id, user_id, exc)
        return {
            'user_id': user_id,
            'group_id': group_id,
            'success': False,
            'message': str(exc),
        }


@register_route('POST', '/api/ext/group-member-overlap/kick', timeout=180)
async def kick_members(request: web.Request) -> web.Response:
    try:
        body = await _json_object(request)
        self_id = _identity(body.get('self_id'), '机器人账号')
        raw_targets = body.get('targets')
        if not isinstance(raw_targets, list):
            raise ValueError('targets 必须是数组')
        targets: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                raise ValueError('移群目标格式无效')
            user_id = _identity(raw_target.get('user_id'), '用户 QQ')
            group_id = _identity(raw_target.get('group_id'), '群号')
            if user_id == self_id:
                raise ValueError('不能将机器人账号自身移出群')
            target = (user_id, group_id)
            if target not in seen:
                seen.add(target)
                targets.append(target)
        if not targets:
            raise ValueError('没有选择要执行的用户和群')
        if len(targets) > _MAX_KICK_TARGETS:
            raise ValueError(f'一次最多执行 {_MAX_KICK_TARGETS} 个移群操作')
        reject_add = body.get('reject_add') is True
    except ValueError as exc:
        return _error(str(exc))

    semaphore = asyncio.Semaphore(_KICK_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _kick_member(self_id, user_id, group_id, reject_add, semaphore)
            for user_id, group_id in targets
        )
    )
    success_count = sum(1 for item in results if item['success'])
    failed_count = len(results) - success_count
    return web.json_response(
        {
            'success': True,
            'all_succeeded': failed_count == 0,
            'success_count': success_count,
            'failed_count': failed_count,
            'results': results,
        }
    )
