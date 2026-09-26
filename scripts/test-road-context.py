import ctypes
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bridge'))
from gta_road_context import Packet, decode, projection_fit, validity


class RoadContextTest(unittest.TestCase):
    def fixture(self):
        return (ROOT/'build/native/road-context-native-fixture.bin').read_bytes()

    def test_native_layout(self):
        self.assertEqual(ctypes.sizeof(Packet), 344)
        p = decode(self.fixture())
        self.assertEqual((p['sequence'], p['vehicle'], p['ego']['y']), (7, 123, 200))
        self.assertEqual((p['forward_lanes'], p['backward_lanes'], p['median_gap']), (2, 1, 1.5))
        self.assertEqual((p['direction_label'], p['junction_distance_raw']), ('left', 123))
        self.assertNotIn('road_width', p)
        self.assertNotIn('junction_distance_m', p)

    def test_invalid_data(self):
        for data in (b'', self.fixture()[:-1], self.fixture()+b'x'):
            with self.assertRaises(ValueError): decode(data)
        for field, value in (('magic', 0), ('version', 7), ('flags', 1024), ('speed', math.nan)):
            p = Packet.from_buffer_copy(self.fixture())
            setattr(p, field, value)
            with self.assertRaises(ValueError): decode(bytes(p))
        p = Packet.from_buffer_copy(self.fixture())
        p.projections[0].valid = 2
        with self.assertRaises(ValueError): decode(bytes(p))

    def test_freshness_and_identity(self):
        p = decode(self.fixture())
        t = dict(tick_ms=1000, vehicle=123, flags=5)
        self.assertEqual(validity(p, t, 1200), (True, 'fresh'))
        self.assertFalse(validity(p, t, 2500)[0])
        self.assertFalse(validity(p, t, 900)[0])
        self.assertFalse(validity(p, dict(t, vehicle=456), 1200)[0])
        self.assertFalse(validity(p, dict(t, flags=7), 1200)[0])
        self.assertFalse(validity(p, None, 1200)[0])
        self.assertTrue(validity(p, dict(t, tick_ms=-1000), 1200)[0])
        self.assertFalse(validity(p, dict(t, tick_ms=-2000), 1200)[0])

    def test_projection_recovers_wrong_focal_and_center(self):
        p = decode(self.fixture())
        p['flags'] |= 256
        for point, xyz in zip(p['projections'], [(-3, 10, 0), (3, 10, 0), (0, 10, 2),
                                               (0, 10, -1), (-5, 30, 0), (5, 30, 0)]):
            x, y, z = xyz
            point.update(local=dict(x=x, y=y, z=z), u=(970+620*x/y)/1928,
                         v=(602-610*z/y)/1208, valid=1)
        fit = projection_fit(p)
        for field, focal, center in [('horizontal', 620, 970), ('vertical', 610, 602)]:
            self.assertAlmostEqual(fit[field]['focal_px'], focal)
            self.assertAlmostEqual(fit[field]['center_px'], center)
            self.assertLess(fit[field]['residual_px'], 1e-9)
        p['flags'] &= ~256
        self.assertIsNone(projection_fit(p))


if __name__ == '__main__':
    unittest.main()
