"""Exercise visible buttons with real mouse clicks while the game is stationary."""
import ctypes
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
u = ctypes.windll.user32
u.SetProcessDPIAware()
u.GetForegroundWindow.restype = ctypes.c_void_p
u.FindWindowW.restype = ctypes.c_void_p
u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
game = u.FindWindowW(None,'Grand Theft Auto V')

def status():
    for _ in range(5):
        try:
            return json.loads((root/'reports/bridge-status.json').read_text())
        except ValueError:
            time.sleep(.03)
    raise RuntimeError('No readable live bridge status')

initial = status()
if initial['speed_mps'] > .2 or initial['armed']:
    raise SystemExit('Park and turn off cruise before GUI verification.')
u.SetForegroundWindow(game)
layout = json.loads((root/'reports/control-panel-layout.json').read_text())
rows=[]
sequence = [('F10',False),('[',False),('[',False),(']',False),(']',False),
            ('+',False),('-',False),('F7',False),('F10',False),
            ('F5',False),('F5',False),('F4',False),('F4',False),('F4',False),
            ('F1',False),('F1',False),('F2',False),('F2',False),('F3',False),('F3',False),
            ('F11',False),('F11',False),('INSERT',False),('INSERT',False),('INSERT',False)]
for key,shift in sequence:
    current=status()
    if current['speed_mps'] > .2 or current['openpilot_active']:
        raise SystemExit('Driving resumed; stopped GUI test.')
    item=next(x for x in layout if x['key']==key and x['shift']==shift)
    u.SetCursorPos(item['x'],item['y'])
    u.mouse_event(0x2,0,0,0,0)
    time.sleep(.04)
    u.mouse_event(0x4,0,0,0,0)
    time.sleep(1.4)
    rows.append({'button':item['label'],'gta_kept_focus':u.GetForegroundWindow()==game,'state':status()})
    (root/'reports/control-panel-test.json').write_text(json.dumps(rows,indent=2))
print('Completed visible mouse-button test:',len(rows),'clicks')
