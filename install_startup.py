"""Installs Lock In properly:
 - copies the app to %LOCALAPPDATA%\\LockIn\\app  (so you can delete the folder you unzipped)
 - keeps your data in %APPDATA%\\LockIn  (never touched by installs/updates/deletes)
 - opens Lock In at login, and puts a "Lock In" shortcut on your Desktop
Run:  python install_startup.py            (install or update)
      python install_startup.py --remove   (stop opening at login; data is kept)
"""
import os, sys, shutil, subprocess, time, urllib.request

src = os.path.dirname(os.path.abspath(__file__))
local = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
dst = os.path.join(local, 'LockIn', 'app')
appdata = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'LockIn')
startup = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
vbs = os.path.join(startup, 'LockIn.vbs')


def stop_running():
    try:
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:47615/api/quit', method='POST'), timeout=3)
    except Exception:
        pass
    time.sleep(2)


if '--remove' in sys.argv:
    stop_running()
    if os.path.exists(vbs):
        os.remove(vbs)
    print('Removed. Lock In will no longer open at login. Your data is kept in: ' + appdata)
    sys.exit()

stop_running()
os.makedirs(appdata, exist_ok=True)
# bring an existing data folder across (only if there is no data yet)
old = os.path.join(src, 'data', 'store.json')
new = os.path.join(appdata, 'store.json')
if os.path.exists(old) and not os.path.exists(new):
    shutil.copy2(old, new)
    print('Imported your existing events.')
if os.path.abspath(src) != os.path.abspath(dst):
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('data', '__pycache__', '*.zip', '*.tmp'))
pyw = sys.executable
if pyw.lower().endswith('python.exe'):
    cand = pyw[:-10] + 'pythonw.exe'
    if os.path.exists(cand):
        pyw = cand
app = os.path.join(dst, 'app.py')
os.makedirs(startup, exist_ok=True)
with open(vbs, 'w') as f:
    f.write('CreateObject("Wscript.Shell").Run """%s"" ""%s""", 0, False\r\n' % (pyw, app))
ps = ("$d=[Environment]::GetFolderPath('Desktop');$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\\Lock In.lnk');"
      "$s.TargetPath='%s';$s.Arguments='\"%s\"';$s.WorkingDirectory='%s';$s.Save()" % (pyw, app, dst))
try:
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=False, timeout=30)
except Exception:
    pass
print('Installed to: ' + dst)
print('Your data lives in: ' + appdata + '  (safe to reinstall / delete the unzipped folder)')
print('Starting Lock In...')
subprocess.Popen([pyw, app], cwd=dst)
