import copy
import json
import math
import unittest
from unittest.mock import patch
from pathlib import Path
from gta_radar import HEADER, POINT, PACKET_SIZE, MAGIC, RadarReceiver, decode_radar, validate


def packet(sequence=1, tick=1000, points=True):
    return dict(version=1, sequence=sequence, tick_ms=tick, vehicle=123, valid=True,
                points=[dict(id=7, tick_ms=tick-33, d=30., y=.5, v=-5.)] if points else [])


class RadarTests(unittest.TestCase):
    def test_receiver_update_after_loop_timestamp_is_not_a_sensor_failure(self):
        r=RadarReceiver()
        old_loop_time=10.
        # TCP receiver wins the race while GTAVehicle is assembling carState.
        r.update(packet(),old_loop_time+.0001)
        t=dict(vehicle=123,tick_ms=1000)
        self.assertFalse(r.data(t,True,old_loop_time)[0])  # Reproduce old bug.
        with patch('gta_radar.time.monotonic',return_value=old_loop_time+.0002):
            valid,data=r.data(t,True)  # Production path snapshots before clock.
        self.assertTrue(valid)
        self.assertEqual(len(data['points']),1)
        self.assertFalse(data['errors']['radarUnavailableTemporary'])

    def test_packet_written_by_native_sensor(self):
        fixture=Path(__file__).resolve().parents[1]/'build/native/radar-native-fixture.bin'
        if not fixture.exists(): self.skipTest('Run native CTest first')
        p=decode_radar(fixture.read_bytes())
        self.assertEqual(len(p['points']),1)
        self.assertGreater(p['points'][0]['y'],0)
        self.assertEqual(p['points'][0]['v'],-5.)

    def test_binary_layout_and_coordinate_signs(self):
        data = HEADER.pack(MAGIC, 1, 1, 1000, 123, 1, 1)
        data += POINT.pack(7, 967, 30., .5, -5.) + bytes(15*POINT.size)
        self.assertEqual(len(data), 420)
        self.assertEqual(decode_radar(data), packet())
        for bad in (data[:-1], data+b'\0', b'\0'*PACKET_SIZE):
            with self.assertRaises(ValueError): decode_radar(bad)

    def test_duplicate_headers_do_not_refresh_and_empty_is_valid(self):
        r=RadarReceiver(); r.update(packet(),10.)
        t=dict(tick_ms=1000, vehicle=123)
        r.update(packet(),10.19)
        self.assertTrue(r.data(t,True,10.1)[0])
        self.assertFalse(r.data(t,True,10.21)[0])
        r.update(packet(2,1200,False),10.22); t['tick_ms']=1200
        valid,data=r.data(t,True,10.23)
        self.assertTrue(valid); self.assertEqual(data['points'],[])
        self.assertFalse(data['errors']['radarUnavailableTemporary'])

    def test_reject_bad_sensor_data(self):
        for edit in (lambda p:p.update(version=9), lambda p:p.update(sequence=-1),
                     lambda p:p['points'][0].update(v=math.nan),
                     lambda p:p['points'][0].update(d=-1.),
                     lambda p:p['points'][0].update(y=29.),
                     lambda p:p['points'][0].update(tick_ms=700),
                     lambda p:p['points'].append(p['points'][0].copy())):
            p=packet(); edit(p)
            with self.assertRaises(ValueError): validate(p)

    def test_vehicle_change_disconnect_and_old_measurement(self):
        r=RadarReceiver(); r.update(packet(),10.)
        t=dict(tick_ms=1000,vehicle=123)
        self.assertFalse(r.data({**t,'vehicle':456},True,10.01)[0])
        self.assertFalse(r.data(t,False,10.01)[0])
        self.assertFalse(r.data({**t,'tick_ms':1300},True,10.01)[0])
        valid,data=r.data(t,True,10.18)
        self.assertTrue(valid); self.assertEqual(data['points'],[])
        r.update(None,10.19); self.assertFalse(r.data(t,True,10.19)[0])

    def test_16_tracks_fit_existing_transport_header(self):
        p=packet()
        p['points']=[dict(id=i+1,tick_ms=1000,d=149.123456789,y=-29.123456789,v=-100.123456789) for i in range(16)]
        validate(p)
        # Reserve 2 KB for existing vehicle/camera header.
        self.assertLess(len(json.dumps(p).encode())+2048,8192)


if __name__=='__main__': unittest.main()
