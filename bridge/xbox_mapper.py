# -*- coding: utf-8 -*-
"""NMK AI — Xbox controller button mapper for the driving bridge.

Polls XInput gamepads and translates buttons into the same keyboard
commands the NMK AI control panel uses. Runs in the background; game
window receives the keys exactly like manual panel presses.

Default mapping (editable below):
  D-PAD UP    -> + speed        (VK +)
  D-PAD DOWN  -> - speed        (VK -)
  A           -> SET/activate autopilot (F8)
  B           -> Steering master toggle   (F7)
  X           -> Cancel cruise  (F9)
  Y           -> Camera toggle  (F6)
  START       -> ALL OFF        (F10)
"""
import ctypes
import logging
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(filename=ROOT/'reports/xbox-mapper.log', level=logging.INFO)
u, k = ctypes.windll.user32, ctypes.windll.kernel32
u.SetProcessDPIAware()

XINPUT_GAMEPAD = ctypes.Structure
class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_ulong),
                ('wButtons', ctypes.c_ushort),
                ('bLeftTrigger', ctypes.c_ubyte),
                ('bRightTrigger', ctypes.c_ubyte),
                ('sThumbLX', ctypes.c_short),
                ('sThumbLY', ctypes.c_short),
                ('sThumbRX', ctypes.c_short),
                ('sThumbRY', ctypes.c_short)]

try:
    xinput = ctypes.windll.xinput1_4
except OSError:
    xinput = ctypes.windll.xinput9_1_0
XInputGetState = xinput.XInputGetState
XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_STATE)]

BTN = {'UP': 0x0001, 'DOWN': 0x0002, 'LEFT': 0x0004, 'RIGHT': 0x0008,
       'START': 0x0010, 'BACK': 0x0020, 'L3': 0x0040, 'R3': 0x0080,
       'LB': 0x0100, 'RB': 0x0200, 'A': 0x1000, 'B': 0x2000,
       'X': 0x4000, 'Y': 0x8000}

# name -> (virtual key, hold seconds)
MAPPING = {
    'UP':    (0xBB, 0.16),   # speed +
    'DOWN':  (0xBD, 0.16),   # speed -
    'A':     (0x77, 0.16),   # F8 SET / activate
    'B':     (0x76, 0.16),   # F7 steering master
    'X':     (0x78, 0.16),   # F9 cancel cruise
    'Y':     (0x75, 0.16),   # F6 camera
    'START': (0x79, 0.16),   # F10 all off
}

def find_gta():
    return u.FindWindowW(None, 'Grand Theft Auto V')

def send_key(vk, hold):
    hwnd = find_gta()
    if not hwnd:
        return False
    cur = k.GetCurrentThreadId()
    fg = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
    at = cur != fg and u.AttachThreadInput(cur, fg, True)
    try:
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    finally:
        if at:
            u.AttachThreadInput(cur, fg, False)
    time.sleep(0.04)
    scan = u.MapVirtualKeyW(vk, 0)
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(hold)
    u.keybd_event(vk, scan, 2, 0)
    return True

def main():
    logging.info('xbox mapper started')
    state = XINPUT_STATE()
    prev = 0
    while True:
        for pad in range(0, 4):
            res = XInputGetState(pad, ctypes.byref(state))
            if res != 0:
                continue
            now = state.wButtons
            changed = now & ~prev
            for name, (vk, hold) in MAPPING.items():
                if changed & BTN[name]:
                    if send_key(vk, hold):
                        logging.info('pad %d %s -> VK 0x%02X', pad, name, vk)
            prev = now
            break
        time.sleep(0.03)

if __name__ == '__main__':
    main()
