"""OneBot v11 请求和响应的统一契约。"""

from typing import Any


def action_ok(data: Any = None, **extra) -> dict[str, Any]:
    """构造标准成功响应。"""
    return {
        'status': 'ok',
        'retcode': 0,
        'data': data,
        'message': '',
        'wording': '',
        **extra,
    }


def action_failed(message: str, retcode: int = 1500, **extra) -> dict[str, Any]:
    """构造标准失败响应。"""
    text = str(message or 'OneBot 动作执行失败')
    return {
        'status': 'failed',
        'retcode': int(retcode),
        'data': None,
        'message': text,
        'wording': text,
        **extra,
    }


def normalize_action_response(response: Any) -> dict[str, Any]:
    """将内置 QQ、WebSocket 和 HTTP 的结果收敛为同一种结构。"""
    if not isinstance(response, dict):
        return action_failed('机器人未连接或接口不可用', 1404)

    normalized = dict(response)
    status = str(normalized.get('status') or '').lower()
    try:
        retcode = int(normalized.get('retcode', 0 if status != 'failed' else 1500))
    except (TypeError, ValueError):
        retcode = 1500

    success = status != 'failed' and retcode == 0
    normalized['status'] = 'ok' if success else 'failed'
    normalized['retcode'] = 0 if success else retcode or 1500
    normalized.setdefault('data', None)
    message = str(normalized.get('message') or normalized.get('wording') or '')
    normalized['message'] = message
    normalized['wording'] = str(normalized.get('wording') or message)
    return normalized


def action_succeeded(response: Any) -> bool:
    """判断规范化前后的动作结果是否成功。"""
    normalized = normalize_action_response(response)
    return normalized['status'] == 'ok' and normalized['retcode'] == 0
