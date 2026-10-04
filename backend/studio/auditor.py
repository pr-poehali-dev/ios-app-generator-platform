import io
import json
import re
import zipfile
from urllib.parse import urlparse

MAX_ENTRIES = 20000
MAX_TOTAL_UNCOMPRESSED = 300 * 1024 * 1024
MAX_READ = 512 * 1024
MAX_TEXT_FILES = 800
MAX_TOTAL_READ = 25 * 1024 * 1024
MAX_TREE = 4000

SKIP_DIRS = {
    'node_modules', '.git', 'dist', 'build', '.next', '__pycache__', '.venv',
    'venv', '.cache', 'coverage', '.turbo', '.idea', '.vscode',
}
TEXT_EXT = (
    '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.py', '.html', '.css',
    '.json', '.sql', '.toml', '.yml', '.yaml', '.txt', '.cfg', '.ini',
)
IGNORE_ENV_NAMES = {'MODE', 'DEV', 'PROD', 'BASE_URL', 'SSR', 'NODE_ENV'}
PLATFORM_ENV_NAMES = {
    'DATABASE_URL', 'MAIN_DB_SCHEMA', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
}
LOCKFILES = ['bun.lockb', 'bun.lock', 'pnpm-lock.yaml', 'yarn.lock', 'package-lock.json']
CONFIG_PATTERNS = [
    r'^vite\.config\.\w+$', r'^tailwind\.config\.\w+$', r'^tsconfig[\w.]*\.json$',
    r'^eslint\.config\.\w+$', r'^\.eslintrc[\w.]*$', r'^postcss\.config\.\w+$',
    r'^components\.json$', r'^vercel\.json$', r'^netlify\.toml$', r'^Dockerfile$',
    r'^docker-compose\.ya?ml$', r'^next\.config\.\w+$', r'^\.github/workflows/.+$',
    r'^func2url\.json$',
]

ENV_PATTERNS = [
    re.compile(r'os\.environ\[\s*[\'"]([A-Za-z0-9_]+)[\'"]\s*\]'),
    re.compile(r'os\.environ\.get\(\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
    re.compile(r'os\.getenv\(\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
    re.compile(r'import\.meta\.env\.([A-Za-z0-9_]+)'),
    re.compile(r'process\.env\.([A-Za-z0-9_]+)'),
]
ENV_FILE_KEY = re.compile(r'^\s*(?:export\s+)?([A-Za-z][A-Za-z0-9_]*)\s*=', re.M)
POEHALI_HOST = re.compile(r'(?:https?:)?//([a-z0-9.-]*poehali\.dev)', re.I)
SCRIPT_SRC = re.compile(r'<script[^>]*\ssrc=["\']([^"\']+)["\']', re.I)
SCHEMA_PREFIX = re.compile(r'\bt_p\d{4,}_[a-z0-9_]+\b')
PRIVATE_KEY = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')


class AuditError(Exception):
    pass


def _clean_name(raw: str):
    name = raw.replace('\\', '/')
    while name.startswith('./'):
        name = name[2:]
    if not name or name.startswith('/') or re.match(r'^[A-Za-z]:', name):
        return None
    parts = name.split('/')
    if '..' in parts:
        return None
    return name


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _status_counts(items):
    counts = {'portable': 0, 'needs_setup': 0, 'needs_adaptation': 0, 'unknown': 0}
    for it in items:
        counts[it['status']] += 1
    return counts


def _parse_requirements(text: str):
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '-')):
            continue
        name = re.split(r'[<>=!~\[; @]', line)[0].strip()
        if name:
            names.append(name)
    return names


def audit_zip(data: bytes, filename: str) -> dict:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise AuditError('Файл не является ZIP-архивом или повреждён')
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise AuditError('В архиве слишком много файлов (больше %d)' % MAX_ENTRIES)
    if sum(i.file_size for i in infos) > MAX_TOTAL_UNCOMPRESSED:
        raise AuditError('Распакованный размер архива превышает 300 МБ — разбор отменён')

    warnings = []
    unsafe = 0
    symlinks = 0
    encrypted = 0
    entries = []
    for info in infos:
        if info.is_dir():
            continue
        name = _clean_name(info.filename)
        if name is None:
            unsafe += 1
            continue
        if name.startswith('__MACOSX/') or name.endswith('.DS_Store'):
            continue
        if _is_symlink(info):
            symlinks += 1
            continue
        if info.flag_bits & 1:
            encrypted += 1
            continue
        entries.append((name, info))

    if unsafe:
        warnings.append('Пропущено %d записей с небезопасными путями (../ или абсолютные)' % unsafe)
    if symlinks:
        warnings.append('Пропущено %d символических ссылок' % symlinks)
    if encrypted:
        warnings.append('Пропущено %d зашифрованных файлов — их содержимое недоступно' % encrypted)
    if not entries:
        raise AuditError('В архиве нет читаемых файлов')

    tops = {n.split('/')[0] for n, _ in entries if '/' in n}
    all_nested = all('/' in n for n, _ in entries)
    root_prefix = ''
    if all_nested and len(tops) == 1:
        root_prefix = tops.pop() + '/'
    files = {}
    skipped = {}
    for name, info in entries:
        rel = name[len(root_prefix):] if root_prefix else name
        if not rel:
            continue
        parts = rel.split('/')
        hit = next((p for p in parts[:-1] if p in SKIP_DIRS), None)
        if hit:
            skipped[hit] = skipped.get(hit, 0) + 1
            continue
        files[rel] = info

    state = {'read_bytes': 0, 'text_files': 0}
    cache = {}

    def read(path: str):
        if path in cache:
            return cache[path]
        info = files.get(path)
        text = None
        if info is not None and state['read_bytes'] < MAX_TOTAL_READ:
            try:
                with zf.open(info) as fh:
                    raw = fh.read(MAX_READ + 1)
                state['read_bytes'] += len(raw)
                if len(raw) <= MAX_READ and b'\x00' not in raw[:2048]:
                    text = raw.decode('utf-8', errors='replace')
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
                text = None
        cache[path] = text
        return text

    items = []

    def add(category, status, title, detail='', evidence=None):
        items.append({
            'category': category, 'status': status, 'title': title,
            'detail': detail, 'evidence': (evidence or [])[:12],
        })

    ext_counts = {}
    total_size = 0
    for rel, info in files.items():
        total_size += info.file_size
        base = rel.rsplit('/', 1)[-1]
        ext = ('.' + base.rsplit('.', 1)[-1].lower()) if '.' in base else '(без расширения)'
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    top_ext = sorted(ext_counts.items(), key=lambda kv: -kv[1])[:10]

    configs = sorted(
        rel for rel in files
        if any(re.match(p, rel) for p in CONFIG_PATTERNS)
    )
    lockfiles = [lf for lf in LOCKFILES if lf in files]

    pkg = None
    pkg_text = read('package.json') if 'package.json' in files else None
    if pkg_text:
        try:
            parsed = json.loads(pkg_text)
            if isinstance(parsed, dict):
                pkg = parsed
        except ValueError:
            warnings.append('package.json не удалось разобрать как JSON')
    extra_pkgs = sorted(
        p for p in files
        if p.endswith('/package.json') and p.count('/') <= 2
    )

    prod = dict(pkg.get('dependencies', {})) if pkg else {}
    dev = dict(pkg.get('devDependencies', {})) if pkg else {}
    all_deps = {**dev, **prod}

    stack_tags = []
    if pkg:
        if 'react' in all_deps:
            stack_tags.append('React')
        if 'vue' in all_deps:
            stack_tags.append('Vue')
        if 'svelte' in all_deps:
            stack_tags.append('Svelte')
        if 'next' in all_deps:
            stack_tags.append('Next.js')
        if 'vite' in all_deps:
            stack_tags.append('Vite')
        if 'react-scripts' in all_deps:
            stack_tags.append('Create React App')
        if 'typescript' in all_deps or 'tsconfig.json' in files:
            stack_tags.append('TypeScript')
        if 'tailwindcss' in all_deps:
            stack_tags.append('Tailwind CSS')
        if 'components.json' in files:
            stack_tags.append('shadcn/ui')
        if 'react-router-dom' in all_deps:
            stack_tags.append('React Router')
        if '@tanstack/react-query' in all_deps:
            stack_tags.append('TanStack Query')
    backend_fn_re = re.compile(r'^backend/([^/]+)/index\.(py|ts)$')
    functions = []
    for rel in sorted(files):
        m = backend_fn_re.match(rel)
        if not m:
            continue
        fdir = 'backend/%s' % m.group(1)
        src = read(rel) or ''
        reqs = _parse_requirements(read(fdir + '/requirements.txt') or '') if fdir + '/requirements.txt' in files else []
        functions.append({
            'name': m.group(1),
            'path': rel,
            'language': 'Python' if m.group(2) == 'py' else 'TypeScript',
            'has_handler': bool(re.search(r'def\s+handler\s*\(|export\s+(?:async\s+)?(?:function\s+)?handler', src)),
            'has_tests': (fdir + '/tests.json') in files,
            'requirements': reqs[:40],
            'uses_db': bool(re.search(r'psycopg|DATABASE_URL|asyncpg|pg\b', src)),
            'uses_storage': bool(re.search(r'boto3|bucket\.poehali\.dev|S3Client', src)),
        })
    if functions:
        stack_tags.append('Backend-функции (%d)' % len(functions))

    func_map = None
    if 'func2url.json' in files:
        try:
            parsed = json.loads(read('func2url.json') or '')
            if isinstance(parsed, dict):
                func_map = parsed
        except ValueError:
            warnings.append('func2url.json не удалось разобрать')

    migrations = sorted(
        p for p in files
        if p.endswith('.sql') and re.search(r'(^|/)(db_migrations|migrations)/', p)
    )
    schema_refs = []
    for mig in migrations[:200]:
        txt = read(mig)
        if txt and SCHEMA_PREFIX.search(txt):
            schema_refs.append(mig)

    py_root = [p for p in ('requirements.txt', 'pyproject.toml', 'Pipfile') if p in files]
    py_deps = {}
    for rel in files:
        if rel.endswith('requirements.txt'):
            py_deps[rel] = _parse_requirements(read(rel) or '')[:60]

    pm = None
    if lockfiles:
        pm = {'bun.lockb': 'bun', 'bun.lock': 'bun', 'pnpm-lock.yaml': 'pnpm',
              'yarn.lock': 'yarn', 'package-lock.json': 'npm'}[lockfiles[0]]
    pm_src = 'по lock-файлу %s' % lockfiles[0] if lockfiles else None
    if pm is None and pkg:
        pm = 'npm'
        pm_src = 'по умолчанию (lock-файл не найден)'
    scripts = pkg.get('scripts', {}) if pkg else {}
    run_prefix = {'npm': 'npm run', 'pnpm': 'pnpm', 'yarn': 'yarn', 'bun': 'bun run'}.get(pm or 'npm')

    def cmd(script):
        if script in scripts:
            return {'value': '%s %s' % (run_prefix, script), 'script': scripts[script],
                    'source': 'scripts.%s в package.json' % script, 'confidence': 'found'}
        return {'value': '', 'script': '', 'source': 'скрипт не найден', 'confidence': 'none'}

    if pm == 'npm':
        install_val = 'npm ci' if 'package-lock.json' in files else 'npm install'
    elif pm:
        install_val = '%s install' % pm
    else:
        install_val = ''
    install = {
        'value': install_val,
        'source': pm_src or 'package.json не найден',
        'confidence': 'found' if lockfiles else ('inferred' if pm else 'none'),
    }
    dev_cmd = cmd('dev')
    if not dev_cmd['value']:
        dev_cmd = cmd('start')
    build_cmd = cmd('build')

    out_dir = {'value': '', 'source': 'не определено', 'confidence': 'none'}
    vite_cfg = next((c for c in configs if re.match(r'^vite\.config\.\w+$', c)), None)
    if vite_cfg:
        m = re.search(r'outDir\s*:\s*[\'"]([^\'"]+)[\'"]', read(vite_cfg) or '')
        if m:
            out_dir = {'value': m.group(1), 'source': 'outDir в %s' % vite_cfg, 'confidence': 'found'}
        else:
            out_dir = {'value': 'dist', 'source': 'значение Vite по умолчанию (в конфиге не задано)', 'confidence': 'inferred'}
    elif 'next' in all_deps:
        out_dir = {'value': '.next', 'source': 'значение Next.js по умолчанию', 'confidence': 'inferred'}
    elif 'react-scripts' in all_deps:
        out_dir = {'value': 'build', 'source': 'значение Create React App по умолчанию', 'confidence': 'inferred'}

    node_version = {'value': '', 'source': 'не указана', 'confidence': 'none'}
    for nf in ('.nvmrc', '.node-version'):
        if nf in files and (read(nf) or '').strip():
            node_version = {'value': read(nf).strip(), 'source': nf, 'confidence': 'found'}
            break
    else:
        eng = (pkg or {}).get('engines', {}) if isinstance((pkg or {}).get('engines', {}), dict) else {}
        if eng.get('node'):
            node_version = {'value': str(eng['node']), 'source': 'engines.node в package.json', 'confidence': 'found'}

    env_found = {}
    poehali_hosts = {}
    poehali_files = {}
    private_key_files = []
    sql_or_text = [
        p for p in sorted(files)
        if p.lower().endswith(TEXT_EXT)
        and not p.endswith(('package-lock.json', 'bun.lock', 'yarn.lock'))
        and files[p].file_size <= MAX_READ
    ]
    for rel in sql_or_text[:MAX_TEXT_FILES]:
        txt = read(rel)
        if not txt:
            continue
        for pat in ENV_PATTERNS:
            for name in pat.findall(txt):
                if name.upper() in IGNORE_ENV_NAMES:
                    continue
                env_found.setdefault(name, set()).add(rel)
        for host in POEHALI_HOST.findall(txt):
            h = host.lower()
            poehali_hosts[h] = poehali_hosts.get(h, 0) + 1
            poehali_files.setdefault(h, set()).add(rel)
        if PRIVATE_KEY.search(txt):
            private_key_files.append(rel)

    env_files = []
    for rel in sorted(files):
        base = rel.rsplit('/', 1)[-1]
        if base.startswith('.env'):
            env_files.append(rel)
            txt = read(rel)
            if txt:
                for key in ENV_FILE_KEY.findall(txt):
                    if key.upper() not in IGNORE_ENV_NAMES:
                        env_found.setdefault(key, set()).add(rel)
    real_env_files = [e for e in env_files if not re.search(r'(example|sample|template|dist)$', e)]

    env_vars = [
        {
            'name': n,
            'files': sorted(fs)[:5],
            'likely_platform': n in PLATFORM_ENV_NAMES,
            'client_side': n.startswith('VITE_'),
        }
        for n, fs in sorted(env_found.items())
    ]

    index_html_poehali = []
    if 'index.html' in files:
        html = read('index.html') or ''
        for src in SCRIPT_SRC.findall(html):
            if 'poehali.dev' in src:
                index_html_poehali.append(src)

    poehali_pkgs = sorted(n for n in all_deps if 'poehali' in n.lower())
    poehali_marker = bool(
        index_html_poehali or poehali_pkgs or func_map is not None
        or poehali_hosts or schema_refs
    )

    if pkg is None and 'package.json' in files:
        add('Frontend', 'unknown', 'package.json есть, но не прочитан',
            'Файл повреждён или слишком большой — стек и команды определить нельзя.')
    elif pkg is None:
        add('Frontend', 'unknown', 'package.json не найден в корне проекта',
            'Без него нельзя определить зависимости и команды запуска. Возможно, проект лежит во вложенной папке.',
            extra_pkgs)
    else:
        stack_line = ', '.join(t for t in stack_tags if not t.startswith('Backend')) or 'стек не распознан'
        if 'react' in all_deps and ('vite' in all_deps or 'next' in all_deps or 'react-scripts' in all_deps):
            add('Frontend', 'portable', 'Стандартный frontend-стек',
                'Распознан по package.json: %s. Всего пакетов: %d (рабочих %d, dev %d). Доступность пакетов и совместимость версий не проверялись.'
                % (stack_line, len(all_deps), len(prod), len(dev)))
        else:
            add('Frontend', 'unknown', 'Стек не распознан однозначно',
                'Найдено: %s. Пакетов: %d.' % (stack_line, len(all_deps)))
        if poehali_pkgs:
            add('Frontend', 'needs_adaptation', 'Пакеты с именем poehali в зависимостях',
                'Нужно проверить, доступны ли они вне платформы, и при необходимости заменить.', poehali_pkgs)

    if extra_pkgs:
        add('Frontend', 'unknown', 'Найдены вложенные package.json',
            'Возможно, это монорепозиторий. Анализировался только корневой файл.', extra_pkgs)

    if pkg:
        if len(lockfiles) == 1:
            add('Сборка', 'portable', 'Lock-файл: %s' % lockfiles[0], 'Версии зависимостей зафиксированы.')
        elif len(lockfiles) > 1:
            add('Сборка', 'needs_setup', 'Несколько lock-файлов',
                'Нужно выбрать один менеджер пакетов и удалить лишние lock-файлы. Выбран первый по приоритету: %s.' % pm,
                lockfiles)
        else:
            add('Сборка', 'needs_setup', 'Lock-файл не найден',
                'Версии зависимостей не зафиксированы — сборка может отличаться от оригинала.')

        if build_cmd['confidence'] == 'found':
            add('Сборка', 'portable', 'Команда сборки найдена', '%s → %s' % (build_cmd['value'], build_cmd['script']))
        else:
            add('Сборка', 'unknown', 'Команда сборки не найдена', 'В package.json нет скрипта build.')
        if dev_cmd['confidence'] != 'found':
            add('Сборка', 'unknown', 'Команда запуска не найдена', 'В package.json нет скрипта dev или start.')
        if node_version['confidence'] == 'none':
            add('Сборка', 'needs_setup', 'Версия Node.js не указана',
                'Подберите версию при первом запуске на своём компьютере или сервере.')
        if out_dir['confidence'] == 'inferred':
            add('Сборка', 'unknown', 'Папка результата сборки — предположение', out_dir['source'])

    if index_html_poehali:
        add('Платформа Poehali', 'needs_adaptation', 'Служебные скрипты платформы в index.html',
            'Страница подгружает скрипты с poehali.dev. Для независимой работы их нужно проверить и убрать или заменить.',
            index_html_poehali)

    if functions:
        names = ['%s (%s)' % (f['name'], f['language']) for f in functions]
        add('Backend', 'needs_adaptation', 'Backend-функции: %d' % len(functions),
            'Написаны под облачные функции платформы (точка входа handler). Для независимой работы нужен свой сервер или облако.',
            names)
        no_handler = [f['path'] for f in functions if not f['has_handler']]
        if no_handler:
            add('Backend', 'unknown', 'У части функций не найдена точка входа handler', '', no_handler)
        db_fn = [f['name'] for f in functions if f['uses_db']]
        if db_fn:
            add('База данных', 'needs_setup', 'Функции обращаются к PostgreSQL',
                'Нужна собственная база и строка подключения.', db_fn)
        st_fn = [f['name'] for f in functions if f['uses_storage']]
        if st_fn:
            add('Хранилище', 'needs_adaptation', 'Функции используют S3-хранилище',
                'Нужно своё S3-совместимое хранилище и замена адреса сервера, если в коде указан адрес платформы.', st_fn)

    if func_map is not None:
        hosts = sorted({urlparse(str(u)).netloc for u in func_map.values() if u})
        add('Backend', 'needs_adaptation', 'func2url.json: адреса функций привязаны к платформе',
            'Файл содержит %d адресов функций. После переноса их нужно заменить на свои.' % len(func_map), hosts)

    if migrations:
        if schema_refs:
            add('База данных', 'needs_adaptation', 'SQL-миграции содержат имя схемы платформы',
                'В %d из %d файлов есть имя вида t_pNNN_… — его нужно заменить на свою схему.'
                % (len(schema_refs), len(migrations)), schema_refs)
        else:
            add('База данных', 'needs_setup', 'SQL-миграции: %d' % len(migrations),
                'Обычный SQL, но нужна своя PostgreSQL и применение миграций по порядку.', migrations)
    elif functions:
        add('База данных', 'unknown', 'SQL-миграций не найдено',
            'Схема базы в архиве отсутствует — её придётся выгрузить отдельно.')

    if py_deps and not functions:
        add('Backend', 'needs_setup', 'Python-зависимости', 'Файлов requirements.txt: %d.' % len(py_deps), list(py_deps))
    elif py_root:
        add('Backend', 'needs_setup', 'Конфигурации Python в корне', '', py_root)

    ref_hosts_non_script = {h: c for h, c in poehali_hosts.items()}
    if ref_hosts_non_script:
        total_refs = sum(ref_hosts_non_script.values())
        ev = []
        for h in sorted(ref_hosts_non_script):
            ev.append('%s — %d упоминаний, например %s' % (h, ref_hosts_non_script[h], sorted(poehali_files[h])[0]))
        status = 'needs_adaptation'
        add('Платформа Poehali', status, 'Ссылки на инфраструктуру poehali.dev в коде',
            'Всего упоминаний: %d. Картинки и файлы на CDN платформы нужно скачать и разместить у себя.' % total_refs, ev)

    if env_vars:
        names = [v['name'] for v in env_vars]
        platform = [v['name'] for v in env_vars if v['likely_platform']]
        detail = 'Найдено переменных: %d. Значения не читались и не сохранялись.' % len(env_vars)
        if platform:
            detail += ' Из них обычно задаёт платформа: %s.' % ', '.join(platform)
        add('Окружение', 'needs_setup', 'Нужны переменные окружения', detail, names)
    if real_env_files:
        add('Окружение', 'needs_setup', 'В архиве лежит файл .env',
            'Проверьте, нет ли в нём реальных секретов, и не публикуйте архив. Значения не читались, учтены только имена.',
            real_env_files)
    if private_key_files:
        add('Окружение', 'needs_setup', 'В файлах найден блок приватного ключа',
            'Значение не сохранено. Уберите ключ из кода и перевыпустите его.', private_key_files)

    deploy_hints = [c for c in configs if re.match(r'^(vercel\.json|netlify\.toml|Dockerfile|docker-compose\.ya?ml|\.github/.+)$', c)]
    if deploy_hints:
        add('Публикация', 'portable', 'Найдены файлы развёртывания', 'Могут пригодиться для переноса.', deploy_hints)

    if skipped:
        sk = ['%s: %d файлов' % (k, v) for k, v in sorted(skipped.items())]
        add('Архив', 'portable', 'Служебные папки пропущены при анализе', 'Их содержимое не читалось.', sk)

    unread = len(sql_or_text) - MAX_TEXT_FILES
    if unread > 0:
        warnings.append('Текстовых файлов больше лимита анализа: %d не проверены на переменные и ссылки' % unread)

    tree_files = sorted(files)[:MAX_TREE]
    tree = [[p, files[p].file_size] for p in tree_files]
    if len(files) > MAX_TREE:
        warnings.append('Дерево файлов обрезано до %d записей из %d' % (MAX_TREE, len(files)))

    report = {
        'notice': 'Статический анализ: код не запускался, зависимости не устанавливались, команды не выполнялись.',
        'archive': {
            'filename': filename, 'compressed': len(data), 'files': len(files),
            'uncompressed': total_size, 'root_folder': root_prefix.rstrip('/'),
        },
        'poehali_detected': poehali_marker,
        'stack': stack_tags,
        'package': {
            'name': (pkg or {}).get('name', ''),
            'version': (pkg or {}).get('version', ''),
            'scripts': scripts,
            'prod': prod,
            'dev': dev,
        },
        'commands': {
            'package_manager': pm or '',
            'install': install, 'dev': dev_cmd, 'build': build_cmd,
            'output_dir': out_dir, 'node_version': node_version,
        },
        'lockfiles': lockfiles,
        'configs': configs,
        'functions': functions,
        'func2url': sorted(func_map.keys()) if func_map else [],
        'migrations': migrations,
        'python': {'files': py_deps, 'root': py_root},
        'env_vars': env_vars,
        'env_files': env_files,
        'poehali_refs': [
            {'host': h, 'count': c, 'files': sorted(poehali_files[h])[:5]}
            for h, c in sorted(poehali_hosts.items())
        ],
        'extensions': top_ext,
        'skipped_dirs': skipped,
        'warnings': warnings,
        'items': items,
        'counts': _status_counts(items),
    }
    return {'report': report, 'tree': tree}
