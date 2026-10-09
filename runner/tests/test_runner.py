import sys, os, io, json, zipfile, shutil, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import runner as R

SHA = 'a' * 40
def mkzip(entries, root='owner-repo-aaaaaaa', comment=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.comment = (comment if comment is not None else SHA).encode()
        for n, c in entries:
            z.writestr((root + '/' + n) if root else n, c)
    return b.getvalue()

class FakeCab:
    def __init__(self, cancel_after=None):
        self.reports = []; self.cancel_after = cancel_after
    def report(self, jid, **f):
        self.reports.append(f)
        return {'cancel': bool(self.cancel_after is not None and len(self.reports) > self.cancel_after), 'accepted': True}

def cfg(**kw):
    c = dict(R.DEFAULTS); c.update(work_dir='/tmp/rt/work', docker_bin='' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fakedocker.py') + '',
        install_timeout=5, build_timeout=5, github_token='ghp_' + 'A'*30)
    c.update(kw); R.register_secret(c['github_token']); return c

def job(**kw):
    j = dict(id=1, repo='owner/repo', branch='main', commit_sha=SHA, install_cmd='npm ci', build_cmd='npm run build',
             node_major=20, output_dir='dist', allow_scripts=False)
    j.update(kw); return j

GOOD = [('package.json', '{"scripts":{"build":"x"}}'), ('package-lock.json', '{}'), ('src/a.ts', 'x')]
def run(name, j=None, mode='ok', zipdata=None, cab=None, c=None):
    os.environ['FAKE_MODE'] = mode
    R.github_zip = lambda *a, **k: zipdata if zipdata is not None else mkzip(GOOD)
    cab = cab or FakeCab()
    res = R.process_job(c or cfg(), cab, j or job())
    last = cab.reports[-1]
    print('%-34s -> %-9s | exit_i=%s exit_b=%s files=%s err=%r' % (name, res, last.get('exit_install'), last.get('exit_build'), last.get('output_files'), (last.get('error') or '')[:70]))
    return res, cab

fails = []
def expect(cond, msg):
    if not cond: fails.append(msg); print('   !! ПРОВАЛ:', msg)

res, cab = run('успешная сборка'); expect(res == 'success', 'success')
log = cab.reports[-1]['log']
expect('github_pat_' not in log and 'pw@' not in log, 'секреты в журнале')
expect(cab.reports[-1]['output_files'] == 2 and cab.reports[-1]['output_bytes'] > 0, 'статистика dist')
expect(not os.path.exists('/tmp/rt/work/job-1'), 'рабочая папка не удалена')

open('/tmp/rt/dk.log', 'w').close(); os.environ['FAKE_LOG'] = '/tmp/rt/dk.log'
run('аргументы Docker')
calls = [json.loads(l) for l in open('/tmp/rt/dk.log') if '"run"' in l]
inst, build = ' '.join(calls[0]), ' '.join(calls[1])
for flag in ['--cap-drop ALL', 'no-new-privileges', '--read-only', '--memory 2g', '--pids-limit', '--ignore-scripts', '--user']:
    expect(flag in inst, 'install без ' + flag)
expect('--network none' in build, 'build должен идти без сети')
expect('--network' not in inst, 'install имеет сеть (нужно для npm)')
expect('--privileged' not in inst + build and 'docker.sock' not in inst + build, 'опасные флаги')
expect(inst.count('-v ') == 1, 'ровно один том')
os.environ.pop('FAKE_LOG')

run('со скриптами зависимостей', j=job(allow_scripts=True))
calls = [json.loads(l) for l in open('/tmp/rt/dk.log')]
run('сбой установки', mode='install_fail')
run('сбой сборки', mode='build_fail')
res, _ = run('таймаут', mode='slow', c=cfg(install_timeout=2)); expect(res == 'timeout', 'timeout')
res, _ = run('отмена из кабинета', mode='slow', cab=FakeCab(cancel_after=2)); expect(res == 'cancelled', 'cancel')

run('нет package.json', zipdata=mkzip([('a.txt', 'x')]))
run('npm ci без lock-файла', zipdata=mkzip([('package.json', '{}')]))
run('чужое имя папки', zipdata=mkzip(GOOD, root='owner-repo-bbbbbbb'))
r_, _ = run('верная папка, чужой SHA в ZIP', zipdata=mkzip(GOOD, comment='a'*7 + 'b'*33)); expect(r_ == 'error', 'подмена SHA')
r_, _ = run('верная папка, нет комментария', zipdata=mkzip(GOOD, comment='')); expect(r_ == 'error', 'нет SHA в комментарии')
run('path traversal', zipdata=mkzip([('../../evil.txt', 'x'), ('package.json', '{}')]))
def sym():
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.comment = SHA.encode()
        z.writestr('owner-repo-aaaaaaa/package.json', '{}')
        i = zipfile.ZipInfo('owner-repo-aaaaaaa/link'); i.external_attr = 0o120777 << 16; z.writestr(i, '/etc/passwd')
    return b.getvalue()
run('симлинк', zipdata=sym())
run('не ZIP', zipdata=b'hello')
run('злая команда установки', j=job(install_cmd='rm -rf /'))
run('злое repo', j=job(repo='a/b; rm -rf /'))
run('злая папка результата', j=job(output_dir='../../etc'))
run('битый SHA', j=job(commit_sha='xyz'))

class RevokedCab:
    def __init__(self): self.n = 0
    def report(self, jid, **f):
        self.n += 1
        if self.n > 3: raise R.KeyRevoked('revoked')
        return {'cancel': False}
open('/tmp/rt/dk.log','w').close(); os.environ['FAKE_LOG'] = '/tmp/rt/dk.log'
os.environ['FAKE_MODE'] = 'slow'; R.github_zip = lambda *a, **k: mkzip(GOOD)
t0 = time.time(); r_ = R.process_job(cfg(install_timeout=60), RevokedCab(), job()); dt = time.time() - t0
kills = [l for l in open('/tmp/rt/dk.log') if '"kill"' in l]
print('%-34s -> %-9s | %.0f c, команд kill: %d' % ('ключ отозван посреди задания', r_, dt, len(kills)))
expect(r_ in ('error', 'cancelled') and kills and dt < 40, 'при отзыве ключа контейнер должен быть остановлен')
os.environ.pop('FAKE_LOG')

class Boom:
    def report(self, jid, **f): return {'cancel': False}
def crash(*a, **k): raise ValueError('boom')
R.safe_extract_orig = R.safe_extract; R.safe_extract = crash
r_ = R.process_job(cfg(), Boom(), job()); print('%-34s -> %-9s' % ('неожиданное исключение', r_)); expect(r_ == 'error', 'исключение не должно ронять runner')
R.safe_extract = R.safe_extract_orig
bomb = mkzip([('big.txt', '0' * (700 * 1024 * 1024 // 10))]) if False else None

print()
print('ПРОВАЛЕНО:' if fails else 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ', fails or '')
