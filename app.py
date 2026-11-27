"""Lock In - local calendar / inbox / focus app.
Runs a tiny local server (stdlib only) and opens it in an app-style window.
Data lives in data/store.json (a backup of the previous save is kept as store.bak.json).
"""
import json, os, re, sys, threading, time, subprocess, webbrowser, shutil, io, zipfile, urllib.request, secrets, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))


def data_dir():
    # Your data lives OUTSIDE the app folder so reinstalling / deleting / updating the app never touches it.
    d = os.environ.get('LOCKIN_DATA')
    if d:
        return d
    if os.name == 'nt' and os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'LockIn')
    return os.path.join(BASE, 'data')


DATA = data_dir()
os.makedirs(DATA, exist_ok=True)
_old = os.path.join(BASE, 'data')
if os.path.abspath(_old) != os.path.abspath(DATA) and not os.path.exists(os.path.join(DATA, 'store.json')) \
        and os.path.exists(os.path.join(_old, 'store.json')):
    try:  # one-time migration from the old in-folder location
        shutil.copy2(os.path.join(_old, 'store.json'), os.path.join(DATA, 'store.json'))
    except Exception:
        pass
VERSION_FILE = os.path.join(BASE, 'version.txt')
STORE = os.path.join(DATA, 'store.json')
BAK = os.path.join(DATA, 'store.bak.json')
PROFILE = os.path.join(DATA, 'window-profile')
PORT = 47615
URL = 'http://127.0.0.1:%d/' % PORT
LOCK = threading.Lock()
last_ping = 0.0

# ---- connector (Claude <-> Lock In): token-protected command queue. The page applies the commands itself,
# so Claude can never overwrite what you are typing in the window.
TOKEN_FILE = os.path.join(DATA, 'agent.token')
QUEUE = []          # pending commands for the page
RESULTS = {}        # qid -> result reported by the page
QLOCK = threading.Lock()


def agent_token():
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            t = f.read().strip()
            if len(t) >= 16:
                return t
    except Exception:
        pass
    t = secrets.token_hex(24)
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        f.write(t)
    return t


AGENT_TOKEN = agent_token()

DEFAULT_UPDATE_URL = 'https://raw.githubusercontent.com/nishidaondrugs-spec/lock-in/main'
DEFAULT_SETTINGS = {
    'name': '', 'openOnWake': True, 'focusMin': 25, 'breakMin': 5,
    'remindDefault': 10, 'jobGoal': 5, 'updateUrl': DEFAULT_UPDATE_URL, 'autoUpdate': True,
    'jobSearches': [], 'epStudio': 'http://127.0.0.1:5055', 'epNext': 21, 'reelGoal': 6, 'gymGoal': 4, 'gymUrl': '',
}


def default_state():
    return {'items': [], 'settings': dict(DEFAULT_SETTINGS), 'top3': {'date': '', 'ids': []},
            'days': {}, 'fired': {}}


def load():
    st = default_state()
    for path in (STORE, BAK):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get('items'), list):
                st.update({k: v for k, v in d.items() if k != 'settings'})
                st['settings'].update(d.get('settings') or {})
                if not st['settings'].get('updateUrl'):
                    st['settings']['updateUrl'] = DEFAULT_UPDATE_URL
                return st
        except Exception:
            continue
    return st


def save(state):
    tmp = STORE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    if os.path.exists(STORE):
        try:
            shutil.copyfile(STORE, BAK)
        except Exception:
            pass
    os.replace(tmp, STORE)


# ---------------------------------------------------------------- window
def find_browser():
    cands = []
    if os.name == 'nt':
        for env in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
            root = os.environ.get(env)
            if not root:
                continue
            cands += [os.path.join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                      os.path.join(root, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    else:
        for n in ('microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser'):
            p = shutil.which(n)
            if p:
                cands.append(p)
        cands.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def open_window():
    exe = find_browser()
    if exe:
        args = [exe, '--app=' + URL, '--window-size=1440,900', '--user-data-dir=' + PROFILE,
                '--no-first-run', '--no-default-browser-check',
                '--autoplay-policy=no-user-gesture-required']
        try:
            subprocess.Popen(args)
            return
        except Exception:
            pass
    webbrowser.open(URL)


def toast(title, msg):
    if os.name != 'nt':
        return
    t = title.replace("'", "''")[:60]
    m = msg.replace("'", "''")[:120]
    ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
          "$n=New-Object System.Windows.Forms.NotifyIcon; $n.Icon=[System.Drawing.SystemIcons]::Information; "
          "$n.Visible=$true; $n.ShowBalloonTip(10000,'%s','%s',[System.Windows.Forms.ToolTipIcon]::None); "
          "Start-Sleep 11; $n.Dispose()" % (t, m))
    try:
        subprocess.Popen(['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps],
                         creationflags=0x08000000)
    except Exception:
        pass


# ---------------------------------------------------------------- reminders
def fire_info(it):
    """Mirror of the JS logic. Returns (due, fire, key) or None."""
    if not it.get('date') or it.get('done') or it.get('tentative') or it.get('remind') is None:
        return None
    try:
        t = it.get('time') or '09:00'
        due = datetime.strptime(it['date'] + ' ' + t, '%Y-%m-%d %H:%M')
        fire = due - timedelta(minutes=int(it['remind']))
        if it.get('snooze'):
            sn = datetime.strptime(it['snooze'], '%Y-%m-%dT%H:%M')
            if sn > fire:
                fire = sn
        return due, fire, fire.strftime('%Y-%m-%dT%H:%M')
    except Exception:
        return None


def recurs(it, d):
    r = it.get('repeat')
    if not r or not it.get('date'):
        return False
    ds = d.strftime('%Y-%m-%d')
    if ds < it['date'] or (it.get('until') and ds > it['until']) or ds in (it.get('skip') or []):
        return False
    if (d.weekday() + 1) % 7 not in r.get('days', []):
        return False
    iv = int(r.get('interval', 1) or 1)
    if iv > 1:
        s = datetime.strptime(it['date'], '%Y-%m-%d').date()
        weeks = ((d - timedelta(days=d.weekday())) - (s - timedelta(days=s.weekday()))).days // 7
        if weeks % iv:
            return False
    return True


def candidates(st, now):
    out = []
    today = now.date()
    ds = today.strftime('%Y-%m-%d')
    for it in st['items']:
        c = dict(it)
        if it.get('repeat'):
            if not recurs(it, today) or ds in (it.get('doneDates') or []):
                continue
            c['date'] = ds
            c['done'] = False
            c['snooze'] = (it.get('snoozes') or {}).get(ds)
            ov = (it.get('overrides') or {}).get(ds)
            if ov:
                c['time'] = ov.get('time')
            c['_key'] = it['id'] + '@' + ds
        else:
            c['_key'] = it['id']
        out.append(c)
    return out


def check_reminders():
    # the open window handles reminders itself; the server only steps in when it is closed
    if time.time() - last_ping < 30:
        return
    with LOCK:
        st = load()
        fired = st.setdefault('fired', {})
        hits = []
        now = datetime.now()
        for it in candidates(st, now):
            fi = fire_info(it)
            if not fi:
                continue
            due, fire, key = fi
            if now >= fire and now < due + timedelta(hours=2) and fired.get(it['_key']) != key:
                fired[it['_key']] = key
                hits.append((it, due))
        if hits:
            save(st)
    for it, due in hits:
        when = due.strftime('%H:%M') if it.get('time') else 'today'
        toast('Lock In: ' + it.get('title', ''), 'Starts ' + when)
    if hits:
        open_window()


def on_resume():
    time.sleep(10)
    st = load()
    if st['settings'].get('openOnWake', True) and time.time() - last_ping > 15:
        open_window()


def reminder_loop():
    last = time.time()
    while True:
        time.sleep(5)
        now = time.time()
        gap = now - last
        last = now
        if gap > 60:
            threading.Thread(target=on_resume, daemon=True).start()
        try:
            check_reminders()
        except Exception:
            pass


# ---------------------------------------------------------------- updates
def current_version():
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip() or '0'
    except Exception:
        return '0'


def _fetch(url, limit=20_000_000):
    if not url.lower().startswith('https://') and not url.startswith('http://127.0.0.1') and not url.startswith('http://localhost'):
        raise ValueError('update address must be https')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LockIn-updater'}), timeout=20) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError('download too large')
    return data


def _apply_zip(zb):
    z = zipfile.ZipFile(io.BytesIO(zb))
    names = [n for n in z.namelist() if not n.endswith('/')]
    cand = [n for n in names if n.endswith('static/index.html')]
    if not cand:
        raise ValueError('not a Lock In package')
    prefix = cand[0][:-len('static/index.html')]
    if prefix + 'app.py' not in names:
        raise ValueError('not a Lock In package')
    files = []
    for n in names:
        if not n.startswith(prefix):
            continue
        rel = n[len(prefix):]
        parts = rel.split('/')
        if not rel or parts[0] in ('data', '__pycache__') or '..' in parts or rel.startswith('/') or ':' in rel:
            continue
        files.append((rel, n))
    files.sort(key=lambda t: t[0] == 'app.py')  # app.py last
    for rel, n in files:
        out = os.path.join(BASE, *rel.split('/'))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with z.open(n) as f:
            blob = f.read()
        with open(out, 'wb') as g:
            g.write(blob)


def restart_self():
    show = time.time() - last_ping > 30   # reopen a window only if none is open
    code = "import time,subprocess;time.sleep(2);subprocess.Popen(%r)" % ([sys.executable, os.path.join(BASE, 'app.py')] + ([] if show else ['--no-window']),)
    flags = (0x00000200 | 0x08000000) if os.name == 'nt' else 0
    subprocess.Popen([sys.executable, '-c', code], creationflags=flags, close_fds=True)
    time.sleep(1.5)   # let the HTTP reply reach the window before exiting
    os._exit(0)


def check_update(url=None, apply=False, auto=False):
    url = (url or load()['settings'].get('updateUrl') or '').strip().rstrip('/')
    if not url:
        return {'status': 'no-url', 'version': current_version()}
    try:
        remote = _fetch(url + '/version.txt', 1000).decode().strip()
        if not remote or remote == current_version():
            return {'status': 'current', 'version': current_version()}
        if not apply:
            return {'status': 'available', 'version': current_version(), 'remote': remote}
        mark = os.path.join(DATA, 'update-state.json')
        if auto:
            try:
                with open(mark) as f:
                    m = json.load(f)
                if m.get('remote') == remote and time.time() - m.get('at', 0) < 86400:
                    return {'status': 'current', 'version': current_version()}
            except Exception:
                pass
        with open(mark, 'w') as f:
            json.dump({'remote': remote, 'at': time.time()}, f)
        _apply_zip(_fetch(url + '/lockin.zip'))
        threading.Thread(target=restart_self, daemon=True).start()
        return {'status': 'updated', 'version': current_version(), 'remote': remote}
    except Exception as e:
        return {'status': 'error', 'error': str(e)[:160], 'version': current_version()}


def update_loop():
    if os.environ.get('LOCKIN_NO_UPDATE'):
        return   # dev switch: never auto-update
    time.sleep(8)
    while True:
        try:
            st = load()['settings']
            if st.get('updateUrl') and st.get('autoUpdate', True):
                check_update(apply=True, auto=True)
        except Exception:
            pass
        time.sleep(6 * 3600)


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _agent_ok(self):
        t = self.headers.get('X-LockIn-Token', '')
        return bool(t) and secrets.compare_digest(t, AGENT_TOKEN)

    def do_GET(self):
        global last_ping
        p = self.path.split('?')[0]
        if p in ('/', '/index.html'):
            with open(os.path.join(BASE, 'static', 'index.html'), 'rb') as f:
                return self._send(200, f.read(), 'text/html; charset=utf-8')
        if p == '/api/state':
            last_ping = time.time()
            with LOCK:
                return self._send(200, load())
        if p == '/api/cloud':   # the online-sync key (stored only on this computer, never in the repo)
            if self.headers.get('X-LockIn') != '1':
                return self._send(403, {'error': 'forbidden'})
            try:
                with open(os.path.join(DATA, 'cloud.json'), encoding='utf-8') as f:
                    c = json.load(f)
            except Exception:
                c = {}
            return self._send(200, {'token': str(c.get('token') or '')})
        if p == '/api/queue':
            if self.headers.get('X-LockIn') != '1':
                return self._send(403, {'error': 'forbidden'})
            last_ping = time.time()
            with QLOCK:
                return self._send(200, {'cmds': list(QUEUE)})
        if p == '/api/agent/state':
            if not self._agent_ok():
                return self._send(403, {'error': 'bad token'})
            with LOCK:   # read-only: does not count as the page being open
                return self._send(200, load())
        if p == '/api/agent/result':
            if not self._agent_ok():
                return self._send(403, {'error': 'bad token'})
            qid = (self.path.split('qid=') + [''])[1].split('&')[0]
            with QLOCK:
                return self._send(200, {'done': qid in RESULTS, 'result': RESULTS.get(qid)})
        if p == '/api/rev':
            with LOCK:
                return self._send(200, {'rev': int(load().get('_rev') or 0)})
        if p == '/api/version':
            return self._send(200, {'version': current_version(), 'data': DATA})
        if p == '/api/ping':
            last_ping = time.time()
            return self._send(200, {'ok': True})
        if p == '/api/export':
            with LOCK:
                data = json.dumps(load(), indent=1, ensure_ascii=False)
            name = 'lockin-backup-%s.json' % datetime.now().strftime('%Y-%m-%d')
            return self._send(200, data, 'application/json',
                              {'Content-Disposition': 'attachment; filename=' + name})
        self._send(404, {'error': 'not found'})

    def do_PUT(self):
        global last_ping
        if self.path.split('?')[0] != '/api/state':
            return self._send(404, {'error': 'not found'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(n).decode('utf-8'))
            assert isinstance(body, dict) and isinstance(body.get('items'), list)
        except Exception:
            return self._send(400, {'error': 'bad body'})
        last_ping = time.time()
        with LOCK:
            cur = load()
            cur_rev = int(cur.get('_rev') or 0)
            cr = body.get('_rev')
            try:
                stale = cr is not None and int(cr) != cur_rev
            except Exception:
                stale = False
            if stale:   # someone else (another window, the connector...) saved since this page last synced
                return self._send(409, {'conflict': True, 'state': cur})
            merged = dict(body.get('fired') or {})
            for k, v in (cur.get('fired') or {}).items():
                if k not in merged or v > merged[k]:
                    merged[k] = v
            live = {i.get('id') for i in body['items']}
            merged = {k: v for k, v in merged.items() if k.split('@')[0] in live}
            body['fired'] = merged
            body['_rev'] = cur_rev + 1
            save(body)
        self._send(200, {'ok': True, 'fired': merged, 'rev': cur_rev + 1})

    def do_POST(self):
        if self.path.split('?')[0] == '/api/update':
            try:
                n = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            except Exception:
                body = {}
            try:
                res = check_update(body.get('url'), bool(body.get('apply')))
            except Exception as e:
                res = {'status': 'error', 'error': str(e)[:160], 'version': current_version()}
            return self._send(200, res)
        pp = self.path.split('?')[0]
        if pp in ('/api/queue/ack', '/api/agent/cmd'):
            try:
                n = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                assert isinstance(body, dict)
            except Exception:
                return self._send(400, {'error': 'bad body'})
            if pp == '/api/queue/ack':
                if self.headers.get('X-LockIn') != '1':
                    return self._send(403, {'error': 'forbidden'})
                res = body.get('results') or {}
                with QLOCK:
                    for qid, r in res.items():
                        RESULTS[str(qid)] = r
                    QUEUE[:] = [c for c in QUEUE if c.get('qid') not in set(res.keys())]
                    for k in list(RESULTS)[:-200]:
                        RESULTS.pop(k, None)
                return self._send(200, {'ok': True})
            if not self._agent_ok():
                return self._send(403, {'error': 'bad token'})
            if body.get('op') not in ('add', 'quick', 'update', 'complete', 'delete'):
                return self._send(400, {'error': 'unknown op'})
            body['qid'] = uuid.uuid4().hex[:10]
            with QLOCK:
                QUEUE.append(body)
            if time.time() - last_ping > 30:   # window is closed -> open it so the command gets applied
                threading.Thread(target=open_window, daemon=True).start()
            return self._send(200, {'qid': body['qid']})
        if self.path.split('?')[0] == '/api/cloud':
            if self.headers.get('X-LockIn') != '1':
                return self._send(403, {'error': 'forbidden'})
            try:
                n = int(self.headers.get('Content-Length', '0'))
                tok = str(json.loads(self.rfile.read(n).decode('utf-8') or '{}').get('token') or '').strip()
            except Exception:
                tok = ''
            if tok and not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', tok):
                return self._send(400, {'ok': False, 'error': 'That key does not look right.'})
            with open(os.path.join(DATA, 'cloud.json'), 'w', encoding='utf-8') as f:
                json.dump({'token': tok}, f)
            return self._send(200, {'ok': True})
        if self.path.split('?')[0] == '/api/open':   # open the EP Studio path saved in Settings (never an arbitrary path)
            if self.headers.get('X-LockIn') != '1':
                return self._send(403, {'error': 'forbidden'})
            with LOCK:
                target = str(load().get('settings', {}).get('epStudio') or '').strip().strip('"')
            if not target or target.lower().startswith(('http://', 'https://')) or not os.path.exists(target):
                return self._send(200, {'ok': False, 'error': "I can't find that EP Studio path - check it in Settings."})
            try:
                if hasattr(os, 'startfile'):
                    os.startfile(target)
                else:
                    subprocess.Popen(['xdg-open', target])
                return self._send(200, {'ok': True})
            except Exception as e:
                return self._send(200, {'ok': False, 'error': str(e)[:120]})
        if self.path.split('?')[0] == '/api/quit':
            self._send(200, {'ok': True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        self._send(404, {'error': 'not found'})


def main():
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    except OSError:
        # already running in the background -> just show the window
        open_window()
        return
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=update_loop, daemon=True).start()
    if '--no-window' not in sys.argv:
        threading.Timer(0.8, open_window).start()
    srv.serve_forever()


if __name__ == '__main__':
    main()
