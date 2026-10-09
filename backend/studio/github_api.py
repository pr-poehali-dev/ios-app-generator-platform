import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
MAX_ZIP_BYTES = 25 * 1024 * 1024
REQ_TIMEOUT = 6
MAX_TREE = 4000
ZIP_HOSTS = ('codeload.github.com',)

OWNER_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')
NAME_RE = re.compile(r'^[A-Za-z0-9._-]{1,100}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')
BRANCH_RE = re.compile(r'^[A-Za-z0-9._/@+-]{1,200}$')


class GitHubError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_repo(raw):
    s = str(raw or '').strip()
    if not s:
        raise GitHubError('Укажите репозиторий в виде owner/name или ссылку на GitHub')
    m = re.match(r'^git@github\.com:([^/]+)/(.+?)(?:\.git)?$', s)
    if m:
        owner, name = m.group(1), m.group(2)
    else:
        s = re.sub(r'^https?://(?:www\.)?github\.com/', '', s, flags=re.I)
        s = s.split('?')[0].split('#')[0].strip('/')
        parts = s.split('/')
        if len(parts) < 2:
            raise GitHubError('Репозиторий нужно указать как owner/name или ссылкой github.com/owner/name')
        owner, name = parts[0], parts[1]
        if name.lower().endswith('.git'):
            name = name[:-4]
    if not OWNER_RE.match(owner) or not NAME_RE.match(name) or name in ('.', '..'):
        raise GitHubError('Некорректное имя репозитория')
    return '%s/%s' % (owner, name)


def clean_branch(raw):
    b = str(raw or '').strip()
    if not b:
        return ''
    if not BRANCH_RE.match(b) or '..' in b or b.startswith('/') or b.endswith('/'):
        raise GitHubError('Некорректное имя ветки')
    return b


def _headers(token, accept='application/vnd.github+json'):
    h = {
        'Accept': accept,
        'User-Agent': 'ai-web-studio-readonly',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        h['Authorization'] = 'Bearer ' + token
    return h


def _explain(code, body, token):
    msg = ''
    try:
        msg = str(json.loads(body).get('message', ''))
    except (ValueError, AttributeError):
        pass
    low = msg.lower()
    if code == 401:
        return GitHubError('GitHub отклонил токен: он неверный или истёк', 422)
    if code == 403 and 'rate limit' in low:
        hint = '' if token else ' Добавьте токен — с ним лимит выше.'
        return GitHubError('Достигнут лимит запросов GitHub.' + hint, 429)
    if code == 403:
        return GitHubError('Доступ запрещён: у токена нет права читать содержимое репозитория (Contents: Read)', 422)
    if code == 404:
        if token:
            return GitHubError('Репозиторий или ветка не найдены, либо у токена нет к ним доступа', 422)
        return GitHubError('Репозиторий или ветка не найдены. Если репозиторий приватный, нужен токен', 422)
    if code == 409:
        return GitHubError('Репозиторий пуст', 422)
    return GitHubError('GitHub вернул ошибку %d' % code, 502)


def _get(path, token, accept='application/vnd.github+json'):
    req = urllib.request.Request(API + path, headers=_headers(token, accept))
    try:
        with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
            return r.status, dict(r.headers), r.read(5 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        raise _explain(e.code, e.read(4096).decode('utf-8', 'replace'), token)
    except (socket.timeout, TimeoutError):
        raise GitHubError('GitHub не ответил вовремя. Повторите попытку', 504)
    except urllib.error.URLError:
        raise GitHubError('Не удалось связаться с GitHub', 502)


def _json(path, token):
    _, headers, body = _get(path, token)
    try:
        return json.loads(body), headers
    except ValueError:
        raise GitHubError('GitHub вернул непонятный ответ', 502)


def repo_info(repo, token):
    data, headers = _json('/repos/%s' % repo, token)
    scopes = [x.strip() for x in str(headers.get('X-OAuth-Scopes', headers.get('x-oauth-scopes', ''))).split(',') if x.strip()]
    warnings = []
    if 'repo' in scopes or any(x.startswith(('write:', 'admin:', 'delete')) for x in scopes):
        warnings.append('Токен даёт права записи. Для кабинета достаточно чтения: создайте fine-grained токен только на этот репозиторий с правом Contents: Read-only.')
    perms = data.get('permissions') or {}
    if token and (perms.get('push') or perms.get('admin')):
        w = 'Этот токен позволяет записывать в репозиторий. Кабинет только читает, но лучше выдать токен с правом Contents: Read-only.'
        if w not in warnings and not warnings:
            warnings.append(w)
    return {
        'full_name': data.get('full_name') or repo,
        'private': bool(data.get('private')),
        'default_branch': data.get('default_branch') or 'main',
        'size_kb': data.get('size') or 0,
        'warnings': warnings,
    }


def commits(repo, branch, token, per_page=20):
    q = urllib.parse.urlencode({'sha': branch, 'per_page': per_page})
    data, _ = _json('/repos/%s/commits?%s' % (repo, q), token)
    out = []
    for c in data if isinstance(data, list) else []:
        commit = c.get('commit') or {}
        author = commit.get('author') or {}
        out.append({
            'sha': str(c.get('sha', ''))[:40],
            'message': str(commit.get('message', '')).split('\n')[0][:200],
            'author': str(author.get('name', ''))[:80],
            'date': str(author.get('date', '')),
        })
    return out


def tree(repo, branch, token):
    ref = urllib.parse.quote(branch, safe='')
    data, _ = _json('/repos/%s/git/trees/%s?recursive=1' % (repo, ref), token)
    items = []
    skipped = 0
    for t in data.get('tree', []):
        if t.get('type') != 'blob' or t.get('mode') == '120000':
            skipped += 1
            continue
        items.append([str(t.get('path', '')), int(t.get('size') or 0)])
    items.sort(key=lambda x: x[0])
    total = len(items)
    return {
        'files': items[:MAX_TREE], 'total': total,
        'truncated': bool(data.get('truncated')) or total > MAX_TREE,
        'skipped': skipped,
    }


def download_zip(repo, branch, token):
    ref = urllib.parse.quote(branch, safe='')
    url = API + '/repos/%s/zipball/%s' % (repo, ref)
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers=_headers(token))
    location = ''
    try:
        opener.open(req, timeout=REQ_TIMEOUT)
        raise GitHubError('GitHub не вернул ссылку на архив', 502)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            location = e.headers.get('Location', '')
        else:
            raise _explain(e.code, e.read(4096).decode('utf-8', 'replace'), token)
    except (socket.timeout, TimeoutError):
        raise GitHubError('GitHub не ответил вовремя. Повторите попытку', 504)
    except urllib.error.URLError:
        raise GitHubError('Не удалось связаться с GitHub', 502)

    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != 'https' or parsed.hostname not in ZIP_HOSTS:
        raise GitHubError('GitHub вернул неожиданный адрес архива — загрузка отклонена', 502)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(location, headers={'User-Agent': 'ai-web-studio-readonly'}), timeout=REQ_TIMEOUT) as r:
            length = r.headers.get('Content-Length')
            if length and length.isdigit() and int(length) > MAX_ZIP_BYTES:
                raise GitHubError('Репозиторий слишком большой для аудита: архив больше %d МБ' % (MAX_ZIP_BYTES // 1048576), 413)
            chunks, size = [], 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise GitHubError('Репозиторий слишком большой для аудита: архив больше %d МБ' % (MAX_ZIP_BYTES // 1048576), 413)
                chunks.append(chunk)
                if time.monotonic() - started > 25:
                    raise GitHubError('Загрузка архива заняла слишком много времени', 504)
            return b''.join(chunks)
    except (socket.timeout, TimeoutError):
        raise GitHubError('Загрузка архива прервана по времени. Если репозиторий крупный, увеличьте таймаут функции', 504)
    except urllib.error.URLError:
        raise GitHubError('Не удалось скачать архив с GitHub', 502)
