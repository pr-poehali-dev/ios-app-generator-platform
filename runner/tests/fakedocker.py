#!/usr/bin/env python3
import sys, os, time, json
a = sys.argv[1:]
log = os.environ.get('FAKE_LOG')
if log:
    open(log, 'a').write(json.dumps(a) + '\n')
if a[0] == 'kill':
    sys.exit(0)
if a[0] != 'run':
    sys.exit(0)
vol = a[a.index('-v') + 1].split(':')[0]
cmd = a[-3:] if 'ignore-scripts' in ' '.join(a) else a[-2:]
joined = ' '.join(a)
mode = os.environ.get('FAKE_MODE', 'ok')
phase_build = '--network' in a and a[a.index('--network') + 1] == 'none'
if mode == 'slow':
    print('working...', flush=True); time.sleep(30); sys.exit(0)
if not phase_build:
    print('npm ci done; token=github_pat_11ABCDEFG0123456789abcdefghij registry https://u:pw@reg.example/x')
    if mode == 'install_fail':
        print('npm ERR! 404'); sys.exit(1)
    os.makedirs(os.path.join(vol, 'node_modules'), exist_ok=True)
    sys.exit(0)
print('vite build...')
if mode == 'build_fail':
    print('error TS2304 at src/a.ts:3'); sys.exit(2)
os.makedirs(os.path.join(vol, 'dist'), exist_ok=True)
open(os.path.join(vol, 'dist', 'index.html'), 'w').write('<html></html>')
open(os.path.join(vol, 'dist', 'a.js'), 'w').write('x' * 100)
sys.exit(0)
