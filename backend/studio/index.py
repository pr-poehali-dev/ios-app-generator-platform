import base64
import json
import os

import psycopg2
import psycopg2.extras

from auditor import audit_zip, AuditError

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
TEMPLATES = {'empty', 'vite', 'tailwind', 'components'}
EDITABLE = ['name', 'description', 'repo_url', 'stack', 'install_cmd', 'dev_cmd',
            'build_cmd', 'output_dir', 'node_version', 'archived']

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-User-Id, X-Auth-Token, X-Session-Id',
}


def resp(status: int, body: dict) -> dict:
    return {
        'statusCode': status,
        'headers': {**CORS, 'Content-Type': 'application/json'},
        'body': json.dumps(body, ensure_ascii=False, default=str),
    }


def connect():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    return conn


def schema() -> str:
    return os.environ['MAIN_DB_SCHEMA']


PROJECT_COLS = ('id, name, description, template, source_type, repo_url, stack, install_cmd, '
                'dev_cmd, build_cmd, output_dir, node_version, archived, created_at, updated_at')


def list_projects(cur, include_archived: bool):
    s = schema()
    where = '' if include_archived else 'WHERE p.archived = FALSE'
    cur.execute(
        f"""SELECT p.id, p.name, p.description, p.template, p.source_type, p.repo_url, p.stack,
                   p.archived, p.created_at, p.updated_at,
                   a.id AS last_audit_id, a.created_at AS last_audit_at,
                   a.report->'counts' AS counts, a.report->'poehali_detected' AS poehali_detected
            FROM {s}.projects p
            LEFT JOIN LATERAL (
                SELECT id, created_at, report FROM {s}.project_audits
                WHERE project_id = p.id ORDER BY created_at DESC LIMIT 1
            ) a ON TRUE
            {where}
            ORDER BY p.updated_at DESC"""
    )
    return cur.fetchall()


def get_project(cur, pid: int):
    s = schema()
    cur.execute(f"SELECT {PROJECT_COLS} FROM {s}.projects WHERE id = %s", (pid,))
    project = cur.fetchone()
    if not project:
        return None
    cur.execute(
        f"""SELECT id, filename, archive_size, created_at, report->'counts' AS counts
            FROM {s}.project_audits WHERE project_id = %s ORDER BY created_at DESC""",
        (pid,),
    )
    project['audits'] = cur.fetchall()
    return project


def get_audit(cur, aid: int):
    s = schema()
    cur.execute(
        f"""SELECT id, project_id, filename, archive_size, report, tree, created_at
            FROM {s}.project_audits WHERE id = %s""",
        (aid,),
    )
    return cur.fetchone()


def clean_str(value, limit: int) -> str:
    return str(value or '').strip()[:limit]


def handler(event: dict, context) -> dict:
    """Кабинет проектов AI Web Studio: список, создание, настройки и статический аудит ZIP-архива."""
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': {**CORS, 'Access-Control-Max-Age': '86400'}, 'body': ''}

    params = event.get('queryStringParameters') or {}
    conn = connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    s = schema()
    try:
        if method == 'GET':
            if params.get('audit_id'):
                audit = get_audit(cur, int(params['audit_id']))
                return resp(200, audit) if audit else resp(404, {'error': 'Аудит не найден'})
            if params.get('id'):
                project = get_project(cur, int(params['id']))
                return resp(200, project) if project else resp(404, {'error': 'Проект не найден'})
            return resp(200, {'projects': list_projects(cur, params.get('archived') == '1')})

        body = json.loads(event.get('body') or '{}')

        if method == 'POST' and body.get('action') == 'create':
            name = clean_str(body.get('name'), 200)
            if not name:
                return resp(400, {'error': 'Укажите название проекта'})
            template = body.get('template') if body.get('template') in TEMPLATES else 'empty'
            cur.execute(
                f"""INSERT INTO {s}.projects (name, description, template, source_type)
                    VALUES (%s, %s, %s, 'new') RETURNING id""",
                (name, clean_str(body.get('description'), 4000), template),
            )
            return resp(200, {'id': cur.fetchone()['id']})

        if method == 'POST' and body.get('action') == 'import':
            name = clean_str(body.get('name'), 200)
            filename = clean_str(body.get('filename'), 300)
            raw_b64 = body.get('file_base64') or ''
            if not raw_b64:
                return resp(400, {'error': 'Архив не передан'})
            if len(raw_b64) > MAX_ARCHIVE_BYTES * 4 // 3 + 16:
                return resp(413, {'error': 'Архив больше 8 МБ. Удалите node_modules и dist и попробуйте снова'})
            try:
                data = base64.b64decode(raw_b64, validate=False)
            except ValueError:
                return resp(400, {'error': 'Не удалось прочитать архив'})
            if len(data) > MAX_ARCHIVE_BYTES:
                return resp(413, {'error': 'Архив больше 8 МБ. Удалите node_modules и dist и попробуйте снова'})
            try:
                result = audit_zip(data, filename)
            except AuditError as e:
                return resp(422, {'error': str(e)})
            report = result['report']
            if not name:
                name = clean_str(report['package'].get('name') or filename.rsplit('.', 1)[0] or 'Импортированный проект', 200)
            cmds = report['commands']
            cur.execute(
                f"""INSERT INTO {s}.projects
                    (name, description, template, source_type, repo_url, stack, install_cmd,
                     dev_cmd, build_cmd, output_dir, node_version)
                    VALUES (%s, %s, 'empty', 'zip', %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    name, clean_str(body.get('description'), 4000), clean_str(body.get('repo_url'), 500),
                    ', '.join(report['stack'])[:200],
                    cmds['install']['value'], cmds['dev']['value'], cmds['build']['value'],
                    cmds['output_dir']['value'], cmds['node_version']['value'],
                ),
            )
            pid = cur.fetchone()['id']
            cur.execute(
                f"""INSERT INTO {s}.project_audits (project_id, filename, archive_size, report, tree)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (pid, filename, len(data), json.dumps(report, ensure_ascii=False),
                 json.dumps(result['tree'], ensure_ascii=False)),
            )
            return resp(200, {'id': pid, 'audit_id': cur.fetchone()['id']})

        if method == 'PUT':
            pid = int(body.get('id') or 0)
            sets, vals = [], []
            for key in EDITABLE:
                if key in body:
                    if key == 'archived':
                        vals.append(bool(body[key]))
                    else:
                        vals.append(clean_str(body[key], 4000 if key == 'description' else 500))
                    sets.append(f'{key} = %s')
            if not pid or not sets:
                return resp(400, {'error': 'Нечего обновлять'})
            if 'name' in body and not clean_str(body['name'], 200):
                return resp(400, {'error': 'Название не может быть пустым'})
            vals.append(pid)
            cur.execute(
                f"UPDATE {s}.projects SET {', '.join(sets)}, updated_at = NOW() WHERE id = %s RETURNING id",
                vals,
            )
            return resp(200, {'ok': True}) if cur.fetchone() else resp(404, {'error': 'Проект не найден'})

        return resp(400, {'error': 'Неизвестное действие'})
    finally:
        cur.close()
        conn.close()
