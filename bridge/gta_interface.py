"""Local GTA vehicle model: no OEM CAN controller or EPS torque/rate limits."""
import math
import os
import json
from pathlib import Path

from cereal import car, custom
from opendbc.car import scale_rot_inertia, scale_tire_stiffness
from opendbc.car.interfaces import CarInterfaceBase

PROJECT_ROOT = Path(os.environ['GTA_PROJECT_ROOT']) if os.getenv('GTA_PROJECT_ROOT') else Path(__file__).resolve().parents[1]
STOCK_HANDLING = json.loads((PROJECT_ROOT/'config/krieger-handling.json').read_text())['handling']
MAX_WHEEL_ANGLE_DEG = float(STOCK_HANDLING['fSteeringLock'])  # Actual stock-car lock; not input gain.
ACCEL_AT_FULL_THROTTLE = 4.0
DECEL_AT_FULL_BRAKE = 8.0
# Retain the working throttle launch compensation. Brake input is independent:
# recorded clear-road windows give ~18-23 m/s^2 per unit raw brake, and show
# severe over-braking with the old 25% floor. This is a provisional feedforward
# coefficient, not a measured full-pedal stopping limit or a planner limit.
BRAKE_ACCEL_PER_UNIT = 20.0
PEDAL_INPUT_DEADZONE = .25


class CarInterface(CarInterfaceBase):
    def __init__(self, CP, FPCP):
        self.CP, self.FPCP = CP, FPCP

    @staticmethod
    def _get_params(*args):
        raise NotImplementedError('Use the GTA simulation profile')

    @classmethod
    def get_params(cls, *args, **kwargs):
        if os.getenv('GTA_SIMULATION') != '1' or os.getenv('SIMULATION') != '1':
            raise RuntimeError('The GTA profile is only available in the local game simulator')
        cp = car.CarParams.new_message()
        cp.carFingerprint, cp.brand = 'GTA_V', 'gta'
        cp.carVin = 'GTA_SIMULATOR_ONLY'
        cp.passive = cp.dashcamOnly = False
        cp.openpilotLongitudinalControl = True
        cp.pcmCruise = True  # F8 is the simulated cruise-master switch.
        cp.radarUnavailable = False  # Native GTA forward vehicle radar -> liveTracks -> radard.
        cp.radarDelay = .1  # Nominal async probe, 20 Hz packet and message scheduling.
        cp.enableBsm = True
        cp.autoResumeSng = True
        cp.minEnableSpeed = -1.
        cp.minSteerSpeed = 0.
        cp.steerControlType = 'angle'
        cp.steerRatio = cp.wheelSpeedFactor = cp.tireStiffnessFactor = 1.
        # Mass comes from the installed Krieger handling entry. Its wheelbase
        # comes from the spawned model's actual wheel positions.
        cp.mass, cp.wheelbase = float(STOCK_HANDLING['fMass']), 2.598646402359009
        calibration = PROJECT_ROOT/'runtime/krieger-calibration.json'
        if calibration.exists():
            measured = json.loads(calibration.read_text())
            if measured.get('model_name') != 'krieger' or not 2. < measured['wheelbase_m'] < 4.:
                raise ValueError('Invalid stock Krieger calibration')
            cp.wheelbase = float(measured['wheelbase_m'])
        cp.centerToFront = cp.wheelbase * .5
        cp.rotationalInertia = scale_rot_inertia(cp.mass, cp.wheelbase)
        cp.tireStiffnessFront, cp.tireStiffnessRear = scale_tire_stiffness(cp.mass, cp.wheelbase, cp.centerToFront, 1.)
        # Route 21 and 24 clean turning windows show ~0.11-0.17 s command-to-
        # measured-motion lag. lagd must not add its real-car 0.2 s fallback
        # to this direct game-motion prior. Learned delay still takes over.
        cp.steerActuatorDelay = .15
        cp.longitudinalActuatorDelay = .1
        cp.steerLimitTimer = 1.
        cp.maxLateralAccel = 10.
        # GTA pedal commands have substantially more lag/gain than an OEM
        # acceleration actuator. High acceleration feedback caused alternating
        # gas/brake corrections; use a slower correcting loop over feedforward.
        cp.longitudinalTuning.kpBP, cp.longitudinalTuning.kpV = [0., 20.], [.18, .12]
        cp.longitudinalTuning.kiBP, cp.longitudinalTuning.kiV = [0.], [.08]
        cp.vEgoStopping = cp.vEgoStarting = .2
        cp.stopAccel, cp.stoppingDecelRate = -2., .8
        cp.safetyConfigs = [{'safetyModel': 'allOutput', 'safetyParam': 0}]
        return cp

    @staticmethod
    def get_frogpilot_params(*args, **kwargs):
        fp = custom.FrogPilotCarParams.new_message()
        fp.safetyConfigs = [{'safetyParam': 0}]
        return fp

    @staticmethod
    def get_pid_accel_limits(CP, current_speed, cruise_speed):
        return -DECEL_AT_FULL_BRAKE, ACCEL_AT_FULL_THROTTLE


def actuators_to_game(angle_deg, accel, lateral, longitudinal, *, speed=None, stopping=False):
    """Encode separate throttle/brake responses and preserve requested creep."""
    if not math.isfinite(angle_deg) or not math.isfinite(accel):
        raise ValueError('Nonfinite GTA actuator request')
    steer = max(-MAX_WHEEL_ANGLE_DEG, min(MAX_WHEEL_ANGLE_DEG, angle_deg)) if lateral else 0.
    throttle = encode_pedal(accel / ACCEL_AT_FULL_THROTTLE) if longitudinal else 0.
    brake = max(0., min(1., -accel / BRAKE_ACCEL_PER_UNIT)) if longitudinal else 0.
    # Installed native adapter uses full handbrake for any brake below 1 m/s
    # to avoid GTA's reverse-pedal behavior. Only permit that final-stop hold
    # when genuine openpilot longitudinal control actually requests a stop.
    if speed is not None:
        if not math.isfinite(speed):
            raise ValueError('Nonfinite vehicle speed')
        if 0. <= speed <= 1. and not stopping:
            brake = 0.
    return steer, throttle, brake


def encode_pedal(travel):
    """Throttle launch compensation; never apply this mapping to the brake."""
    if not math.isfinite(travel):
        raise ValueError('Nonfinite pedal request')
    if travel <= 0.:
        return 0.
    return PEDAL_INPUT_DEADZONE + (1. - PEDAL_INPUT_DEADZONE) * min(1., travel)
