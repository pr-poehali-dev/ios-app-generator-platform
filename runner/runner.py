#!/usr/bin/env python3
import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

VERSION = '0.1.0'
GITHUB_API = 'https://api.github.com'
ZIP_HOSTS = ('codeload.github.com',)

MAX_ZIP_BYTES = 80 * 1024 * 1024
MAX_UNPACKED = 600 * 1024 * 1024
MAX_FILE = 100 * 1024 * 1024
MAX_ENTRIES = 40000
MAX_RATIO = 200

DEFAULTS = {
    'cabinet_url': '',
    'runner_key': '',
    'github_token': '',
    'work_dir': 'work',
    'docker_bin': 'docker',
    'node_image': 'node:{major}-bookworm-slim',
    'npm_registry': '',
    'memory': '2g',
    'cpus': '2',
    'pids': '512',
    'install_timeout': 900,
    'build_timeout': 900,
    'poll_seconds': 5,
    'confirm_each': True,
    'keep_workdir': False,
}

SHA_RE = re.compile(r'^[0-9a-f]{40}$')
REPO_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$')
INSTALL_OK = {'npm ci', 'npm install', 'pnpm install --frozen-lockfile'}
BUILD_OK = {'npm run build', 'pnpm run build'}
OUT_RE = re.compile(r'^[A-Za-z0-9._-]{1,50}$')

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

_SECRETS = []


def register_secret(value):
    v = str(value or '')
    if len(v) >= 8 and v not in _SECRETS:
        _SECRETS.append(v)


def redact(text):
    s = ANSI.sub('', str(text or ''))
    s = CTRL.sub('', s)
    for v in _SECRETS:
        s = s.replace(v, '***')
    for rx in REDACT:
        s = rx.sub('***', s)
    s = BEARER.sub('Bearer ***', s)
    s = URL_CREDS.sub(r'\1***@', s)
    s = KEY_VALUE.sub(r'\1***', s)
    return s


class RunnerError(Exception):
    pass


class Cancelled(Exception):
    pass


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for k in DEFAULTS:
            if k in data:
                cfg[k] = data[k]
    env_map = {
        'STUDIO_CABINET_URL': 'cabinet_url', 'STUDIO_RUNNER_KEY': 'runner_key',
        'STUDIO_GITHUB_TOKEN': 'github_token', 'STUDIO_WORK_DIR': 'work_dir',
        'STUDIO_DOCKER_BIN': 'docker_bin', 'STUDIO_NODE_IMAGE': 'node_image',
        'STUDIO_NPM_REGISTRY': 'npm_registry',
    }
    for env, key in env_map.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    register_secret(cfg['runner_key'])
    register_secret(cfg['github_token'])
    return cfg


def validate_config(cfg, need_cabinet=True):
    if need_cabinet:
        url = urllib.parse.urlparse(cfg['cabinet_url'])
        if url.scheme != 'https' or not url.hostname:
            raise RunnerError('cabinet_url должен быть адресом https:// функции кабинета')
        if not str(cfg['runner_key']).startswith('sr_'):
            raise RunnerError('runner_key не задан или имеет неверный формат')
    if cfg['npm_registry']:
        reg = urllib.parse.urlparse(cfg['npm_registry'])
        if reg.scheme != 'https' or not reg.hostname:
            raise RunnerError('npm_registry должен быть адресом https://')
    if '{major}' not in cfg['node_image'] and not re.match(r'^[\w./:@-]+$', cfg['node_image']):
        raise RunnerError('node_image содержит недопустимые символы')
    if not re.match(r'^[\w./:@{}-]+$', cfg['node_image']):
        raise RunnerError('node_image содержит недопустимые символы')
    if not re.match(r'^\d+[mg]$', str(cfg['memory'])):
        raise RunnerError('memory задаётся как 2g или 1500m')
    if not re.match(r'^\d+(\.\d+)?$', str(cfg['cpus'])):
        raise RunnerError('cpus задаётся числом')


class Cabinet:
    def __init__(self, cfg):
        self.url = cfg['cabinet_url']
        self.key = cfg['runner_key']

    def call(self, body, timeout=20):
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method='POST',
            headers={'Content-Type': 'application/json', 'X-Runner-Key': self.key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            msg = ''
            try:
                msg = json.loads(e.read()).get('error', '')
            except (ValueError, AttributeError):
                pass
            raise RunnerError('Кабинет ответил %d: %s' % (e.code, msg))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RunnerError('Нет связи с кабинетом: %s' % type(e).__name__)

    def claim(self):
        return self.call({'action': 'runner_claim'}).get('job')

    def report(self, job_id, **fields):
        body = {'action': 'runner_report', 'job_id': job_id}
        body.update(fields)
        return self.call(body)


def github_zip(repo, sha, token, api=GITHUB_API):
    if not REPO_RE.match(repo) or not SHA_RE.match(sha):
        raise RunnerError('Некорректные параметры репозитория или коммита')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'ai-web-studio-runner',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(urllib.request.Request('%s/repos/%s/zipball/%s' % (api, repo, sha), headers=headers), timeout=30)
        raise RunnerError('GitHub не вернул ссылку на архив')
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 307, 308):
            hint = ' Для приватного репозитория задайте github_token у runner.' if e.code == 404 and not token else ''
            raise RunnerError('GitHub ответил %d при запросе архива.%s' % (e.code, hint))
        location = e.headers.get('Location', '')
    except urllib.error.URLError as e:
        raise RunnerError('Нет связи с GitHub: %s' % type(e).__name__)
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != 'https' or parsed.hostname not in ZIP_HOSTS:
        raise RunnerError('GitHub вернул неожиданный адрес архива — загрузка отклонена')
    try:
        with urllib.request.urlopen(urllib.request.Request(location, headers={'User-Agent': 'ai-web-studio-runner'}), timeout=60) as r:
            chunks, size = [], 0
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise RunnerError('Архив больше %d МБ' % (MAX_ZIP_BYTES // 1048576))
                chunks.append(chunk)
            return b''.join(chunks)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RunnerError('Не удалось скачать архив: %s' % type(e).__name__)


def safe_extract(data, dest, sha):
    import io
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise RunnerError('Скачанный файл не является ZIP')
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise RunnerError('В архиве слишком много файлов')
    total = 0
    seen = set()
    names = []
    for info in infos:
        raw = info.filename
        name = raw.replace('\\', '/')
        if '\x00' in name or name.startswith('/') or re.match(r'^[A-Za-z]:', name) or '..' in name.split('/'):
            raise RunnerError('Архив отклонён: небезопасный путь «%s»' % name[:80])
        if ((info.external_attr >> 16) & 0o170000) == 0o120000:
            raise RunnerError('Архив отклонён: символическая ссылка «%s»' % name[:80])
        if info.flag_bits & 1:
            raise RunnerError('Архив отклонён: зашифрованный файл')
        if info.is_dir():
            names.append((name, info))
            continue
        if info.file_size > MAX_FILE:
            raise RunnerError('Архив отклонён: файл «%s» слишком большой' % name[:80])
        key = name.lower()
        if key in seen:
            raise RunnerError('Архив отклонён: повторяющееся имя «%s»' % name[:80])
        seen.add(key)
        total += info.file_size
        names.append((name, info))
    if total > MAX_UNPACKED:
        raise RunnerError('Архив отклонён: распакованный размер больше %d МБ' % (MAX_UNPACKED // 1048576))
    if total > 50 * 1048576 and total > MAX_RATIO * max(len(data), 1):
        raise RunnerError('Архив отклонён: подозрительная степень сжатия')
    tops = {n.split('/')[0] for n, _ in names if n.strip('/')}
    if len(tops) != 1:
        raise RunnerError('Ожидалась одна корневая папка в архиве GitHub')
    root = tops.pop()
    if not root.endswith(sha[:7]):
        raise RunnerError('Архив не соответствует коммиту %s' % sha[:7])
    os.makedirs(dest, exist_ok=True)
    base = os.path.realpath(dest)
    written = 0
    for name, info in names:
        rel = name[len(root):].lstrip('/')
        if not rel:
            continue
        target = os.path.realpath(os.path.join(base, rel))
        if target != base and not target.startswith(base + os.sep):
            raise RunnerError('Архив отклонён: выход за пределы папки')
        if info.is_dir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, 'wb') as out:
            copied = 0
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > info.file_size + 1024:
                    raise RunnerError('Архив отклонён: размер файла не совпадает с заголовком')
                out.write(chunk)
        written += 1
    return written


class LogBuffer:
    def __init__(self, limit=400000):
        self.parts = []
        self.size = 0
        self.limit = limit
        self.lock = threading.Lock()
        self.truncated = False

    def add(self, text):
        with self.lock:
            self.parts.append(text)
            self.size += len(text)
            while self.size > self.limit and len(self.parts) > 1:
                self.size -= len(self.parts.pop(0))
                self.truncated = True

    def text(self):
        with self.lock:
            body = ''.join(self.parts)
        return ('…(начало журнала обрезано)…\n' if self.truncated else '') + redact(body)


def container_user():
    if hasattr(os, 'getuid'):
        return '%d:%d' % (os.getuid(), os.getgid())
    return '1000:1000'


def docker_args(cfg, job, workdir, phase, name):
    major = int(job['node_major'])
    image = cfg['node_image'].replace('{major}', str(major))
    args = [
        cfg['docker_bin'], 'run', '--rm', '--name', name,
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--memory', str(cfg['memory']), '--memory-swap', str(cfg['memory']),
        '--cpus', str(cfg['cpus']), '--pids-limit', str(cfg['pids']),
        '--read-only', '--tmpfs', '/tmp:rw,size=1g,mode=1777',
        '--user', container_user(),
        '-v', '%s:/app' % workdir, '-w', '/app',
        '-e', 'CI=true', '-e', 'HOME=/tmp/home', '-e', 'npm_config_cache=/tmp/npm-cache',
        '-e', 'NODE_ENV=' + ('development' if phase == 'install' else 'production'),
        '-e', 'npm_config_update_notifier=false', '-e', 'npm_config_fund=false',
    ]
    if cfg['npm_registry']:
        args += ['-e', 'npm_config_registry=' + cfg['npm_registry']]
    if phase == 'build':
        args += ['--network', 'none']
    args.append(image)
    return args


def phase_command(job, phase):
    if phase == 'install':
        cmd = job['install_cmd']
        if cmd not in INSTALL_OK:
            raise RunnerError('Команда установки не из списка разрешённых')
        parts = cmd.split()
        if not job.get('allow_scripts'):
            parts.append('--ignore-scripts')
        parts.append('--no-audit')
        return parts
    cmd = job['build_cmd']
    if cmd not in BUILD_OK:
        raise RunnerError('Команда сборки не из списка разрешённых')
    return cmd.split()


def run_container(cfg, job, workdir, phase, log, timeout, should_cancel):
    name = 'studio-%s-%s-%d' % (job['id'], phase, int(time.time()))
    argv = docker_args(cfg, job, workdir, phase, name) + phase_command(job, phase)
    log.add('\n$ [%s] %s\n' % (phase, ' '.join(phase_command(job, phase))))
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **flags)

    def pump():
        for line in iter(proc.stdout.readline, b''):
            log.add(line.decode('utf-8', 'replace'))

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    started = time.monotonic()
    status = None
    while proc.poll() is None:
        if should_cancel():
            status = 'cancelled'
        elif time.monotonic() - started > timeout:
            status = 'timeout'
        if status:
            subprocess.run([cfg['docker_bin'], 'kill', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        time.sleep(0.5)
    t.join(timeout=5)
    if status == 'cancelled':
        raise Cancelled()
    if status == 'timeout':
        log.add('\nПревышено время выполнения (%d с). Контейнер остановлен.\n' % timeout)
        return None
    return proc.returncode


def dir_stats(path):
    files, size = 0, 0
    for root, _, names in os.walk(path):
        for n in names:
            fp = os.path.join(root, n)
            if os.path.islink(fp):
                continue
            files += 1
            size += os.path.getsize(fp)
    return files, size


def process_job(cfg, cab, job, on_confirm=None):
    jid = job['id']
    log = LogBuffer()
    state = {'cancel': False, 'last': 0}

    def push(**fields):
        res = cab.report(jid, log=log.text(), **fields)
        state['cancel'] = bool(res.get('cancel'))
        state['last'] = time.monotonic()

    def should_cancel():
        if time.monotonic() - state['last'] > 5:
            try:
                push()
            except RunnerError:
                pass
        return state['cancel']

    workdir = os.path.abspath(os.path.join(cfg['work_dir'], 'job-%s' % jid))
    env_info = '%s %s, docker образ %s' % (platform.system(), platform.release(), cfg['node_image'].replace('{major}', str(job['node_major'])))
    try:
        if not REPO_RE.match(str(job['repo'])) or not SHA_RE.match(str(job['commit_sha'])):
            raise RunnerError('Задание содержит некорректные данные')
        if job['output_dir'] and not OUT_RE.match(job['output_dir']):
            raise RunnerError('Некорректная папка результата')
        if on_confirm and not on_confirm(job):
            log.add('Запуск отклонён на стороне runner.\n')
            push(status='cancelled', phase='done', error='Запуск отклонён на стороне runner', env_info=env_info)
            return 'cancelled'
        state['last'] = time.monotonic()
        push(phase='download', env_info=env_info)
        log.add('Скачиваю %s@%s\n' % (job['repo'], job['commit_sha'][:7]))
        data = github_zip(job['repo'], job['commit_sha'], cfg['github_token'])
        if os.path.exists(workdir):
            shutil.rmtree(workdir)
        push(phase='prepare')
        count = safe_extract(data, workdir, job['commit_sha'])
        log.add('Распаковано файлов: %d\n' % count)
        if not os.path.exists(os.path.join(workdir, 'package.json')):
            raise RunnerError('В корне репозитория нет package.json')
        if job['install_cmd'] == 'npm ci' and not os.path.exists(os.path.join(workdir, 'package-lock.json')):
            raise RunnerError('Для «npm ci» нужен package-lock.json, а его в репозитории нет. Выберите «npm install» или добавьте lock-файл')
        if job['install_cmd'].startswith('pnpm') and not os.path.exists(os.path.join(workdir, 'pnpm-lock.yaml')):
            raise RunnerError('Для pnpm нужен pnpm-lock.yaml, а его в репозитории нет')

        push(phase='install')
        code = run_container(cfg, job, workdir, 'install', log, int(cfg['install_timeout']), should_cancel)
        if code is None:
            push(status='timeout', phase='install', error='Установка зависимостей превысила лимит времени', env_info=env_info)
            return 'timeout'
        if code != 0:
            push(status='failed', phase='install', exit_install=code, error='Установка зависимостей завершилась с кодом %d' % code, env_info=env_info)
            return 'failed'

        push(phase='build', exit_install=0)
        code = run_container(cfg, job, workdir, 'build', log, int(cfg['build_timeout']), should_cancel)
        if code is None:
            push(status='timeout', phase='build', exit_install=0, error='Сборка превысила лимит времени', env_info=env_info)
            return 'timeout'
        files = size = None
        if job['output_dir']:
            out = os.path.join(workdir, job['output_dir'])
            if os.path.isdir(out):
                files, size = dir_stats(out)
        if code != 0:
            push(status='failed', phase='build', exit_install=0, exit_build=code, error='Сборка завершилась с кодом %d' % code, env_info=env_info)
            return 'failed'
        note = ''
        if job['output_dir'] and not files:
            note = 'Сборка прошла, но папка результата «%s» пуста или не найдена' % job['output_dir']
            log.add('\n' + note + '\n')
        push(status='success', phase='done', exit_install=0, exit_build=0,
             output_files=files, output_bytes=size, error=note, env_info=env_info)
        return 'success'
    except Cancelled:
        log.add('\nЗадание отменено.\n')
        push(status='cancelled', error='Отменено из кабинета', env_info=env_info)
        return 'cancelled'
    except RunnerError as e:
        log.add('\nОшибка: %s\n' % e)
        push(status='error', error=str(e), env_info=env_info)
        return 'error'
    finally:
        if not cfg['keep_workdir'] and os.path.exists(workdir):
            shutil.rmtree(workdir, ignore_errors=True)


def ask_confirm(job):
    print('\n=== Новое задание №%s ===' % job['id'])
    print('Репозиторий: %s' % job['repo'])
    print('Коммит:      %s' % job['commit_sha'])
    print('Установка:   %s%s' % (job['install_cmd'], '  (скрипты зависимостей РАЗРЕШЕНЫ)' if job.get('allow_scripts') else '  (скрипты зависимостей отключены)'))
    print('Сборка:      %s, Node.js %s' % (job['build_cmd'], job['node_major']))
    print('Код из репозитория и его зависимостей будет выполнен в контейнере.')
    try:
        return input('Запустить? [y/N] ').strip().lower() in ('y', 'yes', 'д', 'да')
    except EOFError:
        return False


def check(cfg):
    ok = True
    print('Версия runner: %s, система: %s' % (VERSION, platform.platform()))
    try:
        out = subprocess.run([cfg['docker_bin'], 'version', '--format', '{{.Server.Version}}'], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            print('Docker: работает, версия сервера %s' % out.stdout.strip())
        else:
            ok = False
            print('Docker: не отвечает. %s' % redact(out.stderr.strip())[:300])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        ok = False
        print('Docker: не найден. Установите Docker и запустите его.')
    image = cfg['node_image'].replace('{major}', '20')
    try:
        out = subprocess.run([cfg['docker_bin'], 'image', 'inspect', image], capture_output=True, timeout=30)
        if out.returncode != 0:
            print('Образ %s ещё не скачан; он загрузится при первом задании (или выполните: docker pull %s)' % (image, image))
        else:
            print('Образ %s: есть' % image)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        Cabinet(cfg).call({'action': 'runner_report', 'job_id': 0})
    except RunnerError as e:
        msg = str(e)
        if '404' in msg:
            print('Кабинет: доступен, ключ принят')
        else:
            ok = False
            print('Кабинет: %s' % msg)
    return ok


def main():
    ap = argparse.ArgumentParser(description='Runner AI Web Studio: независимая установка и сборка проекта')
    ap.add_argument('--config', default='config.json')
    ap.add_argument('--check', action='store_true', help='проверить Docker и связь с кабинетом')
    ap.add_argument('--once', action='store_true', help='взять не больше одного задания и выйти')
    ap.add_argument('--auto', action='store_true', help='не спрашивать подтверждение в консоли (подтверждение остаётся в кабинете)')
    args = ap.parse_args()
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except (RunnerError, ValueError, OSError) as e:
        print('Ошибка настройки: %s' % e)
        return 2
    if args.check:
        return 0 if check(cfg) else 1
    if args.auto:
        cfg['confirm_each'] = False
    cab = Cabinet(cfg)
    stop = {'v': False}
    signal.signal(signal.SIGINT, lambda *a: stop.update(v=True))
    print('Runner %s запущен. Ожидаю задания. Остановка: Ctrl+C' % VERSION)
    while not stop['v']:
        try:
            job = cab.claim()
        except RunnerError as e:
            print('[%s] %s' % (time.strftime('%H:%M:%S'), e))
            time.sleep(max(15, int(cfg['poll_seconds'])))
            continue
        if not job:
            if args.once:
                return 0
            time.sleep(int(cfg['poll_seconds']))
            continue
        result = process_job(cfg, cab, job, ask_confirm if cfg['confirm_each'] else None)
        print('Задание №%s: %s' % (job['id'], result))
        if args.once:
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
