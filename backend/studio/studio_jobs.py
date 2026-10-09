import hashlib
import re
import secrets

INSTALL_CHOICES = {
    'npm ci': 'npm run build',
    'npm install': 'npm run build',
    'pnpm install --frozen-lockfile': 'pnpm run build',
}
NODE_MAJORS = (18, 20, 22)
LOG_LIMIT = 100000
ONLINE_SEC = 60
STALE_RUNNING_SEC = 180
PENDING_EXPIRE_MIN = 30
MAX_RUNNERS = 5
FINAL = ('success', 'failed', 'timeout', 'error', 'cancelled')
PHASES = ('download', 'prepare', 'install', 'build', 'done')
OUTPUT_DIR_RE = re.compile(r'^[A-Za-z0-9._-]{1,50}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')

ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
REDACT = [
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}'),
    re.compile(r'\bsr_[A-Za-z0-9_-]{20,}'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)'),
]
BEARER = re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}')
URL_CREDS = re.compile(r'(?i)\b([a-z][a-z0-9+.-]{1,15}://)[^\s/@:]+:[^\s/@]+@')
KEY_VALUE = re.compile(r'(?i)((?:[A-Za-z0-9_.-]*)(?:token|secret|passw(?:or)?d|api[_-]?key|authorization|_auth)[A-Za-z0-9_.-]*\s*[=:]\s*)(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s"\']+)')


def redact(text):
    s = ANSI.sub('', str(text or ''))
    s = CTRL.sub('', s)
    for rx in REDACT:
        s = rx.sub('***', s)
    s = BEARER.sub('Bearer ***', s)
    s = URL_CREDS.sub(r'\1***@', s)
    s = KEY_VALUE.sub(r'\1***', s)
    return s


def tail(text, limit=LOG_LIMIT):
    return text if len(text) <= limit else '…(начало журнала обрезано)…\n' + text[-limit:]


def new_runner_key():
    key = 'sr_' + secrets.token_urlsafe(32)
    return key, hash_key(key)


def hash_key(key):
    return hashlib.sha256(str(key).encode()).hexdigest()


def parse_job_params(body, project_output_dir):
    install = str(body.get('install') or '').strip()
    if install not in INSTALL_CHOICES:
        return None, 'Недопустимая команда установки. Доступно: %s' % ', '.join(INSTALL_CHOICES)
    try:
        node = int(body.get('node_major'))
    except (TypeError, ValueError):
        return None, 'Укажите версию Node.js: %s' % ', '.join(map(str, NODE_MAJORS))
    if node not in NODE_MAJORS:
        return None, 'Версия Node.js должна быть одной из: %s' % ', '.join(map(str, NODE_MAJORS))
    out = str(project_output_dir or '').strip()
    if out and not OUTPUT_DIR_RE.match(out):
        out = ''
    sha = str(body.get('sha') or '').strip().lower()
    if sha and not SHA_RE.match(sha):
        return None, 'Некорректный SHA коммита'
    return {
        'install': install, 'build': INSTALL_CHOICES[install], 'node_major': node,
        'output_dir': out, 'allow_scripts': bool(body.get('allow_scripts')), 'sha': sha,
    }, ''


def clean_report(body):
    def to_int(key, lo=0, hi=2 ** 40):
        v = body.get(key)
        if v is None:
            return None
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if lo <= v <= hi else None

    status = body.get('status')
    phase = body.get('phase')
    return {
        'phase': phase if phase in PHASES else None,
        'status': status if status in FINAL else None,
        'exit_install': to_int('exit_install', -1000, 1000),
        'exit_build': to_int('exit_build', -1000, 1000),
        'output_files': to_int('output_files'),
        'output_bytes': to_int('output_bytes'),
        'error': redact(str(body.get('error') or ''))[:500],
        'env_info': redact(str(body.get('env_info') or ''))[:300],
        'log': tail(redact(str(body.get('log') or '')[:LOG_LIMIT * 3])),
    }


JOB_PUBLIC = ('id, project_id, runner_id, repo, branch, commit_sha, install_cmd, build_cmd, node_major, '
              'output_dir, allow_scripts, status, phase, exit_install, exit_build, output_files, '
              'output_bytes, error, env_info, cancel_requested, created_at, claimed_at, finished_at, updated_at')


def sweep(cur, s):
    cur.execute(
        f"""UPDATE {s}.runner_jobs SET status = 'error', error = 'Runner перестал отвечать', finished_at = NOW(), updated_at = NOW()
            WHERE status = 'running' AND updated_at < NOW() - INTERVAL '{STALE_RUNNING_SEC} seconds'""")
    cur.execute(
        f"""UPDATE {s}.runner_jobs SET status = 'cancelled', error = 'Ни один runner не взял задание за {PENDING_EXPIRE_MIN} минут', finished_at = NOW(), updated_at = NOW()
            WHERE status = 'pending' AND created_at < NOW() - INTERVAL '{PENDING_EXPIRE_MIN} minutes'""")


def runner_create(cur, s, name):
    name = str(name or '').strip()[:100] or 'runner'
    cur.execute(f"SELECT COUNT(*) AS n FROM {s}.runners WHERE revoked = FALSE")
    if cur.fetchone()['n'] >= MAX_RUNNERS:
        return None, 'Достигнут предел активных runner (%d). Отзовите ненужные' % MAX_RUNNERS
    key, key_hash = new_runner_key()
    cur.execute(f"INSERT INTO {s}.runners (name, key_hash) VALUES (%s, %s) RETURNING id", (name, key_hash))
    return {'id': cur.fetchone()['id'], 'key': key, 'name': name}, ''


def runner_list(cur, s):
    cur.execute(
        f"""SELECT id, name, revoked, last_seen, created_at,
                   (last_seen IS NOT NULL AND last_seen > NOW() - INTERVAL '{ONLINE_SEC} seconds' AND revoked = FALSE) AS online
            FROM {s}.runners ORDER BY id DESC LIMIT 20""")
    return cur.fetchall()


def runner_revoke(cur, s, rid):
    cur.execute(f"UPDATE {s}.runners SET revoked = TRUE WHERE id = %s RETURNING id", (rid,))
    if not cur.fetchone():
        return False
    cur.execute(
        f"""UPDATE {s}.runner_jobs SET status = 'error', error = 'Runner отозван', finished_at = NOW(), updated_at = NOW()
            WHERE runner_id = %s AND status = 'running'""", (rid,))
    return True


def runner_auth(cur, s, key):
    key = str(key or '')
    if not key.startswith('sr_') or len(key) > 200:
        return None
    cur.execute(
        f"UPDATE {s}.runners SET last_seen = NOW() WHERE key_hash = %s AND revoked = FALSE RETURNING id, name",
        (hash_key(key),))
    return cur.fetchone()


def job_create(cur, s, pid, repo, branch, sha, params):
    cur.execute(
        f"SELECT COUNT(*) AS n FROM {s}.runner_jobs WHERE project_id = %s AND status IN ('pending', 'running')", (pid,))
    if cur.fetchone()['n']:
        return None, 'У проекта уже есть активное задание. Дождитесь завершения или отмените его'
    cur.execute(
        f"""INSERT INTO {s}.runner_jobs
            (project_id, repo, branch, commit_sha, install_cmd, build_cmd, node_major, output_dir, allow_scripts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (pid, repo, branch, sha, params['install'], params['build'], params['node_major'],
         params['output_dir'], params['allow_scripts']))
    return cur.fetchone()['id'], ''


def job_list(cur, s, pid):
    sweep(cur, s)
    cur.execute(
        f"SELECT {JOB_PUBLIC} FROM {s}.runner_jobs WHERE project_id = %s ORDER BY id DESC LIMIT 10", (pid,))
    return cur.fetchall()


def job_get(cur, s, jid):
    sweep(cur, s)
    cur.execute(f"SELECT {JOB_PUBLIC}, log FROM {s}.runner_jobs WHERE id = %s", (jid,))
    return cur.fetchone()


def job_cancel(cur, s, jid):
    cur.execute(
        f"""UPDATE {s}.runner_jobs SET cancel_requested = TRUE, updated_at = NOW(),
                   status = CASE WHEN status = 'pending' THEN 'cancelled' ELSE status END,
                   finished_at = CASE WHEN status = 'pending' THEN NOW() ELSE finished_at END
            WHERE id = %s AND status IN ('pending', 'running') RETURNING id""", (jid,))
    return bool(cur.fetchone())


def claim(cur, s, runner_id):
    sweep(cur, s)
    cur.execute(f"SELECT COUNT(*) AS n FROM {s}.runner_jobs WHERE runner_id = %s AND status = 'running'", (runner_id,))
    if cur.fetchone()['n']:
        return None
    cur.execute(
        f"""UPDATE {s}.runner_jobs SET status = 'running', runner_id = %s, phase = 'download',
                   claimed_at = NOW(), updated_at = NOW()
            WHERE id = (SELECT id FROM {s}.runner_jobs WHERE status = 'pending' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING id, repo, branch, commit_sha, install_cmd, build_cmd, node_major, output_dir, allow_scripts""",
        (runner_id,))
    return cur.fetchone()


def report(cur, s, runner_id, jid, body):
    cur.execute(
        f"SELECT status, cancel_requested FROM {s}.runner_jobs WHERE id = %s AND runner_id = %s", (jid, runner_id))
    job = cur.fetchone()
    if not job:
        return None
    if job['status'] != 'running':
        return {'cancel': True, 'accepted': False}
    r = clean_report(body)
    sets = ['updated_at = NOW()', 'log = %s']
    vals = [r['log']]
    for col in ('phase', 'exit_install', 'exit_build', 'output_files', 'output_bytes'):
        if r[col] is not None:
            sets.append(f'{col} = %s')
            vals.append(r[col])
    if r['error']:
        sets.append('error = %s')
        vals.append(r['error'])
    if r['env_info']:
        sets.append('env_info = %s')
        vals.append(r['env_info'])
    if r['status']:
        sets.append('status = %s')
        vals.append(r['status'])
        sets.append('finished_at = NOW()')
    vals.extend([jid, runner_id])
    cur.execute(f"UPDATE {s}.runner_jobs SET {', '.join(sets)} WHERE id = %s AND runner_id = %s AND status = 'running'", vals)
    return {'cancel': bool(job['cancel_requested']), 'accepted': True}
