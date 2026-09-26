import unittest
from types import SimpleNamespace
from gta_cruise import GTACruise


class CruiseTests(unittest.TestCase):
    def setUp(self):
        self.c = GTACruise()
        self.t = SimpleNamespace(is_metric=False, cruise_increase=1, cruise_increase_long=5,
                                 set_speed_offset=0, set_speed_limit=False, reverse_cruise_increase=False)

    def test_tap_hold_and_units(self):
        self.c.update({'flags':4096}, False, 1., self.t)
        self.c.update({'flags':0}, False, 1.15, self.t)
        self.assertAlmostEqual(self.c.speed, 31*.44704)
        self.c.update({'flags':4096}, False, 2., self.t)
        self.c.update({'flags':4096}, False, 2.51, self.t)
        self.assertAlmostEqual(self.c.speed, 35*.44704)
        self.c.update({'flags':0}, False, 2.7, self.t)
        self.assertAlmostEqual(self.c.speed, 35*.44704)  # no extra release step
        self.t.is_metric = True
        self.t.cruise_increase = 3
        old = self.c.speed
        self.c.step(-1, False, self.t)
        self.assertAlmostEqual(self.c.speed, old-3/3.6)

    def test_set_cancel_resume(self):
        self.c.update({'set_pressed':True,'speed':17.}, True, 1., self.t)
        self.assertEqual(self.c.speed, 17.)
        self.c.update({}, False, 2., self.t)
        self.c.update({'set_pressed':True,'shift_pressed':True,'speed':5.}, True, 3., self.t)
        self.assertEqual(self.c.speed, 17.)

    def test_offset_reverse_and_limits(self):
        self.c.speed = 20.
        self.t.is_metric = True
        self.t.set_speed_offset = 5.
        self.c.step(1, True, self.t)
        self.assertAlmostEqual(self.c.speed, 80/3.6)
        self.c.step(-1, True, self.t)
        self.assertAlmostEqual(self.c.speed, 75/3.6)
        self.c.speed = 20/3.6
        self.t.reverse_cruise_increase = True
        self.c.step(1, False, self.t)
        self.assertAlmostEqual(self.c.speed, 25/3.6)
        self.c.speed = 1.
        self.c.step(-1, True, self.t)
        self.assertEqual(self.c.speed, 1.)

if __name__ == '__main__':
    unittest.main()
