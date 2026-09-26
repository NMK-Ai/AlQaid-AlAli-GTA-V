"""Send bounded menu input only after verifying GTA is the foreground window."""
import argparse
import ctypes
import time

parser = argparse.ArgumentParser()
mapping = {'ESC': 0x1b, 'ENTER': 0x0d, 'LEFT': 0x25, 'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28,
           'B': 0x42, 'L': 0x4c, 'F': 0x46, 'E': 0x45, 'A': 0x41, 'D': 0x44, 'W': 0x57, 'S': 0x53,
           '[': 0xdb, ']': 0xdd, '+': 0xbb, '-': 0xbd,
           **{f'F{i}': 0x6f+i for i in range(1, 13)}}
parser.add_argument('keys', nargs='+', choices=list(mapping))
parser.add_argument('--hold', type=float, default=.15)
parser.add_argument('--gap', type=float, default=1.)
parser.add_argument('--shift', action='store_true')
args = parser.parse_args()
if not .05 <= args.hold <= 3.5 or not .1 <= args.gap <= 10:
    raise SystemExit('Input duration exceeds the bounded test range')
u = ctypes.windll.user32
u.FindWindowW.restype = ctypes.c_void_p
u.GetForegroundWindow.restype = ctypes.c_void_p
u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u.BringWindowToTop.argtypes = [ctypes.c_void_p]
hwnd = u.FindWindowW(None, 'Grand Theft Auto V')
if not hwnd:
    raise SystemExit('GTA window not found')
thread = ctypes.windll.kernel32.GetCurrentThreadId()
foreground_thread = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
attached = u.AttachThreadInput(thread, foreground_thread, True) if thread != foreground_thread else False
try:
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)
finally:
    if attached:
        u.AttachThreadInput(thread, foreground_thread, False)
time.sleep(.3)
if u.GetForegroundWindow() != hwnd:
    # A background helper can be denied foreground activation until it produces
    # input. A bounded Alt tap satisfies Windows' foreground-lock rule; still
    # verify the target before sending any requested game control.
    u.keybd_event(0x12, u.MapVirtualKeyW(0x12, 0), 0, 0)
    u.keybd_event(0x12, u.MapVirtualKeyW(0x12, 0), 2, 0)
    u.SetForegroundWindow(hwnd)
    time.sleep(.2)
for key in args.keys:
    if u.GetForegroundWindow() != hwnd:
        raise SystemExit('GTA is not in the foreground; no input sent')
    scan = u.MapVirtualKeyW(mapping[key], 0)
    flags = 0x1 if key in ['LEFT', 'RIGHT', 'UP', 'DOWN'] else 0
    try:
        if args.shift:
            u.keybd_event(0x10, u.MapVirtualKeyW(0x10, 0), 0, 0)
        u.keybd_event(mapping[key], scan, flags, 0)
        time.sleep(args.hold)
    finally:
        u.keybd_event(mapping[key], scan, flags | 0x2, 0)
        if args.shift:
            u.keybd_event(0x10, u.MapVirtualKeyW(0x10, 0), 0x2, 0)
    time.sleep(args.gap)
print('Sent GTA keys:', ' '.join(args.keys))
