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


def normalize_action_response(response: Any, *, action: str = '') -> dict[str, Any]:
    """将内置 QQ、WebSocket 和 HTTP 的结果收敛为同一种结构。"""
    if not isinstance(response, dict):
        return action_failed('机器人未连接或接口不可用', 1404)

    normalized = dict(response)
    status = str(normalized.get('status') or '').lower()
    try:
        retcode = int(normalized.get('retcode', 0 if status != 'failed' else 1500))
    except (TypeError, ValueError):
        retcode = 1500

    # QQNT 原生接口可能被包装成外层 OneBot success，但把真正的错误放在
    # data.result/errMsg 中；Elaina 在 action 层统一检查这一层。
    nested = None
    for candidate in (normalized.get('data'), normalized.get('rsp'), normalized.get('payload')):
        if isinstance(candidate, dict):
            nested = candidate
            break
    if status != 'failed' and nested is not None:
        nested_code = next(
            (nested.get(key) for key in ('retcode', 'retCode', 'code', 'errCode', 'result')
             if isinstance(nested.get(key), (int, float, str)) and str(nested.get(key)).strip()),
            None,
        )
        try:
            nested_retcode = int(nested_code) if nested_code is not None else 0
        except (TypeError, ValueError):
            nested_retcode = 0
        has_native_error = any(nested.get(key) for key in (
            'errMsg', 'retMsg', 'clientWording', 'error', 'errorMessage'
        ))
        if nested_retcode != 0 and (action == 'send_packet' or has_native_error):
            message = str(
                nested.get('errMsg') or nested.get('retMsg') or nested.get('message')
                or nested.get('clientWording') or normalized.get('message') or normalized.get('wording')
                or f'OneBot 原生接口失败 ({nested_retcode})'
            )
            return action_failed(message, nested_retcode)

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
