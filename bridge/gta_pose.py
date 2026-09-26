"""GTA camera motion published through openpilot's genuine livePose schema.

This is simulator ground truth, not a locationd estimate or a validity bypass.
GTA native rotation order 2 (Z-X-Y) becomes NED yaw-pitch-roll after swapping
world X/Y and reversing Z. The attached camera shares the vehicle's rotation.
"""
import math
import os
import numpy as np
from cereal import messaging
from openpilot.common.transformations.orientation import rot_from_euler

CAMERA_OFFSET_DEVICE = np.array([1.1, 0., -.85])  # forward, right, down; native mount
GTA_TO_NED = np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]])


def camera_motion(t):
    orientation = np.radians([t['roll'], t['pitch'], -t['heading']])
    device_from_world = rot_from_euler(orientation).T @ GTA_TO_NED
    angular = device_from_world @ np.array([t['wx'], t['wy'], t['wz']])
    velocity = device_from_world @ np.array([t['vx'], t['vy'], t['vz']])
    # Velocity at the mounted camera, rather than at the vehicle origin.
    velocity += np.cross(angular, CAMERA_OFFSET_DEVICE)
    if not all(np.isfinite(v).all() for v in (orientation, angular, velocity)):
        raise ValueError('Nonfinite GTA camera motion')
    return orientation, velocity, angular


class GTAPose:
    def __init__(self):
        if os.getenv('SIMULATION') != '1' or os.getenv('GTA_SIMULATION') != '1':
            raise RuntimeError('GTA ground-truth pose requires both simulator flags')
        self.previous = None
        self.last_received = -math.inf
        self.last_sequence = None
        self.orientation = self.velocity = self.angular = np.zeros(3)
        self.acceleration = np.zeros(3)
        self.ready = False

    def update(self, telemetry, valid, now):
        if not valid or not telemetry:
            self.previous = None
            self.last_sequence = None
            self.ready = False
            return
        t = telemetry
        identity = (t['vehicle'], t['sequence'])
        if identity == self.last_sequence:
            return
        orientation, velocity, angular = camera_motion(t)
        tick = t['tick_ms']
        previous = self.previous
        dt = (tick-previous[1])/1000 if previous else 0
        self.ready = bool(previous and previous[0] == t['vehicle'] and .005 <= dt <= .2)
        # livePose.accelerationDevice is d(velocityDevice)/dt. The upstream
        # pose model adds angularVelocity x velocity for accelerometer physics.
        self.acceleration = (velocity-previous[2])/dt if self.ready else np.zeros(3)
        self.orientation, self.velocity, self.angular = orientation, velocity, angular
        self.previous = (t['vehicle'], tick, velocity)
        self.last_received, self.last_sequence = now, identity

    def message(self, now, valid):
        fresh = bool(valid and self.ready and 0 <= now-self.last_received < .2)
        msg = messaging.new_message('livePose', valid=fresh)
        pose = msg.livePose
        # These flags describe the replacement motion source's validity. Vision
        # inference, calibration, camera freshness and control checks stay real.
        pose.inputsOK = pose.sensorsOK = pose.posenetOK = fresh
        for name, values, std in (
            ('orientationNED', self.orientation, .005),
            ('velocityDevice', self.velocity, .1),
            ('accelerationDevice', self.acceleration, .5),
            ('angularVelocityDevice', self.angular, .01),
        ):
            field = getattr(pose, name)
            field.x, field.y, field.z = map(float, values)
            # Conservative nonzero discretization uncertainties, not claimed
            # learned sensor covariance. Required by downstream pose consumers.
            field.xStd = field.yStd = field.zStd = std
            field.valid = fresh
        return msg
