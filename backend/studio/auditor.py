import io
import json
import re
import time
import zipfile
from urllib.parse import urlparse

MAX_ENTRIES = 10000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024
MAX_RATIO = 100
MAX_READ = 256 * 1024
MAX_TOTAL_READ = 12 * 1024 * 1024
MAX_SCAN_FILES = 1500
TIME_BUDGET = 3.5
MAX_TREE = 4000

SKIP_DIRS = {
    'node_modules', '.git', 'dist', 'build', '.next', '__pycache__', '.venv',
    'venv', '.cache', 'coverage', '.turbo', '.idea', '.vscode',
}
TEXT_EXT = (
    '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.py', '.html', '.css',
    '.json', '.sql', '.toml', '.yml', '.yaml', '.txt', '.cfg', '.ini', '.md',
)
NOSCAN_SUFFIX = ('package-lock.json', 'bun.lock', 'yarn.lock', 'pnpm-lock.yaml')
IGNORE_ENV_NAMES = {'MODE', 'DEV', 'PROD', 'BASE_URL', 'SSR', 'NODE_ENV'}
LOCKFILES = ['bun.lockb', 'bun.lock', 'pnpm-lock.yaml', 'yarn.lock', 'package-lock.json']
CONFIG_PATTERNS = [
    r'^vite\.config\.\w+$', r'^tailwind\.config\.\w+$', r'^tsconfig[\w.]*\.json$',
    r'^eslint\.config\.\w+$', r'^\.eslintrc[\w.]*$', r'^postcss\.config\.\w+$',
    r'^components\.json$', r'^vercel\.json$', r'^netlify\.toml$', r'^Dockerfile$',
    r'^docker-compose\.ya?ml$', r'^next\.config\.\w+$', r'^\.github/workflows/.+$',
    r'^func2url\.json$', r'^\.npmrc$',
]

ENV_PATTERNS = [
    re.compile(r'os\.environ\[\s*[\'"]([A-Za-z0-9_]+)[\'"]\s*\]'),
    re.compile(r'os\.environ\.get\(\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
    re.compile(r'os\.getenv\(\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
    re.compile(r'import\.meta\.env\.([A-Za-z0-9_]+)'),
    re.compile(r'process\.env\.([A-Za-z0-9_]+)'),
]
ENV_FILE_KEY = re.compile(r'^\s*(?:export\s+)?([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*)$', re.M)
POEHALI_URL = re.compile(r'https?://([a-z0-9.-]*poehali\.dev)(/[^\s"\'`)<>\\]*)?', re.I)
SCHEMA_NAME = re.compile(r'\bt_p\d{4,}_[a-z0-9_]+\b')
CREATE_TABLE = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w."]+)', re.I)

SECRET_PATTERNS = [
    ('Блок приватного ключа', 'fact', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('Ключ доступа в формате AWS', 'assumption', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Строка подключения с паролем', 'assumption',
     re.compile(r'\b[a-z][a-z0-9+.-]{2,15}://[^\s:@/\'"<>{}$]+:([^\s@/\'"<>{}$]{4,})@')),
    ('Токен в формате JWT', 'assumption', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.')),
    ('Присвоение значения ключу/паролю/токену', 'assumption',
     re.compile(r'(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)\w*[\'"]?\s*[:=]\s*[\'"]([^\'"\s]{12,})[\'"]')),
]
PLACEHOLDER = re.compile(r'(?i)(your|example|placeholder|changeme|xxxx|\*{3,}|process\.env|os\.environ|username|password|<|\$\{|\bpass\b)')


class AuditError(Exception):
    pass


def B(file, line=None, note=None):
    d = {'file': file}
    if line:
        d['line'] = line
    if note:
        d['note'] = note
    return d


def _lineno(text, pos):
    return text.count('\n', 0, pos) + 1


def _first_line(text, pattern):
    m = re.search(pattern, text or '')
    return _lineno(text, m.start()) if m else None


def _clean_name(raw):
    if '\x00' in raw:
        return None
    name = raw.replace('\\', '/')
    while name.startswith('./'):
        name = name[2:]
    if not name or name.startswith('/') or re.match(r'^[A-Za-z]:', name):
        return None
    if '..' in name.split('/'):
        return None
    return name


def _is_symlink(info):
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _parse_requirements(text):
    out = []
    for line in text.splitlines():
        line = line.split('#')[0].strip()
        if not line or line.startswith('-'):
            continue
        name = re.split(r'[<>=!~\[; @]', line)[0].strip()
        if name:
            out.append((name, '==' in line))
    return out


def _validate_archive(data, zf):
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise AuditError('В архиве больше %d записей — разбор отклонён' % MAX_ENTRIES)
    total = 0
    seen = set()
    for info in infos:
        name = _clean_name(info.filename)
        if name is None:
            raise AuditError('Архив отклонён: небезопасный путь в записи «%s»' % info.filename[:80].replace('\x00', ''))
        if _is_symlink(info):
            raise AuditError('Архив отклонён: символическая ссылка «%s»' % name[:80])
        if info.flag_bits & 1:
            raise AuditError('Архив отклонён: зашифрованный файл «%s»' % name[:80])
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise AuditError('Архив отклонён: неподдерживаемый метод сжатия у «%s»' % name[:80])
        if info.is_dir():
            continue
        if info.file_size > MAX_FILE_BYTES:
            raise AuditError('Архив отклонён: файл «%s» больше %d МБ' % (name[:80], MAX_FILE_BYTES // 1048576))
        key = name.lower()
        if key in seen:
            raise AuditError('Архив отклонён: повторяющееся имя файла «%s»' % name[:80])
        seen.add(key)
        total += info.file_size
    if total > MAX_TOTAL_UNCOMPRESSED:
        raise AuditError('Архив отклонён: суммарный распакованный размер больше %d МБ' % (MAX_TOTAL_UNCOMPRESSED // 1048576))
    if total > 20 * 1048576 and total > MAX_RATIO * max(len(data), 1):
        raise AuditError('Архив отклонён: подозрительно высокая степень сжатия')


def audit_zip(data, filename):
    started = time.monotonic()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise AuditError('Файл не является ZIP-архивом или повреждён')
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        _validate_archive(data, zf)
        infos = zf.infolist()
    except zipfile.BadZipFile:
        raise AuditError('ZIP-архив повреждён')

    warnings = []
    entries = []
    for info in infos:
        if info.is_dir():
            continue
        name = _clean_name(info.filename)
        if name.startswith('__MACOSX/') or name.endswith('.DS_Store'):
            continue
        entries.append((name, info))
    if not entries:
        raise AuditError('В архиве нет файлов')

    tops = {n.split('/')[0] for n, _ in entries if '/' in n}
    root_prefix = ''
    if all('/' in n for n, _ in entries) and len(tops) == 1:
        root_prefix = tops.pop() + '/'

    files = {}
    skipped = {}
    for name, info in entries:
        rel = name[len(root_prefix):] if root_prefix else name
        if not rel:
            continue
        hit = next((p for p in rel.split('/')[:-1] if p in SKIP_DIRS), None)
        if hit:
            skipped[hit] = skipped.get(hit, 0) + 1
            continue
        files[rel] = info

    state = {'bytes': 0}
    cache = {}

    def read(path):
        if path in cache:
            return cache[path]
        info = files.get(path)
        text = None
        if info is not None and state['bytes'] < MAX_TOTAL_READ:
            try:
                with zf.open(info) as fh:
                    raw = fh.read(MAX_READ + 1)
                state['bytes'] += len(raw)
                if len(raw) <= MAX_READ and b'\x00' not in raw[:2048]:
                    text = raw.decode('utf-8', errors='replace')
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
                text = None
        cache[path] = text
        return text

    items = []

    def add(category, status, certainty, title, detail='', basis=None):
        items.append({
            'category': category, 'status': status, 'certainty': certainty,
            'title': title, 'detail': detail, 'basis': (basis or [])[:12],
        })

    env_found = {}
    poehali_refs = []
    secret_hits = []
    candidates = [
        p for p in sorted(files)
        if p.lower().endswith(TEXT_EXT) and not p.endswith(NOSCAN_SUFFIX)
        and not re.search(r'\.min\.|\.map$', p)
    ]
    too_big = [p for p in candidates if files[p].file_size > MAX_READ]
    candidates = [p for p in candidates if files[p].file_size <= MAX_READ]
    scanned = 0
    truncated = False
    for rel in candidates[:MAX_SCAN_FILES]:
        if time.monotonic() - started > TIME_BUDGET:
            truncated = True
            break
        text = read(rel)
        if not text:
            continue
        scanned += 1
        for pat in ENV_PATTERNS:
            for m in pat.finditer(text):
                name = m.group(1)
                if name.upper() in IGNORE_ENV_NAMES:
                    continue
                lst = env_found.setdefault(name, [])
                if len(lst) < 5:
                    lst.append((rel, _lineno(text, m.start())))
        if 'poehali' in text.lower():
            for m in POEHALI_URL.finditer(text):
                host = m.group(1).lower()
                path = m.group(2) or ''
                if path.lower().split('?')[0].endswith('.js'):
                    kind = 'script'
                elif host == 'functions.poehali.dev':
                    kind = 'functions'
                elif host == 'bucket.poehali.dev':
                    kind = 'storage'
                elif host == 'cdn.poehali.dev' and path.startswith('/intertnal/'):
                    kind = 'internal'
                elif host == 'cdn.poehali.dev':
                    kind = 'asset'
                else:
                    kind = 'other'
                poehali_refs.append((kind, host + path[:60], rel, _lineno(text, m.start())))
        if not rel.endswith('.md'):
            for kind, cert, pat in SECRET_PATTERNS:
                for m in pat.finditer(text):
                    val = m.group(1) if m.groups() else ''
                    if val and PLACEHOLDER.search(val + m.group(0)):
                        continue
                    secret_hits.append((kind, cert, rel, _lineno(text, m.start())))
                    break
    if truncated:
        warnings.append('Анализ остановлен по времени: просканировано %d из %d текстовых файлов. Выводы о переменных, ссылках и секретах неполные.' % (scanned, len(candidates)))
    if len(candidates) > MAX_SCAN_FILES:
        warnings.append('Текстовых файлов больше лимита (%d): часть не просканирована.' % MAX_SCAN_FILES)
    if too_big:
        warnings.append('Не просканированы текстовые файлы крупнее %d КБ: %d шт.' % (MAX_READ // 1024, len(too_big)))

    ext_counts = {}
    total_size = 0
    for rel, info in files.items():
        total_size += info.file_size
        base = rel.rsplit('/', 1)[-1]
        ext = ('.' + base.rsplit('.', 1)[-1].lower()) if '.' in base else '(без расширения)'
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    top_ext = sorted(ext_counts.items(), key=lambda kv: -kv[1])[:10]
    configs = sorted(rel for rel in files if any(re.match(p, rel) for p in CONFIG_PATTERNS))
    lockfiles = [lf for lf in LOCKFILES if lf in files]
    extra_pkgs = sorted(p for p in files if p.endswith('/package.json') and p.count('/') <= 2)

    pkg = None
    pkg_text = read('package.json') if 'package.json' in files else None
    if pkg_text:
        try:
            parsed = json.loads(pkg_text)
            if isinstance(parsed, dict):
                pkg = parsed
        except ValueError:
            pass
    prod = dict(pkg.get('dependencies', {})) if pkg else {}
    dev = dict(pkg.get('devDependencies', {})) if pkg else {}
    all_deps = {**dev, **prod}
    scripts = pkg.get('scripts', {}) if pkg and isinstance(pkg.get('scripts'), dict) else {}

    stack_tags = []
    dep_map = [
        ('react', 'React'), ('vue', 'Vue'), ('svelte', 'Svelte'), ('next', 'Next.js'),
        ('vite', 'Vite'), ('react-scripts', 'Create React App'), ('tailwindcss', 'Tailwind CSS'),
        ('react-router-dom', 'React Router'), ('@tanstack/react-query', 'TanStack Query'),
        ('express', 'Express'), ('fastify', 'Fastify'), ('@nestjs/core', 'NestJS'),
    ]
    for dep, tag in dep_map:
        if dep in all_deps:
            stack_tags.append(tag)
    if 'typescript' in all_deps or 'tsconfig.json' in files:
        stack_tags.append('TypeScript')
    if 'components.json' in files:
        stack_tags.append('shadcn/ui')

    py_reqs = {}
    for rel in sorted(files):
        if rel.endswith('requirements.txt'):
            py_reqs[rel] = _parse_requirements(read(rel) or '')
    py_names = {n.lower() for lst in py_reqs.values() for n, _ in lst}
    for dep, tag in (('django', 'Django'), ('flask', 'Flask'), ('fastapi', 'FastAPI')):
        if dep in py_names:
            stack_tags.append(tag)

    fn_re = re.compile(r'^backend/([^/]+)/index\.(py|ts)$')
    functions = []
    for rel in sorted(files):
        m = fn_re.match(rel)
        if not m:
            continue
        fdir = 'backend/%s' % m.group(1)
        src = read(rel) or ''
        reqs = py_reqs.get(fdir + '/requirements.txt', [])
        functions.append({
            'name': m.group(1), 'path': rel,
            'language': 'Python' if m.group(2) == 'py' else 'TypeScript',
            'handler_line': _first_line(src, r'def\s+handler\s*\(|export\s+(?:async\s+)?(?:function\s+)?handler'),
            'event_line': _first_line(src, r'httpMethod|queryStringParameters'),
            'db_line': _first_line(src, r'psycopg|DATABASE_URL|asyncpg'),
            'storage_line': _first_line(src, r'boto3|S3Client'),
            'has_tests': (fdir + '/tests.json') in files,
            'requirements': [n for n, _ in reqs][:40],
        })
    if functions:
        stack_tags.append('Backend-функции (%d)' % len(functions))

    func_map = None
    func_map_text = read('func2url.json') if 'func2url.json' in files else None
    if func_map_text:
        try:
            parsed = json.loads(func_map_text)
            if isinstance(parsed, dict):
                func_map = parsed
        except ValueError:
            warnings.append('func2url.json не удалось разобрать как JSON')
    func2url_users = []
    for rel in candidates:
        if rel.startswith('src/') and 'func2url' in (cache.get(rel) or ''):
            func2url_users.append(B(rel, _first_line(cache[rel], r'func2url')))

    migrations = sorted(p for p in files if p.endswith('.sql') and re.search(r'(^|/)(db_migrations|migrations)/', p))
    schema_basis = []
    tables = []
    for mig in migrations[:200]:
        txt = read(mig)
        if not txt:
            continue
        ln = _first_line(txt, SCHEMA_NAME.pattern)
        if ln:
            schema_basis.append(B(mig, ln))
        for t in CREATE_TABLE.findall(txt):
            t = t.replace('"', '')
            if t not in tables:
                tables.append(t)

    pm, pm_src, pm_conf, pm_file = None, None, 'none', None
    if pkg and isinstance(pkg.get('packageManager'), str):
        pm = pkg['packageManager'].split('@')[0]
        pm_src, pm_conf, pm_file = 'поле packageManager', 'found', 'package.json'
    elif lockfiles:
        pm = {'bun.lockb': 'bun', 'bun.lock': 'bun', 'pnpm-lock.yaml': 'pnpm',
              'yarn.lock': 'yarn', 'package-lock.json': 'npm'}[lockfiles[0]]
        pm_src, pm_conf, pm_file = 'по lock-файлу %s' % lockfiles[0], 'inferred', lockfiles[0]
    elif pkg:
        pm, pm_src, pm_conf, pm_file = 'npm', 'по умолчанию, lock-файла нет', 'inferred', 'package.json'
    run_prefix = {'npm': 'npm run', 'pnpm': 'pnpm', 'yarn': 'yarn', 'bun': 'bun run'}.get(pm or 'npm')

    def script_cmd(name):
        if name in scripts:
            return {'value': '%s %s' % (run_prefix, name), 'script': str(scripts[name]),
                    'source': 'scripts.%s' % name, 'confidence': 'found' if pm_conf == 'found' else 'inferred',
                    'file': 'package.json', 'line': _first_line(pkg_text, r'"%s"\s*:' % re.escape(name))}
        return {'value': '', 'script': '', 'source': 'скрипт не найден', 'confidence': 'none', 'file': 'package.json', 'line': None}

    if pm == 'npm':
        install_val = 'npm ci' if 'package-lock.json' in files else 'npm install'
    else:
        install_val = '%s install' % pm if pm else ''
    install = {
        'value': install_val, 'source': pm_src or 'package.json не найден',
        'confidence': 'inferred' if pm else 'none', 'file': pm_file, 'line': None,
    }
    dev_cmd = script_cmd('dev')
    if not dev_cmd['value']:
        dev_cmd = script_cmd('start')
    build_cmd = script_cmd('build')

    out_dir = {'value': '', 'source': 'не определено', 'confidence': 'none', 'file': None, 'line': None}
    vite_cfg = next((c for c in configs if re.match(r'^vite\.config\.\w+$', c)), None)
    if vite_cfg:
        vtxt = read(vite_cfg) or ''
        m = re.search(r'outDir\s*:\s*[\'"]([^\'"]+)[\'"]', vtxt)
        if m:
            out_dir = {'value': m.group(1), 'source': 'outDir', 'confidence': 'found', 'file': vite_cfg, 'line': _lineno(vtxt, m.start())}
        else:
            out_dir = {'value': 'dist', 'source': 'значение Vite по умолчанию: в конфиге outDir не задан', 'confidence': 'inferred', 'file': vite_cfg, 'line': None}
    elif 'next' in all_deps:
        out_dir = {'value': '.next', 'source': 'значение Next.js по умолчанию', 'confidence': 'inferred', 'file': 'package.json', 'line': None}
    elif 'react-scripts' in all_deps:
        out_dir = {'value': 'build', 'source': 'значение Create React App по умолчанию', 'confidence': 'inferred', 'file': 'package.json', 'line': None}

    node_version = {'value': '', 'source': 'не указана', 'confidence': 'none', 'file': None, 'line': None}
    for nf in ('.nvmrc', '.node-version'):
        if nf in files and (read(nf) or '').strip():
            node_version = {'value': read(nf).strip()[:40], 'source': nf, 'confidence': 'found', 'file': nf, 'line': 1}
            break
    else:
        eng = pkg.get('engines') if pkg and isinstance(pkg.get('engines'), dict) else {}
        if eng.get('node'):
            node_version = {'value': str(eng['node'])[:40], 'source': 'engines.node', 'confidence': 'found',
                            'file': 'package.json', 'line': _first_line(pkg_text, r'"engines"')}

    if pkg is None and 'package.json' in files:
        add('Frontend', 'unknown', 'unknown', 'package.json не удалось прочитать',
            'Файл повреждён, слишком большой или не является JSON. Стек и команды определить нельзя.', [B('package.json')])
    elif pkg is None:
        add('Frontend', 'unknown', 'unknown', 'package.json не найден в корне архива',
            'Без него нельзя определить зависимости и команды. Возможно, проект лежит во вложенной папке или это не Node.js-проект.',
            [B(p) for p in extra_pkgs])
    else:
        names = [t for t in stack_tags if not t.startswith('Backend-функции')]
        if names:
            add('Frontend', 'portable', 'fact', 'Стек распознан по package.json',
                'Факт: в зависимостях найдено — %s. Всего пакетов: %d (рабочих %d, dev %d). Не проверялось: доступность пакетов и совместимость версий.'
                % (', '.join(names), len(all_deps), len(prod), len(dev)),
                [B('package.json', _first_line(pkg_text, r'"dependencies"'), 'dependencies')])
        else:
            add('Frontend', 'unknown', 'unknown', 'Стек не распознан',
                'Известные фреймворки в зависимостях не найдены. Пакетов: %d.' % len(all_deps), [B('package.json')])

        odd = []
        for n, v in all_deps.items():
            v = str(v)
            if re.match(r'^(file:|link:|git\+|git:|github:|https?:|workspace:|portal:)', v) or re.match(r'^[\w.-]+/[\w.-]+(#.*)?$', v):
                odd.append(B('package.json', _first_line(pkg_text, r'"%s"\s*:' % re.escape(n)), '%s → %s' % (n, v[:60])))
        if odd:
            add('Frontend', 'needs_adaptation', 'fact', 'Зависимости не из публичного реестра',
                'Факт: пакеты подключены по пути, git-адресу или ссылке. Для установки на другом компьютере нужен доступ к ним.', odd)
        pn = [n for n in all_deps if 'poehali' in n.lower()]
        if pn:
            add('Frontend', 'unknown', 'fact', 'В зависимостях есть пакеты с именем poehali',
                'Факт: такие пакеты есть. Неизвестно, доступны ли они вне платформы.',
                [B('package.json', _first_line(pkg_text, r'"%s"\s*:' % re.escape(n)), n) for n in pn])
    if extra_pkgs:
        add('Frontend', 'unknown', 'fact', 'Найдены вложенные package.json',
            'Возможно, это монорепозиторий. Анализировался только корневой package.json.', [B(p) for p in extra_pkgs])
    other_server = [t for t in stack_tags if t in ('Express', 'Fastify', 'NestJS', 'Django', 'Flask', 'FastAPI')]
    if other_server:
        add('Backend', 'unknown', 'fact', 'Найдены серверные фреймворки: %s' % ', '.join(other_server),
            'Факт: они указаны в зависимостях. Как запускается сервер и что ему нужно — автоматически не определялось.',
            [B('package.json')] + [B(p) for p in py_reqs])

    if pkg:
        if len(lockfiles) == 1:
            add('Сборка', 'portable', 'fact', 'Lock-файл: %s' % lockfiles[0], 'Версии зависимостей зафиксированы.', [B(lockfiles[0])])
        elif len(lockfiles) > 1:
            add('Сборка', 'needs_setup', 'fact', 'Несколько lock-файлов',
                'Факт: в проекте лежат lock-файлы разных менеджеров. Неизвестно, какой основной. Команда установки — предположение (выбран %s).' % pm,
                [B(lf) for lf in lockfiles])
        else:
            add('Сборка', 'needs_setup', 'fact', 'Lock-файл не найден',
                'Версии зависимостей не зафиксированы — установка может дать другой результат, чем в оригинале.', [B('package.json')])
        if build_cmd['confidence'] != 'none':
            add('Сборка', 'portable', 'fact', 'Скрипт сборки найден',
                'Факт: scripts.build = «%s». Что сборка проходит — не проверено.' % build_cmd['script'][:120],
                [B('package.json', build_cmd['line'], 'scripts.build')])
        else:
            add('Сборка', 'unknown', 'fact', 'Скрипт сборки не найден', 'В scripts нет build.', [B('package.json', _first_line(pkg_text, r'"scripts"'))])
        if dev_cmd['confidence'] == 'none':
            add('Сборка', 'unknown', 'fact', 'Скрипт запуска не найден', 'В scripts нет dev или start.', [B('package.json', _first_line(pkg_text, r'"scripts"'))])
        if node_version['confidence'] == 'none':
            add('Сборка', 'unknown', 'unknown', 'Версия Node.js не указана',
                'Ни .nvmrc, ни engines.node нет. Подходящую версию придётся подобрать при первом запуске.', [])
        if out_dir['confidence'] == 'inferred':
            add('Сборка', 'unknown', 'assumption', 'Папка результата сборки — предположение', out_dir['source'], [B(out_dir['file'], out_dir['line'])])

    add('Сборка', 'unknown', 'unknown', 'Установка, сборка и запуск не проверялись',
        'Аудит статический. Работоспособность можно подтвердить только запуском на отдельном компьютере или сервере.', [])

    by_kind = {}
    for kind, shown, rel, ln in poehali_refs:
        by_kind.setdefault(kind, []).append(B(rel, ln, shown))
    if 'script' in by_kind:
        add('Ссылки на poehali.dev', 'needs_setup', 'assumption', 'Страница подгружает скрипты с poehali.dev',
            'Факт: найдено ссылок на .js-файлы — %d. Предположение: по именам это служебные скрипты платформы (редактор, телеметрия). Их назначение в архиве не описано, необходимость для работы сайта не определена — проверьте работу без них.' % len(by_kind['script']),
            by_kind['script'])
    if 'internal' in by_kind:
        add('Ссылки на poehali.dev', 'needs_setup', 'fact', 'Ссылки на служебные ресурсы платформы',
            'Факт: %d ссылок (например, картинка превью для соцсетей). Неизвестно, будут ли они доступны вне платформы.' % len(by_kind['internal']),
            by_kind['internal'])
    if 'asset' in by_kind:
        add('Ссылки на poehali.dev', 'needs_setup', 'fact', 'Файлы на CDN платформы',
            'Факт: %d ссылок на файлы на cdn.poehali.dev. Обязательной зависимостью это не является: решение зависит от того, хотите ли вы хранить файлы у себя.' % len(by_kind['asset']),
            by_kind['asset'])
    if 'functions' in by_kind:
        add('Ссылки на poehali.dev', 'needs_adaptation', 'fact', 'Код обращается к облачным функциям на functions.poehali.dev',
            'Факт: %d упоминаний адреса. Чтобы работать независимо, функции нужно развернуть у себя и заменить адреса.' % len(by_kind['functions']),
            by_kind['functions'])
    if 'storage' in by_kind:
        add('Ссылки на poehali.dev', 'needs_adaptation', 'fact', 'Прописан адрес хранилища платформы',
            'Факт: %d упоминаний bucket.poehali.dev. Для независимой работы нужно своё S3-совместимое хранилище.' % len(by_kind['storage']),
            by_kind['storage'])
    if 'other' in by_kind:
        add('Ссылки на poehali.dev', 'unknown', 'unknown', 'Прочие ссылки на poehali.dev',
            'Факт: %d ссылок. Назначение автоматически не определено (возможно, документация или контакты).' % len(by_kind['other']),
            by_kind['other'])

    if functions:
        add('Backend', 'needs_setup', 'fact', 'Найдены backend-функции: %d' % len(functions),
            'Факт: файлы backend/<имя>/index.py|ts. Запускались ли они — не проверено.',
            [B(f['path'], f['handler_line'], '%s, %s' % (f['name'], f['language'])) for f in functions])
        ev = [B(f['path'], f['event_line'], f['name']) for f in functions if f['event_line']]
        if ev:
            add('Backend', 'needs_adaptation', 'assumption', 'Функции ожидают формат события облачных функций',
                'Факт: в коде читаются поля event (httpMethod / queryStringParameters). Предположение: на обычном сервере понадобится слой-адаптер, который собирает такое событие.', ev)
        nh = [B(f['path'], None, f['name']) for f in functions if not f['handler_line']]
        if nh:
            add('Backend', 'unknown', 'fact', 'У части функций не найдена точка входа handler', '', nh)
        dbf = [B(f['path'], f['db_line'], f['name']) for f in functions if f['db_line']]
        if dbf:
            add('База данных', 'needs_setup', 'fact', 'Функции обращаются к PostgreSQL',
                'Факт: в коде есть подключение к базе. Нужна своя PostgreSQL и строка подключения.', dbf)
        stf = [B(f['path'], f['storage_line'], f['name']) for f in functions if f['storage_line']]
        if stf:
            add('Хранилище', 'needs_setup', 'fact', 'Функции работают с S3-хранилищем',
                'Факт: подключён boto3 или S3-клиент. Нужно S3-совместимое хранилище и ключи.', stf)
        unp = [B(rel, None, 'без «==»: %s' % ', '.join(n for n, pinned in lst if not pinned)[:80])
               for rel, lst in py_reqs.items() if any(not p for _, p in lst)]
        if unp:
            add('Backend', 'needs_setup', 'fact', 'Python-пакеты без закреплённой версии',
                'Факт: версия не зафиксирована через «==». Результат установки может отличаться со временем.', unp)
        nt = [B(f['path'], None, f['name']) for f in functions if not f['has_tests']]
        if nt:
            add('Backend', 'unknown', 'fact', 'У части функций нет tests.json', '', nt)
    if func_map is not None:
        hosts = sorted({urlparse(str(u)).netloc for u in func_map.values() if u})
        if func2url_users:
            add('Backend', 'needs_adaptation', 'fact', 'func2url.json используется кодом frontend',
                'Факт: файл содержит %d адресов (хосты: %s) и подключается из src. При смене хостинга адреса нужно заменить.' % (len(func_map), ', '.join(hosts)[:120]),
                [B('func2url.json')] + func2url_users)
        else:
            add('Backend', 'unknown', 'unknown', 'func2url.json найден, использование не обнаружено',
                'Факт: файл содержит %d адресов. Подключение из src не найдено — неизвестно, нужен ли он.' % len(func_map), [B('func2url.json')])

    if migrations:
        add('База данных', 'needs_setup', 'fact', 'SQL-миграции: %d' % len(migrations),
            'Факт: файлы найдены. Нужна своя PostgreSQL и применение по порядку имён. Применялись ли они — не проверено.%s'
            % ((' Создаваемые таблицы: %s.' % ', '.join(tables[:15])) if tables else ''),
            [B(m) for m in migrations])
        if schema_basis:
            add('База данных', 'needs_adaptation', 'fact', 'В миграциях прописано имя схемы вида t_pNNN_…',
                'Факт: имя схемы жёстко записано в SQL. При переносе его нужно заменить на свою схему.', schema_basis)
    elif functions and any(f['db_line'] for f in functions):
        add('База данных', 'unknown', 'unknown', 'Функции используют базу, а миграций в архиве нет',
            'Схему базы придётся выгрузить отдельно.', [])

    env_files = []
    for rel in sorted(files):
        base = rel.rsplit('/', 1)[-1]
        if base.startswith('.env'):
            txt = read(rel) or ''
            pairs = [(k, v) for k, v in ENV_FILE_KEY.findall(txt) if k.upper() not in IGNORE_ENV_NAMES]
            env_files.append({'file': rel, 'keys': len(pairs),
                              'filled': sum(1 for _, v in pairs if v.strip().strip('"\'')),
                              'is_example': bool(re.search(r'(example|sample|template|dist)$', base))})
            for k, _ in pairs:
                lst = env_found.setdefault(k, [])
                if not any(f == rel for f, _l in lst):
                    lst.append((rel, None))
    env_vars = [
        {'name': n, 'files': [B(f, l) for f, l in locs[:5]], 'client_side': n.startswith('VITE_')}
        for n, locs in sorted(env_found.items())
    ]
    if env_vars:
        add('Окружение', 'needs_setup', 'fact', 'Код читает переменные окружения: %d' % len(env_vars),
            'Факт: имена найдены в коде или .env-файлах. Значения не читались и не сохранялись. Какие из них обязательны — автоматически не определено.',
            [B(v['files'][0]['file'], v['files'][0].get('line'), v['name']) for v in env_vars])
        cs = [v for v in env_vars if v['client_side']]
        if cs:
            add('Окружение', 'needs_setup', 'fact', 'Переменные VITE_* попадают в браузер',
                'Факт: значения с префиксом VITE_ встраиваются в публичный код сайта. Секреты в них хранить нельзя.',
                [B(v['files'][0]['file'], v['files'][0].get('line'), v['name']) for v in cs])
    real_env = [e for e in env_files if not e['is_example']]
    if real_env:
        add('Окружение', 'needs_setup', 'fact', 'В архиве лежит файл .env',
            'Факт: файл присутствует, заполненных значений в нём: %d. Сами значения не читались и не сохранены. Не публикуйте такой архив.'
            % sum(e['filled'] for e in real_env), [B(e['file']) for e in real_env])
    if '.npmrc' in files:
        ntxt = read('.npmrc') or ''
        add('Окружение', 'needs_setup', 'fact', 'Есть .npmrc',
            'Факт: файл настроек npm.%s Значения не сохранялись.' % (' В нём есть строка с токеном авторизации.' if '_authToken' in ntxt or '_auth=' in ntxt else ''),
            [B('.npmrc', _first_line(ntxt, r'registry|_auth'))])

    if secret_hits:
        facts = [h for h in secret_hits if h[1] == 'fact']
        guess = [h for h in secret_hits if h[1] == 'assumption']
        if facts:
            add('Секреты', 'needs_setup', 'fact', 'В файлах найден приватный ключ',
                'Факт: обнаружен блок приватного ключа. Значение не сохранено. Уберите ключ из кода и перевыпустите его.',
                [B(f, l, k) for k, c, f, l in facts])
        if guess:
            add('Секреты', 'needs_setup', 'assumption', 'Возможные секреты в коде',
                'Предположение: места похожи на пароль, ключ или токен. Это могут быть и тестовые значения. Значения не сохранены — откройте указанные строки и проверьте.',
                [B(f, l, k) for k, c, f, l in guess])

    deploy = [c for c in configs if re.match(r'^(vercel\.json|netlify\.toml|Dockerfile|docker-compose\.ya?ml|\.github/.+)$', c)]
    if deploy:
        add('Публикация', 'portable', 'fact', 'Найдены файлы развёртывания', 'Могут пригодиться при переносе. Работоспособность не проверялась.', [B(c) for c in deploy])

    if skipped:
        add('Архив', 'portable', 'fact', 'Служебные папки пропущены',
            'Содержимое не читалось: %s.' % ', '.join('%s (%d)' % (k, v) for k, v in sorted(skipped.items())), [])

    tree = [[p, files[p].file_size] for p in sorted(files)[:MAX_TREE]]
    if len(files) > MAX_TREE:
        warnings.append('Дерево файлов обрезано до %d записей из %d.' % (MAX_TREE, len(files)))

    counts = {'portable': 0, 'needs_setup': 0, 'needs_adaptation': 0, 'unknown': 0}
    certainty = {'fact': 0, 'assumption': 0, 'unknown': 0}
    for it in items:
        counts[it['status']] += 1
        certainty[it['certainty']] += 1

    report = {
        'version': 2,
        'notice': 'Статический анализ: код не запускался, зависимости не устанавливались, команды не выполнялись.',
        'verification': {'install': 'not_verified', 'build': 'not_verified', 'run': 'not_verified'},
        'archive': {'filename': filename, 'compressed': len(data), 'files': len(files),
                    'uncompressed': total_size, 'root_folder': root_prefix.rstrip('/')},
        'scan': {'files_scanned': scanned, 'files_text_total': len(candidates) + len(too_big), 'truncated': truncated},
        'stack': stack_tags,
        'package': {'name': (pkg or {}).get('name', ''), 'version': (pkg or {}).get('version', ''),
                    'scripts': scripts, 'prod': prod, 'dev': dev},
        'commands': {'package_manager': pm or '', 'install': install, 'dev': dev_cmd, 'build': build_cmd,
                     'output_dir': out_dir, 'node_version': node_version},
        'lockfiles': lockfiles,
        'configs': configs,
        'functions': functions,
        'migrations': migrations,
        'tables': tables,
        'python': {k: [n for n, _ in v] for k, v in py_reqs.items()},
        'env_vars': env_vars,
        'env_files': env_files,
        'extensions': top_ext,
        'skipped_dirs': skipped,
        'warnings': warnings,
        'items': items,
        'counts': counts,
        'certainty': certainty,
    }
    return {'report': report, 'tree': tree}
