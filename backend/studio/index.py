import base64
import hashlib
import hmac
import json
import os
import time

import psycopg2
import psycopg2.extras

from auditor import audit_zip, AuditError
import github_api as gh
import secrets_box

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
TOKEN_TTL = 12 * 3600
MAX_FAILS = 5
FAIL_WINDOW_MIN = 15
TEMPLATES = {'empty', 'vite', 'tailwind', 'components'}
EDITABLE = ['name', 'description', 'repo_url', 'stack', 'install_cmd', 'dev_cmd',
            'build_cmd', 'output_dir', 'node_version', 'archived']

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-User-Id, X-Auth-Token, X-Session-Id',
}


def resp(status, body):
    return {
        'statusCode': status,
        'headers': {**CORS, 'Content-Type': 'application/json'},
        'body': json.dumps(body, ensure_ascii=False, default=str),
    }


def connect():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    return conn


def schema():
    return os.environ['MAIN_DB_SCHEMA']


def _key():
    pw = os.environ.get('STUDIO_ADMIN_PASSWORD', '')
    return hashlib.sha256(('studio-token:' + pw).encode()).digest() if pw else b''


def make_token():
    exp = str(int(time.time()) + TOKEN_TTL)
    sig = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return exp + '.' + sig


def token_valid(token):
    if not _key() or not token or '.' not in token:
        return False
    exp, sig = token.split('.', 1)
    if not exp.isdigit() or int(exp) < time.time():
        return False
    good = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good)


def header(event, name):
    for k, v in (event.get('headers') or {}).items():
        if k.lower() == name.lower():
            return v
    return ''


def client_ip(event):
    return str(((event.get('requestContext') or {}).get('identity') or {}).get('sourceIp') or '')[:64]


def login(cur, event, body):
    if not os.environ.get('STUDIO_ADMIN_PASSWORD'):
        return resp(503, {'error': 'Доступ не настроен: администратор не задал пароль кабинета'})
    s = schema()
    ip = client_ip(event)
    cur.execute(
        f"SELECT COUNT(*) AS n FROM {s}.studio_login_attempts WHERE ip = %s AND created_at > NOW() - INTERVAL '{FAIL_WINDOW_MIN} minutes'",
        (ip,),
    )
    if cur.fetchone()['n'] >= MAX_FAILS:
        return resp(429, {'error': 'Слишком много неудачных попыток. Подождите %d минут' % FAIL_WINDOW_MIN})
    given = str(body.get('password') or '').encode()
    real = os.environ['STUDIO_ADMIN_PASSWORD'].encode()
    if not hmac.compare_digest(hashlib.sha256(given).digest(), hashlib.sha256(real).digest()):
        cur.execute(f"INSERT INTO {s}.studio_login_attempts (ip) VALUES (%s)", (ip,))
        cur.execute(f"DELETE FROM {s}.studio_login_attempts WHERE created_at < NOW() - INTERVAL '1 day'")
        return resp(401, {'error': 'Неверный пароль'})
    return resp(200, {'token': make_token(), 'expires_in': TOKEN_TTL})


PROJECT_COLS = ('id, name, description, template, source_type, repo_url, stack, install_cmd, '
                'dev_cmd, build_cmd, output_dir, node_version, archived, created_at, updated_at, '
                "gh_repo, gh_branch, (gh_token_enc <> '') AS gh_has_token")


def list_projects(cur, include_archived):
    s = schema()
    where = '' if include_archived else 'WHERE p.archived = FALSE'
    cur.execute(
        f"""SELECT p.id, p.name, p.description, p.template, p.source_type, p.repo_url, p.stack,
                   p.archived, p.created_at, p.updated_at, p.gh_repo,
                   a.id AS last_audit_id, a.created_at AS last_audit_at,
                   a.report->'counts' AS counts
            FROM {s}.projects p
            LEFT JOIN LATERAL (
                SELECT id, created_at, report FROM {s}.project_audits
                WHERE project_id = p.id ORDER BY created_at DESC LIMIT 1
            ) a ON TRUE
            {where}
            ORDER BY p.updated_at DESC"""
    )
    return cur.fetchall()


def get_project(cur, pid):
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


def get_audit(cur, aid):
    s = schema()
    cur.execute(
        f"""SELECT id, project_id, filename, archive_size, report, tree, created_at
            FROM {s}.project_audits WHERE id = %s""",
        (aid,),
    )
    return cur.fetchone()


def gh_context(cur, pid):
    cur.execute(
        f"SELECT gh_repo, gh_branch, gh_token_enc FROM {schema()}.projects WHERE id = %s", (pid,))
    row = cur.fetchone()
    if not row or not row['gh_repo']:
        return None
    return {'repo': row['gh_repo'], 'branch': row['gh_branch'], 'token': secrets_box.decrypt(row['gh_token_enc']),
            'token_broken': bool(row['gh_token_enc']) and not secrets_box.decrypt(row['gh_token_enc'])}


def gh_fail(e):
    return resp(e.status, {'error': str(e)})


def run_github(cur, event, params, body, method):
    s = schema()
    action = body.get('action') if method == 'POST' else params.get('gh')
    pid = int(body.get('id') or params.get('id') or 0)

    if action == 'connect':
        try:
            repo = gh.parse_repo(body.get('repo'))
            branch = gh.clean_branch(body.get('branch'))
        except gh.GitHubError as e:
            return gh_fail(e)
        token = str(body.get('token') or '').strip()
        keep_token = bool(body.get('keep_token'))
        if token and not secrets_box.available():
            return resp(400, {'error': 'Ключ шифрования токенов не задан администратором (секрет STUDIO_TOKEN_KEY). Публичный репозиторий можно подключить без токена'})
        if keep_token and not token:
            ctx = gh_context(cur, pid)
            token = ctx['token'] if ctx else ''
        try:
            info = gh.repo_info(repo, token)
            if not branch:
                branch = info['default_branch']
            head = gh.commits(repo, branch, token, 1)
        except gh.GitHubError as e:
            return gh_fail(e)
        enc = secrets_box.encrypt(token) if token else ''
        cur.execute(
            f"""UPDATE {s}.projects SET gh_repo = %s, gh_branch = %s, gh_token_enc = %s,
                repo_url = %s, updated_at = NOW() WHERE id = %s RETURNING id""",
            (info['full_name'], branch, enc, 'https://github.com/' + info['full_name'], pid),
        )
        if not cur.fetchone():
            return resp(404, {'error': 'Проект не найден'})
        return resp(200, {'repo': info['full_name'], 'branch': branch, 'private': info['private'],
                          'has_token': bool(enc), 'warnings': info['warnings'],
                          'head': head[0] if head else None})

    ctx = gh_context(cur, pid)
    if action == 'disconnect':
        cur.execute(f"UPDATE {s}.projects SET gh_repo = '', gh_branch = '', gh_token_enc = '', updated_at = NOW() WHERE id = %s", (pid,))
        return resp(200, {'ok': True})
    if not ctx:
        return resp(400, {'error': 'К проекту не подключён репозиторий'})
    if ctx['token_broken']:
        return resp(422, {'error': 'Сохранённый токен не читается (ключ шифрования изменён). Подключите репозиторий заново'})

    try:
        if action == 'files':
            return resp(200, gh.tree(ctx['repo'], ctx['branch'], ctx['token']))
        if action == 'commits':
            return resp(200, {'commits': gh.commits(ctx['repo'], ctx['branch'], ctx['token'], 20)})
        if action == 'audit':
            head = gh.commits(ctx['repo'], ctx['branch'], ctx['token'], 1)
            data = gh.download_zip(ctx['repo'], ctx['branch'], ctx['token'])
            label = '%s@%s' % (ctx['repo'], ctx['branch'])
            try:
                result = audit_zip(data, label)
            except AuditError as e:
                return resp(422, {'error': str(e)})
            report = result['report']
            report['source'] = {'type': 'github', 'repo': ctx['repo'], 'branch': ctx['branch'],
                                'commit': head[0]['sha'] if head else '', 'commit_message': head[0]['message'] if head else ''}
            cmds = report['commands']
            cur.execute(
                f"""INSERT INTO {s}.project_audits (project_id, filename, archive_size, report, tree)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (pid, label[:300], len(data), json.dumps(report, ensure_ascii=False),
                 json.dumps(result['tree'], ensure_ascii=False)),
            )
            aid = cur.fetchone()['id']
            cur.execute(
                f"""UPDATE {s}.projects SET stack = %s, install_cmd = %s, dev_cmd = %s, build_cmd = %s,
                    output_dir = %s, node_version = %s, updated_at = NOW() WHERE id = %s""",
                (', '.join(report['stack'])[:200], cmds['install']['value'], cmds['dev']['value'],
                 cmds['build']['value'], cmds['output_dir']['value'], cmds['node_version']['value'], pid),
            )
            return resp(200, {'audit_id': aid})
    except gh.GitHubError as e:
        return gh_fail(e)
    return resp(400, {'error': 'Неизвестное действие'})


def clean_str(value, limit):
    return str(value or '').strip()[:limit]


def handler(event: dict, context) -> dict:
    """Кабинет AI Web Studio: вход по паролю, проекты, настройки и статический аудит ZIP. Все операции кроме входа требуют токен."""
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': {**CORS, 'Access-Control-Max-Age': '86400'}, 'body': ''}

    params = event.get('queryStringParameters') or {}
    try:
        body = json.loads(event.get('body') or '{}') if method in ('POST', 'PUT') else {}
    except ValueError:
        return resp(400, {'error': 'Некорректный запрос'})
    if not isinstance(body, dict):
        return resp(400, {'error': 'Некорректный запрос'})

    conn = connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    s = schema()
    try:
        if method == 'POST' and body.get('action') == 'login':
            return login(cur, event, body)

        if not os.environ.get('STUDIO_ADMIN_PASSWORD'):
            return resp(503, {'error': 'Доступ не настроен: администратор не задал пароль кабинета'})
        if not token_valid(header(event, 'X-Auth-Token')):
            return resp(401, {'error': 'Требуется вход'})

        if method == 'GET' and params.get('gh'):
            return run_github(cur, event, params, body, method)
        if method == 'POST' and body.get('action') in ('connect', 'disconnect', 'audit'):
            return run_github(cur, event, params, body, method)

        if method == 'GET':
            if params.get('check'):
                return resp(200, {'ok': True})
            if params.get('audit_id'):
                audit = get_audit(cur, int(params['audit_id']))
                return resp(200, audit) if audit else resp(404, {'error': 'Аудит не найден'})
            if params.get('id'):
                project = get_project(cur, int(params['id']))
                return resp(200, project) if project else resp(404, {'error': 'Проект не найден'})
            return resp(200, {'projects': list_projects(cur, params.get('archived') == '1')})

        if method == 'POST' and body.get('action') == 'create':
            name = clean_str(body.get('name'), 200)
            if not name:
                return resp(400, {'error': 'Укажите название черновика'})
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
                data = base64.b64decode(raw_b64, validate=True)
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
    except ValueError:
        return resp(400, {'error': 'Некорректные параметры'})
    finally:
        cur.close()
        conn.close()
