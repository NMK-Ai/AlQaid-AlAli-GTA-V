"""Local simulation transport. Units: meters, seconds, degrees."""
import json
import math
import struct

WIDTH, HEIGHT = 1928, 1208
VERSION = 4
NV12_SIZE = WIDTH * HEIGHT * 3 // 2
TELEMETRY = struct.Struct('<IIQQIIII22fI')
COMMAND = struct.Struct('<IIQQIIfff')
KEYS = ('magic version sequence tick_ms frame vehicle model flags speed steer_input gas brake '
        'px py pz vx vy vz pitch roll heading wx wy wz cruise_speed wheelbase '
        'wheel_angle_deg wheel_left_z wheel_right_z applied_steer spawn_status').split()
MAX_HEADER = 8192

def decode_telemetry(data):
    if len(data) != TELEMETRY.size:
        raise ValueError('Wrong telemetry size')
    t = dict(zip(KEYS, TELEMETRY.unpack(data)))
    if t['magic'] != 0x5447504f or t['version'] != VERSION or not all(math.isfinite(t[k]) for k in KEYS[8:]):
        raise ValueError('Invalid telemetry')
    return t

def receive_exact(sock, size):
    result = bytearray(size)
    offset = 0
    while offset < size:
        n = sock.recv_into(memoryview(result)[offset:])
        if not n:
            raise ConnectionError('Transport closed')
        offset += n
    return bytes(result)

def send_json(sock, obj):
    data = json.dumps(obj, separators=(',', ':'), allow_nan=False).encode()
    if len(data) > MAX_HEADER:
        raise ValueError('Header too large')
    sock.sendall(struct.pack('<I', len(data)) + data)

def receive_json(sock):
    length, = struct.unpack('<I', receive_exact(sock, 4))
    if not 0 < length <= MAX_HEADER:
        raise ValueError('Invalid header length')
    return json.loads(receive_exact(sock, length))
