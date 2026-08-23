"""数据库浏览器 — 查询/浏览/删除 (OneBot)"""

import logging
import os
import re
import sqlite3

from aiohttp import web

from core.base.zipsafe import is_within
from web.protocol import json_body

log = logging.getLogger('ElainaQQ.web.database')

_app = None
_base_dir = ''
_READ_PATTERN = re.compile(r'^\s*(SELECT|PRAGMA|EXPLAIN|WITH)\b', re.IGNORECASE)


def set_context(app_instance, base_dir: str):
    global _app, _base_dir
    _app = app_instance
    _base_dir = base_dir


def _log_base_dir():
    from core.base.config import cfg

    log_dir = cfg.get('settings', 'logging.dir', 'log')
    return os.path.join(_base_dir, 'data', log_dir)


def _find_databases():
    base = _log_base_dir()
    result = []
    if not os.path.isdir(base):
        return result
    _collect(result, base, '')
    for sub in sorted(os.listdir(base)):
        sp = os.path.join(base, sub)
        if os.path.isdir(sp):
            _collect(result, sp, sub)
    return result


def _collect(result, directory, label):
    for f in sorted(os.listdir(directory)):
        fpath = os.path.join(directory, f)
        if f.endswith('.db') and os.path.isfile(fpath):
            result.append(
                {
                    'bot_qq': label or 'log',
                    'label': label or '全局日志',
                    'name': f,
                    'path': fpath.replace('\\', '/'),
                    'size': os.path.getsize(fpath),
                    'date': label if re.match(r'^\d{4}-\d{2}-\d{2}$', label) else '',
                }
            )


def _validate_db_path(db_path):
    base = os.path.abspath(_log_base_dir())
    abs_path = os.path.abspath(db_path)
    if not is_within(base, abs_path) or not abs_path.endswith('.db') or not os.path.isfile(abs_path):
        return False, ''
    return True, abs_path


def _open(db_path, readonly=True):
    if readonly:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, check_same_thread=False, timeout=30)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
    return conn


async def handle_list_databases(request: web.Request):
    return web.json_response({'success': True, 'databases': _find_databases()})


async def handle_list_tables(request: web.Request):
    body = await json_body(request)
    db_path = body.get('path', '')
    if not db_path:
        return web.json_response({'success': False, 'message': '缺少 path'}, status=400)
    valid, abs_path = _validate_db_path(db_path)
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    try:
        conn = _open(abs_path)
        tables = []
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            tname = row['name']
            count = conn.execute(f'SELECT COUNT(*) AS c FROM "{tname}"').fetchone()['c']
            columns = [
                {'name': c['name'], 'type': c['type'], 'notnull': bool(c['notnull']), 'pk': bool(c['pk'])}
                for c in conn.execute(f'PRAGMA table_info("{tname}")')
            ]
            tables.append({'name': tname, 'count': count, 'columns': columns})
        conn.close()
        return web.json_response({'success': True, 'tables': tables})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def handle_query_table(request: web.Request):
    body = await json_body(request)
    db_path = body.get('path', '')
    table = body.get('table', '')
    page = max(1, int(body.get('page', 1)))
    page_size = min(200, max(1, int(body.get('page_size', 50))))
    order_by = body.get('order_by', '')
    order_dir = body.get('order_dir', 'DESC')

    if not db_path or not table:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    valid, abs_path = _validate_db_path(db_path)
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    if not re.match(r'^[\w]+$', table):
        return web.json_response({'success': False, 'message': '无效表名'}, status=400)
    if order_dir.upper() not in ('ASC', 'DESC'):
        order_dir = 'DESC'

    try:
        conn = _open(abs_path)
        total = conn.execute(f'SELECT COUNT(*) AS c FROM "{table}"').fetchone()['c']
        order_clause = f'ORDER BY "{order_by}" {order_dir}' if order_by and re.match(r'^[\w]+$', order_by) else 'ORDER BY rowid DESC'
        offset = (page - 1) * page_size
        rows = conn.execute(
            f'SELECT rowid AS _rowid, * FROM "{table}" {order_clause} LIMIT ? OFFSET ?',
            (page_size, offset),
        ).fetchall()
        data = [dict(r) for r in rows]
        columns = [{'name': c['name'], 'type': c['type']} for c in conn.execute(f'PRAGMA table_info("{table}")')]
        conn.close()
        return web.json_response({'success': True, 'data': data, 'columns': columns, 'total': total, 'page': page, 'page_size': page_size})
    except Exception as e:
        log.warning(f'查询表失败: {e}')
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def handle_execute_sql(request: web.Request):
    body = await json_body(request)
    db_path = body.get('path', '')
    sql = (body.get('sql', '') or '').strip()
    if not db_path or not sql:
        return web.json_response({'success': False, 'message': '缺少参数'}, status=400)
    valid, abs_path = _validate_db_path(db_path)
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)

    is_read = _READ_PATTERN.match(sql)
    if is_read and not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        sql = sql.rstrip(';') + ' LIMIT 1000'
    try:
        conn = _open(abs_path, readonly=False)
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        if len(statements) > 1 and not is_read:
            conn.executescript(sql)
            conn.close()
            return web.json_response({'success': True, 'message': f'已执行 {len(statements)} 条语句', 'affected': -1})
        cursor = conn.execute(sql)
        if is_read:
            rows = cursor.fetchall()
            columns = [{'name': d[0], 'type': ''} for d in cursor.description] if cursor.description else []
            data = [dict(r) for r in rows]
            conn.close()
            return web.json_response({'success': True, 'data': data, 'columns': columns, 'total': len(data)})
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return web.json_response({'success': True, 'message': f'执行成功, 影响 {affected} 行', 'affected': affected})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=400)


async def handle_delete_rows(request: web.Request):
    body = await json_body(request)
    db_path = body.get('path', '')
    table = body.get('table', '')
    rowids = body.get('rowids', [])
    if not db_path or not table or not rowids:
        return web.json_response({'success': False, 'message': '缺少参数 (path/table/rowids)'}, status=400)
    if not re.match(r'^[\w]+$', table):
        return web.json_response({'success': False, 'message': '无效表名'}, status=400)
    if not isinstance(rowids, list) or not all(isinstance(r, int) for r in rowids):
        return web.json_response({'success': False, 'message': 'rowids 必须是整数数组'}, status=400)
    valid, abs_path = _validate_db_path(db_path)
    if not valid:
        return web.json_response({'success': False, 'message': '无效路径'}, status=403)
    try:
        conn = _open(abs_path, readonly=False)
        placeholders = ','.join('?' * len(rowids))
        cursor = conn.execute(f'DELETE FROM "{table}" WHERE rowid IN ({placeholders})', rowids)
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return web.json_response({'success': True, 'deleted': deleted})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)
