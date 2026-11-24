"""Lock In connector for Claude (MCP server, stdlib only).

Lets Claude read your Lock In plan and add / change things in it.
It only talks to the Lock In app running on THIS computer (127.0.0.1) - nothing goes to the internet.
Reads come straight from the app; writes are queued and applied by the Lock In window itself,
so Claude can never overwrite something you are typing.
Set up once with connect_claude.bat, then restart the Claude desktop app.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, date

BASE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get('LOCKIN_URL', 'http://127.0.0.1:47615')


def data_dir():
    d = os.environ.get('LOCKIN_DATA')
    if d:
        return d
    if os.name == 'nt' and os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'LockIn')
    return os.path.join(BASE, 'data')


def token():
    with open(os.path.join(data_dir(), 'agent.token'), 'r', encoding='utf-8') as f:
        return f.read().strip()


class NotRunning(Exception):
    pass


def call(path, body=None, timeout=8):
    try:
        h = {'X-LockIn-Token': token()}
    except Exception:
        raise NotRunning("Lock In hasn't created its connector key yet - open the Lock In app once (version 2.1 or newer) and try again.")
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(URL + path, data=data, headers=h, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise NotRunning('Lock In rejected the connector key. Reinstall Lock In v2.1+ (install_autostart.bat) and try again.')
        raise NotRunning('Lock In returned an error (%s).' % e.code)
    except Exception:
        raise NotRunning("Lock In isn't running. Open the Lock In app (Desktop shortcut) and try again.")


# ------------------------------------------------------------------ schedule maths (mirrors the app)

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


def on_day(st, d):
    """All events on date d, recurring ones expanded, as plain dicts."""
    ds = d.strftime('%Y-%m-%d')
    out = []
    for it in st.get('items', []):
        if it.get('repeat'):
            if not recurs(it, d):
                continue
            ov = (it.get('overrides') or {}).get(ds) or {}
            e = dict(it)
            e.update(date=ds, done=ds in (it.get('doneDates') or []), tentative=False, repeating=True)
            if ov:
                e['time'], e['endTime'] = ov.get('time'), ov.get('endTime')
            out.append(e)
        elif it.get('date') == ds:
            e = dict(it)
            e['repeating'] = False
            out.append(e)
    out.sort(key=lambda e: (e.get('time') or '99:99'))
    return out


def brief(e):
    r = {'id': e.get('id'), 'title': e.get('title'), 'area': e.get('area')}
    if e.get('date'):
        r['date'] = e['date']
    if e.get('time'):
        r['time'] = e['time']
    if e.get('endTime'):
        r['end_time'] = e['endTime']
    if e.get('emoji'):
        r['emoji'] = e['emoji']
    if e.get('done'):
        r['done'] = True
    if e.get('tentative'):
        r['pencilled_in'] = True
    if e.get('repeating') or e.get('repeat'):
        r['repeats'] = True
    if e.get('notes'):
        r['notes'] = e['notes'][:200]
    if e.get('company'):
        r['company'] = e['company']
    if e.get('stage'):
        r['stage'] = e['stage']
    return r


def mins(t):
    h, m = t.split(':')
    return int(h) * 60 + int(m)


def hhmm(m):
    return '%02d:%02d' % (m // 60, m % 60)


def parse_date(s, default=None):
    if not s:
        return default
    s = s.strip().lower()
    today = date.today()
    if s == 'today':
        return today
    if s in ('tomorrow', 'tmr'):
        return today + timedelta(days=1)
    return datetime.strptime(s, '%Y-%m-%d').date()


# ------------------------------------------------------------------ tools

def state():
    return call('/api/agent/state')


def run_cmd(cmd):
    q = call('/api/agent/cmd', cmd)['qid']
    end = time.time() + 12
    while time.time() < end:
        time.sleep(0.5)
        r = call('/api/agent/result?qid=' + q)
        if r.get('done'):
            res = r['result'] or {}
            if not res.get('ok'):
                raise ValueError(res.get('msg') or 'Lock In could not do that.')
            return res
    return {'ok': True, 'msg': 'Queued. Lock In will apply it as soon as its window is open and responding.'}


def t_get_schedule(a):
    st = state()
    start = parse_date(a.get('start_date'), date.today())
    days = max(1, min(31, int(a.get('days') or 7)))
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        ev = [brief(e) for e in on_day(st, d)]
        out.append({'date': d.isoformat(), 'weekday': d.strftime('%A'), 'events': ev})
    return {'today': date.today().isoformat(), 'days': out}


def t_list_inbox(a):
    st = state()
    items = st.get('items', [])
    inbox = [brief(i) for i in items if not i.get('date') and not i.get('done') and not i.get('repeat')]
    pencilled = [brief(i) for i in items if i.get('tentative') and i.get('date') and not i.get('done')]
    jobs = [brief(i) for i in items if i.get('area') == 'jobs' and not i.get('done')]
    content = [brief(i) for i in items if i.get('area') == 'content' and not i.get('done')]
    return {'inbox_undated': inbox, 'pencilled_in': pencilled, 'job_hunt_open': jobs, 'content_open': content,
            'top3_today': (st.get('top3') or {}).get('ids', [])}


def t_find_free_slots(a):
    st = state()
    d = parse_date(a.get('date'), date.today())
    lo = mins(a.get('earliest') or '08:00')
    hi = mins(a.get('latest') or '22:00')
    need = int(a.get('min_minutes') or 60)
    busy = []
    for e in on_day(st, d):
        if e.get('time') and not e.get('done') and not e.get('tentative'):
            s = mins(e['time'])
            en = mins(e['endTime']) if e.get('endTime') else s + 60
            busy.append((s, max(en, s + 15)))
    busy.sort()
    free, cur = [], lo
    for s, en in busy:
        if s - cur >= need:
            free.append((cur, min(s, hi)))
        cur = max(cur, en)
    if hi - cur >= need:
        free.append((cur, hi))
    free = [(x, y) for x, y in free if y - x >= need and x < hi]
    return {'date': d.isoformat(), 'weekday': d.strftime('%A'),
            'free_slots': [{'from': hhmm(x), 'to': hhmm(y), 'minutes': y - x} for x, y in free],
            'busy': [{'from': hhmm(s), 'to': hhmm(e)} for s, e in busy]}


def fields_from(a):
    f = {}
    m = {'title': 'title', 'date': 'date', 'time': 'time', 'end_time': 'endTime', 'area': 'area', 'notes': 'notes',
         'emoji': 'emoji', 'color': 'color', 'link': 'link', 'company': 'company', 'until': 'until'}
    for k, v in m.items():
        if k in a:
            f[v] = a[k]
    if 'pencilled_in' in a:
        f['tentative'] = bool(a['pencilled_in'])
    if 'remind_minutes_before' in a:
        f['remind'] = a['remind_minutes_before']
    if 'repeat_weekdays' in a:
        days = a['repeat_weekdays']
        f['repeat'] = {'days': days, 'interval': int(a.get('repeat_every_weeks') or 1)} if days else None
    elif 'repeat_every_weeks' in a:
        pass
    return f


def t_add_item(a):
    f = fields_from(a)
    if not f.get('title'):
        raise ValueError('title is required')
    if f.get('repeat') and not f.get('date'):
        f['date'] = date.today().isoformat()
    return run_cmd({'op': 'add', 'fields': f})


def t_quick_add(a):
    return run_cmd({'op': 'quick', 'text': a.get('text', '')})


def t_update_item(a):
    f = fields_from(a)
    return run_cmd({'op': 'update', 'id': a['id'], 'fields': f})


def t_complete_item(a):
    return run_cmd({'op': 'complete', 'id': a['id'], 'date': a.get('date'), 'done': a.get('done', True)})


def t_delete_item(a):
    return run_cmd({'op': 'delete', 'id': a['id'], 'scope': a.get('scope', 'all'), 'date': a.get('date')})


DATE_P = {'type': 'string', 'description': 'YYYY-MM-DD'}
TIME_P = {'type': 'string', 'description': '24-hour HH:MM, e.g. 16:15'}
FIELD_PROPS = {
    'title': {'type': 'string'},
    'date': {'type': 'string', 'description': 'YYYY-MM-DD. Leave out to put it in the Inbox (undated).'},
    'time': TIME_P, 'end_time': TIME_P,
    'area': {'type': 'string', 'enum': ['content', 'jobs', 'life']},
    'notes': {'type': 'string'},
    'pencilled_in': {'type': 'boolean', 'description': 'A plan the user has not confirmed yet (needs a date).'},
    'remind_minutes_before': {'type': 'integer'},
    'emoji': {'type': 'string'},
    'color': {'type': 'string', 'description': 'hex colour like #4ade80'},
    'repeat_weekdays': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0, 'maximum': 6},
                        'description': 'Weekly repeat on these days, 0=Sunday ... 6=Saturday. Needs date as the first occurrence.'},
    'repeat_every_weeks': {'type': 'integer', 'description': '1 = every week, 2 = every other week'},
    'until': {'type': 'string', 'description': 'Last date a repeating item runs, YYYY-MM-DD'},
}

TOOLS = [
    ('lockin_get_schedule', 'Read the user\'s Lock In plan: every event per day (recurring events already expanded), with ids. Use before suggesting or changing anything.',
     {'start_date': {'type': 'string', 'description': "YYYY-MM-DD, 'today' or 'tomorrow'. Default today."},
      'days': {'type': 'integer', 'description': 'How many days, 1-31. Default 7.'}}, [], t_get_schedule),
    ('lockin_list_inbox', 'List undated Inbox items, pencilled-in (unconfirmed) plans, open job-hunt items and open content items.', {}, [], t_list_inbox),
    ('lockin_find_free_slots', 'Find free time on one day between existing timed events (pencilled-in plans do not block time).',
     {'date': {'type': 'string', 'description': "YYYY-MM-DD, 'today' or 'tomorrow'"}, 'earliest': TIME_P, 'latest': TIME_P,
      'min_minutes': {'type': 'integer', 'description': 'Minimum slot length. Default 60.'}}, ['date'], t_find_free_slots),
    ('lockin_add_item', 'Add one item to Lock In (event, task or inbox note). Ask the user before adding when they have not clearly asked for it.',
     FIELD_PROPS, ['title'], t_add_item),
    ('lockin_quick_add', 'Add something using the same natural-language parser as the Lock In drop box, e.g. "every tue gym 4.15pm to 5.15pm", "call bank tmr 3pm #life", "plan reel fri?" (trailing ? = pencilled in).',
     {'text': {'type': 'string'}}, ['text'], t_quick_add),
    ('lockin_update_item', 'Change fields of an existing item by id (move it, retitle, set emoji, pencil it in, etc.). Only the fields you pass change.',
     dict(FIELD_PROPS, id={'type': 'string'}), ['id'], t_update_item),
    ('lockin_complete_item', 'Mark an item done (or not done with done=false). For repeating items pass the occurrence date.',
     {'id': {'type': 'string'}, 'date': DATE_P, 'done': {'type': 'boolean'}}, ['id'], t_complete_item),
    ('lockin_delete_item', 'Delete an item. For repeating items choose scope: occurrence (just that date), future (that date onwards) or all. Confirm with the user first.',
     {'id': {'type': 'string'}, 'scope': {'type': 'string', 'enum': ['all', 'occurrence', 'future']}, 'date': DATE_P}, ['id'], t_delete_item),
]
TOOL_FN = {t[0]: t[4] for t in TOOLS}


def tool_list():
    return [{'name': n, 'description': d, 'inputSchema': {'type': 'object', 'properties': p, 'required': r}}
            for n, d, p, r, _ in TOOLS]


# ------------------------------------------------------------------ MCP over stdio (newline-delimited JSON-RPC)

def send(msg):
    sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
    sys.stdout.buffer.flush()


def handle(m):
    mid, method = m.get('id'), m.get('method')
    if method == 'initialize':
        pv = (m.get('params') or {}).get('protocolVersion') or '2025-06-18'
        return send({'jsonrpc': '2.0', 'id': mid, 'result': {
            'protocolVersion': pv, 'capabilities': {'tools': {}},
            'serverInfo': {'name': 'lockin', 'version': '1.0'},
            'instructions': "Lock In is the user's personal calendar/planner running on their laptop. Read before you suggest. "
                            "Times are 24-hour. Plans the user hasn't confirmed are 'pencilled in'. Don't add or delete things unasked."}})
    if method == 'ping':
        return send({'jsonrpc': '2.0', 'id': mid, 'result': {}})
    if method == 'tools/list':
        return send({'jsonrpc': '2.0', 'id': mid, 'result': {'tools': tool_list()}})
    if method == 'tools/call':
        p = m.get('params') or {}
        fn = TOOL_FN.get(p.get('name'))
        if not fn:
            return send({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32602, 'message': 'Unknown tool'}})
        try:
            res = fn(p.get('arguments') or {})
            return send({'jsonrpc': '2.0', 'id': mid, 'result': {
                'content': [{'type': 'text', 'text': json.dumps(res, ensure_ascii=False, indent=1)}]}})
        except Exception as e:
            return send({'jsonrpc': '2.0', 'id': mid, 'result': {
                'content': [{'type': 'text', 'text': str(e)}], 'isError': True}})
    if mid is not None:
        send({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'Method not found'}})


def main():
    for line in sys.stdin.buffer:
        line = line.decode('utf-8', 'replace').strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except Exception as e:
            sys.stderr.write('lockin mcp error: %s\n' % e)


if __name__ == '__main__':
    main()
