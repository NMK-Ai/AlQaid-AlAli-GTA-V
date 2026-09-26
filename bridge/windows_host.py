"""GTA window capture and loopback-only native command relay."""
import ctypes
import argparse
from ctypes import wintypes
import json
import socket
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from windows_capture import WindowsCapture, Frame, InternalCaptureControl
from protocol import WIDTH, HEIGHT, NV12_SIZE, VERSION, COMMAND, decode_telemetry, receive_json, send_json
from gta_diagnostics import DisengagementTrace
from gta_radar import MAGIC as RADAR_MAGIC, decode_radar

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
args = parser.parse_args()
cv2.setNumThreads(2)
# Keep camera conversion responsive when game/streaming encoders contend for CPU.
# AboveNormal is bounded Windows scheduling priority, not realtime priority.
kernel = ctypes.windll.kernel32
kernel.GetCurrentProcess.restype = ctypes.c_void_p
kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x8000):
    print('Could not set capture priority; continuing at normal priority', flush=True)
token = (ROOT / 'runtime/bridge-token').read_text().strip()
u = ctypes.windll.user32
u.SetProcessDPIAware()
u.FindWindowW.restype = ctypes.c_void_p
u.GetForegroundWindow.restype = ctypes.c_void_p
u.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
u.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.POINT)]
ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
hwnd = u.FindWindowW(None, 'Grand Theft Auto V')
if not hwnd:
    raise SystemExit('GTA window not found')
telemetry = None
radar = None
last_telemetry = 0.
latest = None
serial = 0
capture_callbacks = 0
conversion_ms = send_ms = 0.
next_conversion = 0.
stop = threading.Event()
disengagement_trace = DisengagementTrace()
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('127.0.0.1', 8766))
udp.settimeout(.2)

def read_telemetry():
    global telemetry, last_telemetry, radar
    while not stop.is_set():
        try:
            data, peer = udp.recvfrom(8192)
            if peer != ('127.0.0.1', 8767):
                continue
            if data[:4] == RADAR_MAGIC.to_bytes(4, 'little'):
                radar = decode_radar(data)
                continue
            telemetry = decode_telemetry(data)
            last_telemetry = time.monotonic()
            keys = [name for key,name in ((0x79,'ALL OFF'), (0x20,'handbrake'), (0x76,'master'), (0x78,'Cancel'))
                    if u.GetForegroundWindow() == hwnd and u.GetAsyncKeyState(key) & 0x8000]
            diagnostic = disengagement_trace.telemetry(telemetry, keys)
            if diagnostic:
                (ROOT/'reports/native-disengagement.json').write_text(json.dumps(diagnostic,indent=2))
                with (ROOT/'reports/native-disengagements.jsonl').open('a') as output:
                    output.write(json.dumps(diagnostic)+'\n')
        except socket.timeout:
            pass
        except (ValueError, OSError) as e:
            print(f'Telemetry: {e}', flush=True)

def nv12(bgra):
    i420 = cv2.cvtColor(bgra, cv2.COLOR_BGRA2YUV_I420).reshape(-1)
    area = WIDTH * HEIGHT
    result = np.empty(NV12_SIZE, np.uint8)
    result[:area] = i420[:area]
    result[area::2] = i420[area:area * 5 // 4]
    result[area+1::2] = i420[area * 5 // 4:]
    return result.tobytes()

# Digital narrow camera has exactly the same principal point and focal length
# as FrogPilot's road camera. Its effective detail is limited by the wide image.
ratio = 567.0 / 2648.0
affine = np.array([[ratio, 0, WIDTH / 2 * (1-ratio)],
                   [0, ratio, HEIGHT / 2 * (1-ratio)]], np.float32)
# WGC's interval is quantized to display refreshes; 50 ms yielded only 15 Hz.
# Capture faster than the 20 Hz transport so its latest-frame queue stays fresh.
# Toggling the capture border (draw_border) requires the Windows 11 Graphics
# Capture API; on Windows 10 pass None so the unsupported toggle is skipped.
import sys
_win11 = sys.getwindowsversion().build >= 22000
capture = WindowsCapture(cursor_capture=False, draw_border=False if _win11 else None, minimum_update_interval=25 if _win11 else None, window_hwnd=hwnd)

@capture.event
def on_frame_arrived(frame: Frame, control: InternalCaptureControl):
    global latest, serial, conversion_ms, next_conversion, capture_callbacks
    conversion_start = time.monotonic()
    if stop.is_set():
        control.stop()
        return
    t = telemetry
    if t is None or time.monotonic() - last_telemetry > .2 or not t['flags'] & 4:
        return
    capture_callbacks += 1
    # Convert only the ~20 Hz stream perception consumes. Previously every
    # ~30 Hz WGC frame was converted twice, then many were thrown away by a
    # second timer in the sender. That wasted CPU and added another frame wait.
    if conversion_start < next_conversion:
        return
    next_conversion = conversion_start+.05 if conversion_start-next_conversion > .05 else next_conversion+.05
    rect, origin, outer = wintypes.RECT(), wintypes.POINT(0, 0), wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rect))
    u.ClientToScreen(hwnd, ctypes.byref(origin))
    status = ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 9, ctypes.byref(outer), ctypes.sizeof(outer))
    if status or rect.right < 320 or rect.bottom < 200:
        raise RuntimeError(f'GTA client unreadable; found {rect.right}x{rect.bottom}')
    ch, cw = rect.bottom, rect.right
    x, y = origin.x - outer.left, origin.y - outer.top
    bgra = frame.frame_buffer[y:y+ch, x:x+cw, :]
    # Accept any windowed client size; scale proportionally to the calibrated
    # transport size. The affine narrow-camera transform is center-relative,
    # so it stays valid after uniform scaling.
    if bgra.shape[0] != HEIGHT or bgra.shape[1] != WIDTH:
        bgra = cv2.resize(bgra, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
    if bgra.shape != (HEIGHT, WIDTH, 4):
        raise RuntimeError('Capture/client geometry mismatch')
    captured = ctypes.windll.kernel32.GetTickCount64()
    road = cv2.warpAffine(bgra, affine, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    serial += 1
    latest = ({'telemetry': t, 'frame_id': serial, 'capture_tick_ms': captured,
               'width': WIDTH, 'height': HEIGHT, 'bytes': NV12_SIZE * 2}, nv12(road) + nv12(bgra))
    conversion_ms = (time.monotonic()-conversion_start)*1000

@capture.event
def on_closed():
    stop.set()

def receive_commands(conn):
    try:
        while not stop.is_set():
            c = receive_json(conn)
            # Avoid sending to an absent native listener during loading screens.
            # Windows reports those ICMP port-unreachable replies on recvfrom.
            if telemetry is None or time.monotonic() - last_telemetry > .2:
                continue
            values = [float(c[k]) for k in ('steer', 'throttle', 'brake')]
            if not all(np.isfinite(values)):
                raise ValueError('Nonfinite actuator')
            mode = int(c['mode'])
            if not 0 <= mode <= 7:
                raise ValueError('Invalid actuator mode')
            data = COMMAND.pack(0x4347504f, VERSION, time.perf_counter_ns(), int(c['capture_tick_ms']),
                                int(c['vehicle']), mode, *values)
            udp.sendto(data, ('127.0.0.1', 8767))
            disengagement_trace.command(c, ctypes.windll.kernel32.GetTickCount64())
    except (ValueError, OSError, ConnectionError, KeyError) as e:
        print(f'Command connection ended: {e}', flush=True)
        stop.set()

threading.Thread(target=read_telemetry, daemon=True).start()
control = capture.start_free_threaded()
print('Capture ready. F6 in GTA enables the fixed forward camera. Waiting for native telemetry.', flush=True)
try:
    with socket.create_connection((args.host, 8765), timeout=3) as conn:
        conn.settimeout(2)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        send_json(conn, {'protocol': VERSION, 'token': token})
        threading.Thread(target=receive_commands, args=(conn,), daemon=True).start()
        last_frame = -1
        last_report = 0.
        sent_frames = 0
        report_frames = 0
        report_serial = 0
        report_callbacks = 0
        while not stop.is_set():
            start = time.monotonic()
            value = latest
            # Vehicle/IMU state must not wait for a converted video frame.
            # Send the newest native sample at control cadence, including on
            # video packets, instead of the older sample saved with the image.
            focused = u.GetForegroundWindow() == hwnd
            down = lambda key: bool(focused and u.GetAsyncKeyState(key) & 0x8000)
            current = telemetry if start-last_telemetry < .2 else None
            if current is not None:
                current = {**current, 'set_pressed': down(0x77), 'shift_pressed': down(0x10),
                           'nudge': int(down(0x66))-int(down(0x64)), 'drive_mode_key': down(0x2d)}
            if value and value[0]['frame_id'] != last_frame and ctypes.windll.kernel32.GetTickCount64() - value[0]['capture_tick_ms'] < 200:
                captured_header, payload = value
                header = {**captured_header, 'frame_id': sent_frames+1, 'telemetry': current, 'radar': radar}
                send_json(conn, header)
                conn.sendall(payload)
                send_ms = (time.monotonic()-start)*1000
                sent_frames += 1
                last_frame = captured_header['frame_id']
            else:
                send_json(conn, {'telemetry': current, 'radar': radar, 'bytes': 0})
            if start-last_report > 2:
                period = start-last_report
                (ROOT / 'reports/capture-status.json').write_text(json.dumps({
                    'frame': sent_frames, 'capture_serial': last_frame, 'telemetry': telemetry, 'radar': radar, 'tick_ms': ctypes.windll.kernel32.GetTickCount64(),
                    'capture_hz': round((capture_callbacks-report_callbacks)/period, 2),
                    'conversion_hz': round((serial-report_serial)/period, 2),
                    'sent_hz': round((sent_frames-report_frames)/period, 2),
                    'conversion_ms': round(conversion_ms, 2), 'send_ms': round(send_ms, 2)}))
                report_frames, report_serial = sent_frames, serial
                report_callbacks = capture_callbacks
                last_report = start
            stop.wait(max(0, .01-(time.monotonic()-start)))
finally:
    stop.set()
    control.stop()
    udp.close()
