import math
import unittest
from gta_lateral import shape_curvature, road_wheel_angle, road_curvature


class LateralResponseTests(unittest.TestCase):
    def test_road_wheel_geometry_and_left_right_sign(self):
        # A 100 m left circle: model curvature negative, +left GTA wheel/yaw.
        angle = road_wheel_angle(-.01, 2.8)
        self.assertGreater(angle, 0.)
        self.assertAlmostEqual(math.tan(math.radians(angle))/2.8, .01)
        self.assertAlmostEqual(road_wheel_angle(.01, 2.8), -angle)
        self.assertAlmostEqual(road_wheel_angle(-math.tan(math.radians(35))/2.8, 2.8), 35.)

    def test_recorded_false_saturation_demand_reaches_actuator(self):
        # Genuine warning sample: 23.04 m/s, only ~5.8 degrees required.
        # The old 4 m/s^2 envelope clipped this well short of the 40-degree lock.
        requested = -.010417705401778221
        result, limited = shape_curvature(23.044878, requested, 2.5986464, 40.)
        self.assertEqual(result, requested)
        self.assertFalse(limited)
        self.assertLess(abs(road_wheel_angle(result, 2.5986464, 23.044878)), 6.)

    def test_full_wheel_range_at_all_speeds_and_reversal(self):
        for speed in (0., 2., 15., 25., 40.):
            for angle in (35., -35., 0.):
                request = road_curvature(angle, 2.5986464, speed)
                result, limited = shape_curvature(speed, request, 2.5986464, 40.)
                self.assertFalse(limited)
                self.assertAlmostEqual(road_wheel_angle(result, 2.5986464, speed), angle)
            for sign in (-1, 1):
                result, limited = shape_curvature(speed, sign*10., 2.5986464, 40.)
                self.assertTrue(limited)
                self.assertAlmostEqual(road_wheel_angle(result, 2.5986464, speed), -sign*40.)

    def test_measured_krieger_turn_response_at_speed(self):
        # Independent measured plant coefficients from two real routes. The
        # calibrated command must reduce understeer across their uncertainty.
        for actual_k in (.0110, .01615):
            for speed in (5., 10., 15., 20., 25.):
                for requested in (-.003, .003):
                    old = road_wheel_angle(requested, 2.5986464)
                    new = road_wheel_angle(requested, 2.5986464, speed)
                    actual = -math.tan(math.radians(new))/(2.5986464+actual_k*speed**2)
                    old_actual = -math.tan(math.radians(old))/(2.5986464+actual_k*speed**2)
                    self.assertLess(abs(actual-requested), abs(old_actual-requested))
                    self.assertLess(abs(actual/requested-1), .18)
                    self.assertAlmostEqual(road_curvature(new, 2.5986464, speed), requested)
        self.assertEqual(road_wheel_angle(.01, 2.6, 40), road_wheel_angle(.01, 2.6, 60))

    def test_new_high_speed_measurement_not_frozen_at_56mph(self):
        # Route 14: independent wheel-angle/yaw fit at 30-40 m/s, K=0.015525.
        speed, curvature, actual_k, wb = 35., -.003, .015525, 2.5986464
        old = math.atan(-curvature*(wb+.0135*25**2))
        new = math.radians(road_wheel_angle(curvature, wb, speed))
        old_actual = -math.tan(old)/(wb+actual_k*speed**2)
        new_actual = -math.tan(new)/(wb+actual_k*speed**2)
        self.assertLess(abs(new_actual-curvature), abs(old_actual-curvature)/2)

    def test_speed_conversion_rejects_nonfinite_input(self):
        for bad in (math.nan, math.inf):
            with self.assertRaises(ValueError):
                road_wheel_angle(.01, 2.6, bad)
            with self.assertRaises(ValueError):
                road_curvature(bad, 2.6, 10.)

    def test_invalid_inputs(self):
        for bad in [math.nan, math.inf]:
            with self.assertRaises(ValueError):
                shape_curvature(15., bad, 2.6, 40.)
            with self.assertRaises(ValueError):
                shape_curvature(bad, .01, 2.6, 40.)
        for bad_lock in (0., -40., 90., math.nan):
            with self.assertRaises(ValueError):
                shape_curvature(15., .01, 2.6, bad_lock)


if __name__ == '__main__':
    unittest.main()
