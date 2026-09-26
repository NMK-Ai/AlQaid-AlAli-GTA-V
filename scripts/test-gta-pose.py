"""Real livePose schema/consumer tests for GTA motion, without publishing."""
import math
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'bridge'))
from gta_pose import GTAPose, camera_motion, GTA_TO_NED, CAMERA_OFFSET_DEVICE
from openpilot.selfdrive.locationd.helpers import Pose
from openpilot.common.transformations.orientation import rot_from_euler


def telemetry(**changes):
    result = dict(vehicle=1, sequence=1, tick_ms=1000, roll=0., pitch=0., heading=0.,
                  vx=0., vy=0., vz=0., wx=0., wy=0., wz=0.)
    result.update(changes)
    return result


class PoseTests(unittest.TestCase):
    def setUp(self):
        self.flags = patch.dict(os.environ, SIMULATION='1', GTA_SIMULATION='1')
        self.flags.start()
        self.addCleanup(self.flags.stop)

    def test_requires_simulator_flags(self):
        with patch.dict(os.environ, GTA_SIMULATION='0'):
            with self.assertRaises(RuntimeError): GTAPose()

    def test_heading_axes_and_rotation_sign(self):
        for heading in (0., 90., -90., 179.):
            h = math.radians(heading)
            r, v, w = camera_motion(telemetry(heading=heading, vx=-10*math.sin(h), vy=10*math.cos(h)))
            np.testing.assert_allclose(v, [10,0,0], atol=1e-6)
            self.assertAlmostEqual(r[2], -h)
        _, v, w = camera_motion(telemetry(wz=.2))
        np.testing.assert_allclose(w, [0,0,-.2])
        np.testing.assert_allclose(v, np.cross(w, CAMERA_OFFSET_DEVICE))

    def test_pitch_roll_and_full_world_to_camera_transform(self):
        rpy = np.radians([12., -8., -60.])
        ned_from_device = rot_from_euler(rpy)
        velocity = np.array([15., .3, -.1])
        angular = np.array([.1, .2, -.3])
        world_v = GTA_TO_NED.T @ ned_from_device @ velocity
        world_w = GTA_TO_NED.T @ ned_from_device @ angular
        r,v,w = camera_motion(telemetry(roll=12,pitch=-8,heading=60,
                            vx=world_v[0],vy=world_v[1],vz=world_v[2],
                            wx=world_w[0],wy=world_w[1],wz=world_w[2]))
        np.testing.assert_allclose(r, rpy)
        np.testing.assert_allclose(w, angular)
        np.testing.assert_allclose(v, velocity+np.cross(angular,CAMERA_OFFSET_DEVICE))

    def test_live_schema_acceleration_and_consumer(self):
        pose = GTAPose()
        pose.update(telemetry(vy=10), True, 1.)
        self.assertFalse(pose.message(1.,True).valid)
        pose.update(telemetry(sequence=2,tick_ms=1050,vy=10.1), True, 1.05)
        msg=pose.message(1.05,True)
        self.assertTrue(msg.valid and msg.livePose.inputsOK and msg.livePose.sensorsOK)
        consumer=Pose.from_live_pose(msg.livePose)
        np.testing.assert_allclose(consumer.acceleration.xyz, [2,0,0], atol=1e-5)
        np.testing.assert_allclose(consumer.velocity.xyz, [10.1,0,0], atol=1e-5)
        self.assertGreater(consumer.angular_velocity.z_std, 0)

    def test_repeated_or_stale_state_cannot_stay_valid(self):
        pose=GTAPose()
        pose.update(telemetry(),True,1.)
        last=telemetry(sequence=2,tick_ms=1050)
        pose.update(last,True,1.05)
        pose.update(last,True,1.24)
        self.assertFalse(pose.message(1.26,True).valid)
        self.assertFalse(pose.message(1.04,True).valid)
        self.assertFalse(pose.message(1.1,False).livePose.inputsOK)

    def test_vehicle_change_gap_and_invalid_camera_reset_derivative(self):
        pose=GTAPose()
        pose.update(telemetry(),True,1.)
        pose.update(telemetry(sequence=2,tick_ms=1050),True,1.05)
        pose.update(telemetry(vehicle=2,sequence=3,tick_ms=1100,vy=30),True,1.1)
        self.assertFalse(pose.message(1.1,True).valid)
        pose.update(telemetry(vehicle=2,sequence=4,tick_ms=1400),True,1.4)
        self.assertFalse(pose.message(1.4,True).valid)
        pose.update(None,False,1.5)
        self.assertFalse(pose.message(1.5,True).livePose.inputsOK)

    def test_nonfinite_motion_rejected(self):
        with self.assertRaises(ValueError): camera_motion(telemetry(vx=float('nan')))

if __name__ == '__main__': unittest.main()
