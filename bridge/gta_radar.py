"""Native GTA radar transport and freshness; no model lead fabrication."""
import math
import struct
import time
from collections import Counter

MAGIC = 0x5247504f
HEADER = struct.Struct('<IIQQIII')
POINT = struct.Struct('<IQfff')
MAX_POINTS = 16
PACKET_SIZE = HEADER.size + MAX_POINTS*POINT.size


def validate(packet):
    def integer(value, low, high):
        return type(value) is int and low <= value <= high
    if not isinstance(packet, dict) or packet.get('version') != 1:
        raise ValueError('Invalid radar protocol')
    if not all(integer(packet.get(k), 0, 2**64-1) for k in ('sequence', 'tick_ms')):
        raise ValueError('Invalid radar timestamp')
    if not integer(packet.get('vehicle'), 0, 2**32-1) or type(packet.get('valid')) is not bool:
        raise ValueError('Invalid radar vehicle/validity')
    points = packet.get('points')
    if not isinstance(points, list) or len(points) > MAX_POINTS:
        raise ValueError('Invalid radar count')
    ids = set()
    for p in points:
        if not isinstance(p, dict) or not integer(p.get('id'), 1, 2**31-1) or p['id'] in ids:
            raise ValueError('Invalid radar identity')
        ids.add(p['id'])
        if not integer(p.get('tick_ms'), max(0, packet['tick_ms']-150), packet['tick_ms']):
            raise ValueError('Invalid radar measurement age')
        if not all(type(p.get(k)) in (int, float) and math.isfinite(p[k]) for k in ('d', 'y', 'v')):
            raise ValueError('Nonfinite radar point')
        if not .5 < p['d'] <= 150 or abs(p['y']) > min(30., p['d']*.700208) or abs(p['v']) > 200:
            raise ValueError('Radar point outside sensor limits')
    return packet


def decode_radar(data):
    if len(data) != PACKET_SIZE:
        raise ValueError('Wrong radar packet size')
    magic, version, sequence, tick, vehicle, valid, count = HEADER.unpack_from(data)
    if magic != MAGIC or valid not in (0, 1) or count > MAX_POINTS:
        raise ValueError('Invalid radar header')
    result = dict(version=version, sequence=sequence, tick_ms=tick, vehicle=vehicle, valid=bool(valid), points=[])
    for i in range(count):
        values = POINT.unpack_from(data, HEADER.size+i*POINT.size)
        result['points'].append(dict(zip(('id', 'tick_ms', 'd', 'y', 'v'), values)))
    return validate(result)


class RadarReceiver:
    def __init__(self):
        self.sample = None
        self.rejects = Counter()

    def update(self, packet, now):
        if packet is None:
            self.sample = None
            return
        try:
            validate(packet)
        except ValueError:
            self.sample = None
            raise
        previous = self.sample
        if previous and (packet['sequence'] <= previous[0]['sequence'] or packet['tick_ms'] <= previous[0]['tick_ms']):
            return  # Repeated transport headers cannot make a sensor fresh.
        self.sample = (packet, now)

    def data(self, telemetry, vehicle_valid, now=None):
        sample = self.sample
        # Snapshot first, then read the clock. The receiver thread may publish
        # a new sample after the vehicle loop captured its earlier timestamp.
        # Comparing that new sample against the loop's old time falsely made
        # a fresh packet "from the future" and invalidated the real planner.
        if now is None:
            now = time.monotonic()
        valid = False
        points = []
        reason = 'no_sample' if vehicle_valid else 'vehicle_inactive'
        if sample and telemetry and vehicle_valid:
            p, received = sample
            elapsed = now-received
            native_age = telemetry['tick_ms']-p['tick_ms']
            valid = (p['valid'] and p['vehicle'] == telemetry['vehicle'] and
                     0 <= elapsed < .2 and -100 <= native_age < 200)
            if not p['valid']: reason = 'sensor_unavailable'
            elif p['vehicle'] != telemetry['vehicle']: reason = 'vehicle_changed'
            elif elapsed < 0: reason = 'clock_order'
            elif elapsed >= .2 or native_age >= 200: reason = 'stale_packet'
            elif native_age < -100: reason = 'telemetry_behind'
            if valid:
                for point in p['points']:
                    age = max(0, native_age, elapsed*1000) + p['tick_ms']-point['tick_ms']
                    if age < 200:
                        points.append(dict(trackId=point['id'], dRel=point['d'], yRel=point['y'], vRel=point['v'],
                                           aRel=math.nan, yvRel=math.nan, measured=True))
        if not valid and vehicle_valid:
            self.rejects[reason] += 1
        return bool(valid), dict(points=points, errors={'radarUnavailableTemporary': not valid})

    def message(self, telemetry, vehicle_valid, now=None):
        from cereal import messaging
        valid, data = self.data(telemetry, vehicle_valid, now)
        msg = messaging.new_message('liveTracks', valid=valid)
        msg.liveTracks = data
        return msg
