"""Connects Lock In to the Claude desktop app (so Claude can read and add to your plan).
Run via connect_claude.bat (the installer also does this for you). Then fully quit and reopen Claude.
Safe to run again: it only adds/updates the "lockin" entry and keeps a backup of your Claude config.
"""
import os, sys, json, glob, shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def config_paths():
    paths = []
    appdata = os.environ.get('APPDATA')
    local = os.environ.get('LOCALAPPDATA')
    if appdata:
        paths.append(os.path.join(appdata, 'Claude', 'claude_desktop_config.json'))
    if local:  # Microsoft Store install keeps its files in a package folder
        paths += glob.glob(os.path.join(local, 'Packages', 'Claude_*', 'LocalCache', 'Roaming', 'Claude', 'claude_desktop_config.json'))
        for pk in glob.glob(os.path.join(local, 'Packages', 'Claude_*', 'LocalCache', 'Roaming', 'Claude')):
            c = os.path.join(pk, 'claude_desktop_config.json')
            if c not in paths:
                paths.append(c)
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def python_exe():
    exe = sys.executable
    if exe.lower().endswith('pythonw.exe'):
        cand = exe[:-11] + 'python.exe'
        if os.path.exists(cand):
            exe = cand
    return exe


def connect(app_dir=None):
    local = os.environ.get('LOCALAPPDATA')
    installed = os.path.join(local, 'LockIn', 'app') if local else None
    if not app_dir:
        app_dir = installed if installed and os.path.exists(os.path.join(installed, 'mcp_lockin.py')) else HERE
    script = os.path.join(app_dir, 'mcp_lockin.py')
    entry = {'command': python_exe(), 'args': [script]}
    done, problems = [], []
    paths = config_paths()
    # use an existing config if there is one; otherwise create the standard one
    existing = [p for p in paths if os.path.exists(p)]
    targets = existing or paths[:1]
    for cfg in targets:
        try:
            data = {}
            if os.path.exists(cfg):
                with open(cfg, 'r', encoding='utf-8-sig') as f:
                    raw = f.read().strip()
                data = json.loads(raw) if raw else {}
                if not isinstance(data, dict):
                    raise ValueError('config is not a JSON object')
                shutil.copyfile(cfg, cfg + '.lockin-backup')
            data.setdefault('mcpServers', {})['lockin'] = entry
            os.makedirs(os.path.dirname(cfg), exist_ok=True)
            with open(cfg, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            done.append(cfg)
        except Exception as e:
            problems.append((cfg, str(e)))
    return entry, done, problems


if __name__ == '__main__':
    entry, done, problems = connect()
    if done:
        print('Lock In connector added to Claude here:')
        for d in done:
            print('  ' + d)
        print('\nNow FULLY QUIT the Claude app (right-click its tray icon > Quit) and open it again.')
        print('Then ask Claude things like: "what is on my Lock In this week?" or "find me a free hour Saturday".')
    for cfg, err in problems:
        print('\nCould not edit %s (%s).' % (cfg, err))
    if problems or not done:
        print('\nManual setup: add this inside "mcpServers" in claude_desktop_config.json:')
        print(json.dumps({'lockin': entry}, indent=2))
