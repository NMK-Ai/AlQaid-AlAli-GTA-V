#!/usr/bin/env python3
"""controller_to_keys.py — Xbox controller -> FrogPilot-GTA hotkeys.

Reads XInput buttons from the physical Xbox controller and synthesizes the
keyboard hotkeys that native/bridge.cpp polls via GetAsyncKeyState:

  Mapping (default):
    START      -> F12  spawn stock Krieger (OPENPILT)
    BACK       -> F6   toggle openpilot camera
    LB         -> F7   steering master (Always On Lateral)
    RB         -> F8   SET / arm cruise (engage)
    B          -> F9   cancel cruise
    Y          -> F10  ALL OFF (release both axes)
    DPad Up    -> '+'  cruise +1 mph (+5 with RIGHT THUMB CLICK held)
    DPad Down  -> '-'  cruise -1 mph

  Native passthrough (handled inside bridge.cpp, not here):
    Left stick = steering, RT = gas, LT = brake, A = handbrake.

Notes:
  - Injected keys are system-wide: bridge.cpp reads them with
    GetAsyncKeyState even when GTA is not the focused window.
  - Only injects on button edge (press), no key repeat except DPad which
    repeats every 200 ms like bridge.cpp expects.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

xinput = ctypes.windll.XInput1_4  # verified working on this machine (index 0)

ERROR_SUCCESS = 0
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_Y = 0x8000
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080

# Virtual keys -> scan codes for SendInput
VK_MAP = {
    'F6': 0x40, 'F7': 0x41, 'F8': 0x42, 'F9': 0x43, 'F10': 0x44, 'F12': 0x58,
    'ADD': 0x4E, 'SUBTRACT': 0x4E + 1 - 1,  # replaced below
}
VK_MAP['SUBTRACT'] = 0x4F  # numpad minus
VK_MAP['OEM_PLUS'] = 0x0D

# Button -> action
BUTTON_MAP = {
    XINPUT_GAMEPAD_START: ('F12', 'spawn Krieger'),
    XINPUT_GAMEPAD_BACK: ('F6', 'camera toggle'),
    XINPUT_GAMEPAD_LEFT_SHOULDER: ('F7', 'steering master'),
    XINPUT_GAMEPAD_RIGHT_SHOULDER: ('F8', 'SET/engage'),
    XINPUT_GAMEPAD_B: ('F9', 'cancel'),
    XINPUT_GAMEPAD_Y: ('F10', 'ALL OFF'),
}
DPAD_UP = ('ADD', 'cruise +1')
DPAD_DOWN = ('SUBTRACT', 'cruise -1')

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
SHIFT_VK = 0x10
SHIFT_SCAN = 0x2A


class XINPUT_STATE(ctypes.Structure):
    class _Gamepad(ctypes.Structure):
        _fields_ = [('wButtons', ctypes.c_ushort), ('bLeftTrigger', ctypes.c_ubyte),
                    ('bRightTrigger', ctypes.c_ubyte), ('sThumbLX', ctypes.c_short),
                    ('sThumbLY', ctypes.c_short), ('sThumbRX', ctypes.c_short),
                    ('sThumbRY', ctypes.c_short)]
    _fields_ = [('dwPacketNumber', ctypes.c_ulong), ('Gamepad', _Gamepad)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wt.DWORD), ('u', _U)]


def tap(vk_name, hold_shift=False, hold_ms=30):
    scan = VK_MAP[vk_name]
    windll = ctypes.windll.user32
    if hold_shift:
        down_shift = INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(SHIFT_VK, SHIFT_SCAN, KEYEVENTF_SCANCODE))
        windll.SendInput(1, ctypes.byref(down_shift), ctypes.sizeof(INPUT))
    down = INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE))
    windll.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(hold_ms / 1000.0)
    up = INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP))
    windll.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    if hold_shift:
        up_shift = INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(SHIFT_VK, SHIFT_SCAN, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP))
        windll.SendInput(1, ctypes.byref(up_shift), ctypes.sizeof(INPUT))


def find_pad():
    st = XINPUT_STATE()
    for i in range(4):
        if xinput.XInputGetState(i, ctypes.byref(st)) == ERROR_SUCCESS:
            # skip pure axes pads (ViGEm) by requiring at least one button ever seen later
            return i
    return None


def main():
    pad = find_pad()
    if pad is None:
        print('ERROR: no XInput controller found'); sys.exit(1)
    print(f'controller_to_keys: using XInput index {pad}')
    print('Mapping: START=F12 spawn | BACK=F6 camera | LB=F7 master | RB=F8 SET | B=F9 cancel | Y=F10 all-off | DPad=+/- speed | R3 hold = +5 steps')
    st = XINPUT_STATE()
    prev_buttons = 0
    last_dpad = 0.0
    try:
        while True:
            if xinput.XInputGetState(pad, ctypes.byref(st)) != ERROR_SUCCESS:
                print('controller disconnected, waiting...')
                time.sleep(1.0); pad = None
                while pad is None:
                    pad = find_pad(); time.sleep(0.5)
                continue
            b = st.Gamepad.wButtons
            edge = b & ~prev_buttons
            for btn, (vk, label) in BUTTON_MAP.items():
                if edge & btn:
                    tap(vk)
                    print(f'{label} -> {vk}')
            now = time.monotonic()
            dpad = b & (XINPUT_GAMEPAD_DPAD_UP | XINPUT_GAMEPAD_DPAD_DOWN)
            if dpad and now - last_dpad >= 0.2:
                big = bool(b & XINPUT_GAMEPAD_RIGHT_THUMB)
                if dpad & XINPUT_GAMEPAD_DPAD_UP:
                    tap('ADD', hold_shift=big); print('cruise +' + ('5' if big else '1'))
                else:
                    tap('SUBTRACT', hold_shift=big); print('cruise -' + ('5' if big else '1'))
                last_dpad = now
            prev_buttons = b
            time.sleep(0.02)
    except KeyboardInterrupt:
        print('bye')


if __name__ == '__main__':
    main()
