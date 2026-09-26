"""Read-only Enhanced road/projection diagnostics, isolated from control transport."""
import ctypes as c
import json
import math
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8772
DIRECTIONS = {0: 'unknown', 1: 'calculating', 2: 'continue', 3: 'left', 4: 'right',
              5: 'straight', 6: 'sharp_left', 7: 'sharp_right', 8: 'recalculating'}


class Vec(c.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [('x', c.c_float), ('y', c.c_float), ('z', c.c_float)]


class Projection(c.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [('local', Vec), ('u', c.c_float), ('v', c.c_float), ('valid', c.c_uint32)]


class Packet(c.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [('magic', c.c_uint32), ('version', c.c_uint32), ('sequence', c.c_uint64),
               ('tick_ms', c.c_uint64), ('vehicle', c.c_uint32), ('flags', c.c_uint32),
               ('update_ms', c.c_float), ('ego', Vec), ('heading', c.c_float), ('speed', c.c_float),
               ('node', Vec), ('node_heading', c.c_float), ('node_lanes', c.c_int32),
               ('density', c.c_int32), ('node_properties', c.c_int32), ('edge_a', Vec), ('edge_b', Vec),
               ('forward_lanes', c.c_int32), ('backward_lanes', c.c_int32), ('median_gap', c.c_float),
               ('boundary_a', Vec), ('boundary_b', Vec), ('waypoint', Vec), ('direction', c.c_int32),
               ('junction_distance_raw', c.c_float), ('navigation_aux_raw', c.c_float),
               ('navigation_return', c.c_int32), ('camera', Vec), ('camera_rotation', Vec),
               ('camera_fov', c.c_float), ('projections', Projection * 6)]


def plain(value):
    if isinstance(value, c.Structure):
        return {name: plain(getattr(value, name)) for name, _ in value._fields_}
    if isinstance(value, c.Array):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite road context')
    return value


def decode(data):
    if len(data) != c.sizeof(Packet):
        raise ValueError('Wrong road context packet size')
    result = plain(Packet.from_buffer_copy(data))
    if result['magic'] != 0x4441504f or result['version'] != 1 or result['flags'] & ~511:
        raise ValueError('Invalid road context header')
    if any(p['valid'] not in (0, 1) for p in result['projections']):
        raise ValueError('Invalid projection validity')
    result['direction_label'] = DIRECTIONS.get(result['direction'], 'unknown')
    # All native values retain their actual units/meaning. In particular, the
    # junction distance is NOT asserted to be metres and median_gap is NOT width.
    return result


def validity(packet, telemetry, now_ms):
    if not packet:
        return False, 'waiting_for_adapter'
    if not -50 <= now_ms-packet['tick_ms'] < 1500:
        return False, 'stale_road_packet'
    if not packet['flags'] & 1:
        return False, 'camera_or_vehicle_inactive'
    # windows_host intentionally writes its report every two seconds. Keep
    # native road freshness strict while allowing one report interval + margin.
    if not telemetry or not -50 <= now_ms-telemetry['tick_ms'] < 3000:
        return False, 'stale_vehicle_telemetry'
    if packet['vehicle'] != telemetry['vehicle']:
        return False, 'vehicle_changed'
    if not telemetry['flags'] & 1 or telemetry['flags'] & 2:
        return False, 'vehicle_inactive'
    return True, 'fresh'


def projection_fit(packet, width=1928, height=1208):
    """Fit normalized screen points against camera-relative probe positions.

    A moving camera may lag entity coordinates by one render frame. Use steady
    samples and residuals to validate the fit before changing intrinsics.
    """
    points = [p for p in packet['projections'] if p['valid'] and p['local']['y'] > 0]
    if not packet['flags'] & 256 or len(points) < 4:
        return None

    def fit(axis, screen, size, sign):
        xs = [sign*p['local'][axis]/p['local']['y'] for p in points]
        ys = [p[screen]*size for p in points]
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        denom = sum((x-mx)**2 for x in xs)
        if denom < 1e-9:
            return None
        focal = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/denom
        center = my-focal*mx
        residual = math.sqrt(sum((y-center-focal*x)**2 for x, y in zip(xs, ys))/len(xs))
        return dict(focal_px=focal, center_px=center, residual_px=residual)

    return dict(horizontal=fit('x', 'u', width, 1), vertical=fit('z', 'v', height, -1),
                samples=len(points), expected_focal_px=567.,
                note='Confirm with stationary samples; projection may use the preceding render frame.')


def write_status(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def main():
    reports = ROOT/'reports'
    reports.mkdir(exist_ok=True)
    tick = c.windll.kernel32.GetTickCount64
    tick.restype = c.c_uint64
    packet = None
    rejects = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(('127.0.0.1', PORT))
    except OSError as exc:
        if exc.winerror == 10048:
            return  # One receiver per session. Launching it again is harmless.
        raise
    sock.settimeout(.5)
    history = reports/'road-context-history.jsonl'
    while True:
        received = False
        try:
            data, peer = sock.recvfrom(4096)
            if peer[0] != '127.0.0.1':
                continue
            new = decode(data)
            # Freshness is tied to the native clock, never refreshed by replay.
            if packet is None or new['tick_ms'] > packet['tick_ms']:
                packet = new
                received = True
        except socket.timeout:
            pass
        except ValueError:
            rejects += 1
        try:
            capture = json.loads((reports/'capture-status.json').read_text())
            telemetry = capture.get('telemetry')
        except (OSError, ValueError):
            capture = {}
            telemetry = None
        now_ms = tick()
        valid, reason = validity(packet, telemetry, now_ms)
        status = dict(time=datetime.now(timezone.utc).isoformat(), tick_ms=now_ms, valid=valid,
                      reason=reason, rejected_packets=rejects, packet=packet,
                      projection=projection_fit(packet) if valid else None,
                      capture_frame=capture.get('frame'), capture_tick_ms=capture.get('tick_ms'),
                      drives_vehicle=False)
        try:
            write_status(reports/'road-context.json', status)
            if received:
                # Bounded diagnostics: preserve one previous ~16 MB file.
                if history.exists() and history.stat().st_size > 16*1024*1024:
                    history.replace(reports/'road-context-history.previous.jsonl')
                with history.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(status, allow_nan=False)+'\n')
        except OSError:
            # A report reader must not terminate the passive receiver.
            pass


if __name__ == '__main__':
    main()
