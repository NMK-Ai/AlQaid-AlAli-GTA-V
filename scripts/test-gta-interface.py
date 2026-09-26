"""Check the GTA profile and full-range controls independently of the live game."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import math

os.environ['GTA_SIMULATION'] = os.environ['SIMULATION'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from gta_interface import CarInterface, actuators_to_game, MAX_WHEEL_ANGLE_DEG, encode_pedal
from gta_lateral import road_wheel_angle, shape_curvature
import gta_lateral
# Exercise the genuine installed angle controller with this staged candidate
# module, without replacing files used by the user's running drive.
sys.modules['openpilot.tools.gta.gta_lateral'] = gta_lateral
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle
from cereal import car
from gta_turn_rate_patch import patch_angle_feedback

# Compile the candidate around the real pinned controller without mutating
# the files used by the user's running drive.
angle_source = Path('/data/openpilot/selfdrive/controls/lib/latcontrol_angle.py').read_text()
candidate = patch_angle_feedback(angle_source)
assert patch_angle_feedback(candidate) == candidate
angle_namespace = {}
exec(compile(candidate, 'candidate-latcontrol-angle.py', 'exec'), angle_namespace)
LatControlAngle = angle_namespace['LatControlAngle']


class GTATests(unittest.TestCase):
    def test_recorded_restart_request_survives_game_trigger_deadzone(self):
        # rlog frame 64909: +0.2134936 m/s^2 actuator output, stationary.
        accel = .21349355578422546
        _, throttle, brake = actuators_to_game(0., accel, False, True)
        game_effective = lambda raw: max(0., (raw - .25) / .75)
        self.assertEqual(game_effective(accel/4.), 0.)  # previous encoding
        self.assertAlmostEqual(game_effective(throttle), accel/4.)
        self.assertEqual(brake, 0.)

    def test_recorded_gentle_brake_is_not_encoded_as_quarter_pedal(self):
        # Camera-reviewed frames 16551-16570: -0.240 requested but -5.87
        # measured m/s^2 with raw brake 0.272. Keep the new request small.
        _, throttle, brake = actuators_to_game(0., -.2399335504, False, True, speed=12.)
        self.assertEqual(throttle, 0.)
        self.assertLess(brake, .02)
        # Observed modest-brake response interval; this is an offline plant
        # estimate, not evidence that the new mapping has been driven yet.
        for measured_gain in (17.6, 20., 23.5):
            self.assertLess(abs(-measured_gain*brake - (-.2399335504)), .05)

    def test_tiny_brake_request_is_continuous_at_release(self):
        for request in (-1e-7,-1e-6,-1e-5):
            _, gas, brake = actuators_to_game(0.,request,False,True,speed=5.)
            self.assertEqual(gas,0.)
            self.assertLess(brake,1e-6)

    def test_creep_does_not_trigger_native_full_handbrake(self):
        for speed in (0., .05, .2, .8, 1.):
            # Native adapter converts any brake at these speeds to full hold.
            self.assertEqual(actuators_to_game(0.,-.1,False,True,speed=speed,stopping=False), (0.,0.,0.))
            _, gas, brake = actuators_to_game(0.,-.1,False,True,speed=speed,stopping=True)
            self.assertEqual(gas,0.)
            self.assertGreater(brake,0.)
            _, gas, brake = actuators_to_game(0.,.2,False,True,speed=speed,stopping=False)
            self.assertGreater(gas,.25)
            self.assertEqual(brake,0.)

    def test_pedal_encoding_preserves_release_and_continuous_effective_travel(self):
        for i in range(1001):
            travel = i/1000.
            encoded = encode_pedal(travel)
            self.assertTrue(0. <= encoded <= 1.)
            self.assertAlmostEqual(max(0., (encoded-.25)/.75), travel)
        self.assertEqual(encode_pedal(0.), 0.)
        self.assertEqual(encode_pedal(-1.), 0.)
        self.assertEqual(encode_pedal(2.), 1.)
        for accel in [-8., -.001, 0., .001, 4.]:
            self.assertEqual(actuators_to_game(0.,accel,False,False), (0.,0.,0.))
            _, gas, brake = actuators_to_game(0.,accel,False,True)
            self.assertFalse(gas and brake)
        self.assertEqual(actuators_to_game(0.,0.,False,True), (0.,0.,0.))
        for value in [float('nan'),float('inf'),-float('inf')]:
            with self.assertRaises(ValueError): encode_pedal(value)

    def test_high_speed_candidate_reaches_real_angle_controller(self):
        cp = CarInterface.get_params()
        controller = LatControlAngle(cp, None, .01)
        cs = car.CarState.new_message()
        cs.vEgo = 35.
        cs.yawRate = .003*cs.vEgo
        params = SimpleNamespace(roll=0., angleOffsetDeg=0.)
        _, angle, _ = controller.update(True, cs, VehicleModel(cp), params, False, -.003, False,
                                        .1, None, None, None)
        self.assertAlmostEqual(angle, road_wheel_angle(-.003, cp.wheelbase, 35.))
        self.assertGreater(angle, road_wheel_angle(-.003, cp.wheelbase, 25.))

    def test_gta_saturation_uses_physical_lock_not_road_wheel_tracking_error(self):
        cp = CarInterface.get_params()
        controller = LatControlAngle(cp, None, .01)
        vm = VehicleModel(cp)
        cs = car.CarState.new_message()
        cs.vEgo, cs.steeringAngleDeg = 23.044878, 0.
        params = SimpleNamespace(roll=0., angleOffsetDeg=0.)
        for requested, expected_saturated in ((-.0104177054, False), (-1., True)):
            controller.reset()
            curvature, limited = shape_curvature(cs.vEgo, requested, cp.wheelbase, MAX_WHEEL_ANGLE_DEG)
            cs.yawRate = -curvature*cs.vEgo
            for _ in range(150):
                _, angle, log = controller.update(True, cs, vm, params, False, curvature, limited,
                                                   .1, None, None, None)
            self.assertEqual(log.saturated, expected_saturated)
            self.assertAlmostEqual(actuators_to_game(angle, 0., True, False)[0], angle)
        # No saturation should build while lateral control is inactive.
        controller.reset()
        for _ in range(150):
            _, _, log = controller.update(False, cs, vm, params, False, curvature, True,
                                           .1, None, None, None)
        self.assertFalse(log.saturated)

    def test_non_gta_angle_saturation_is_unchanged(self):
        cp = CarInterface.get_params()
        cp.brand = 'ford'
        controller = LatControlAngle(cp, None, .01)
        cs = car.CarState.new_message()
        cs.vEgo = 20.
        # Isolate the existing 2.5-degree tracking-error branch from VM tuning.
        vm = SimpleNamespace(get_steer_from_curvature=lambda *args: math.radians(5.))
        params = SimpleNamespace(roll=0., angleOffsetDeg=0.)
        for _ in range(150):
            _, _, log = controller.update(True, cs, vm, params, False, -.01, False,
                                           .1, None, None, None)
        self.assertTrue(log.saturated)

    def test_real_angle_controller_ignores_corrupted_column_learning_for_gta(self):
        cp = CarInterface.get_params()
        controller = LatControlAngle(cp, None, .01)
        vm = VehicleModel(cp)
        vm.update_params(.3, 1.9)
        cs = car.CarState.new_message()
        cs.vEgo, cs.steeringAngleDeg = 12., 1.2
        cs.yawRate = .01*cs.vEgo
        params = SimpleNamespace(roll=.04, angleOffsetDeg=-4.5)
        _, angle, log = controller.update(True, cs, vm, params, False, -.01, False,
                                           .1, None, None, None)
        self.assertAlmostEqual(angle, road_wheel_angle(-.01, cp.wheelbase, cs.vEgo), places=6)
        self.assertAlmostEqual(log.steeringAngleDeg, 1.2, places=5)
        _, angle, _ = controller.update(False, cs, vm, params, False, -.01, False,
                                        .1, None, None, None)
        self.assertAlmostEqual(angle, 1.2, places=5)

    def test_game_profile_has_full_control_from_standstill(self):
        cp = CarInterface.get_params()
        self.assertEqual(cp.brand, 'gta')
        self.assertFalse(cp.passive or cp.dashcamOnly)
        self.assertTrue(cp.openpilotLongitudinalControl)
        self.assertEqual(cp.mass, 1250.)
        self.assertEqual(MAX_WHEEL_ANGLE_DEG, 40.)
        self.assertEqual(cp.steerControlType, 'angle')
        self.assertEqual(cp.minSteerSpeed, 0.)
        self.assertLess(cp.minEnableSpeed, 0.)
        vm = VehicleModel(cp)
        self.assertGreater(vm.get_steer_from_curvature(.1, 5., 0.), 0.)

    def test_turn_feedback_uses_pose_and_clears_on_driver_override(self):
        cp=CarInterface.get_params()
        c=LatControlAngle(cp,None,.01)
        cs=car.CarState.new_message();cs.vEgo=10.2589
        params=SimpleNamespace(roll=0.,angleOffsetDeg=0.)
        pose=SimpleNamespace(angular_velocity=SimpleNamespace(z=-.1079))
        args=(True,cs,VehicleModel(cp),params,False,-.0065,False,.1,pose,None,None)
        for _ in range(100): _,angle,_=c.update(*args)
        self.assertLess(angle,road_wheel_angle(-.0065,cp.wheelbase,cs.vEgo))
        self.assertNotEqual(c.gta_turn_rate.integral,0.)
        cs.steeringPressed=True
        _,angle,_=c.update(*args)
        self.assertEqual(c.gta_turn_rate.integral,0.)
        self.assertAlmostEqual(angle,road_wheel_angle(-.0065,cp.wheelbase,cs.vEgo))
        c.reset();self.assertIsNone(c.gta_turn_rate.measured_curvature)

    def test_no_honda_or_bringup_caps_and_no_command_when_disabled(self):
        self.assertEqual(actuators_to_game(-35., 4., True, True), (-35., 1., 0.))
        self.assertEqual(actuators_to_game(35., -8., True, True), (35., 0., .4))
        self.assertEqual(actuators_to_game(35., -20., True, True), (35., 0., 1.))
        self.assertEqual(actuators_to_game(500., 80., False, False), (0., 0., 0.))
        self.assertEqual(actuators_to_game(-500., 80., True, False), (-40., 0., 0.))
        self.assertEqual(actuators_to_game(4., 0., True, False), (4., 0., 0.))
        with self.assertRaises(ValueError):
            actuators_to_game(float('nan'), 0., True, True)

    def test_profile_unavailable_outside_simulation(self):
        os.environ['SIMULATION'] = '0'
        try:
            with self.assertRaises(RuntimeError):
                CarInterface.get_params()
        finally:
            os.environ['SIMULATION'] = '1'


if __name__ == '__main__':
    unittest.main()
