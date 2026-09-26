"""Krieger curvature conversion and physical road-wheel range."""
import math

# Two independent stock-Krieger routes estimated K=0.0110 and 0.0161 s^2/m
# from tan(delta)=(wheelbase+K*v^2)*yaw/v. Use their midpoint as the initial
# feedforward calibration. Do not extrapolate its v^2 term beyond observed
# speed coverage. New route 14 provides 80 steady samples at 30-40 m/s with
# K=0.0155; retain the existing coefficient and extend its previous 25 m/s
# coverage. Above 40 m/s the observed fit is poor and remains uncalibrated.
# This bounds compensation, not vehicle speed or wheel range.
KRIEGER_UNDERSTEER = .0135
KRIEGER_CALIBRATED_SPEED = 40.0


def steering_length(wheelbase, speed):
    if not all(math.isfinite(x) for x in (wheelbase, speed)) or not 1. < wheelbase < 10.:
        raise ValueError('Invalid GTA speed/geometry')
    return wheelbase + KRIEGER_UNDERSTEER * min(abs(speed), KRIEGER_CALIBRATED_SPEED)**2


def road_wheel_angle(curvature, wheelbase, speed=0.):
    """Model curvature is +right; road-wheel degrees and GTA yaw are +left."""
    if not math.isfinite(curvature):
        raise ValueError('Invalid GTA curvature/geometry')
    return math.degrees(math.atan(-curvature * steering_length(wheelbase, speed)))


def road_curvature(angle, wheelbase, speed=0.):
    """Inverse of the same calibrated model used for angle requests."""
    if not math.isfinite(angle) or abs(angle) >= 90:
        raise ValueError('Invalid GTA wheel angle')
    return -math.tan(math.radians(angle)) / steering_length(wheelbase, speed)


def shape_curvature(speed, requested, wheelbase, max_wheel_angle):
    """Restrict demand only to the installed car's actual steering lock.

    The native angle servo already handles input slew and measured feedback.
    An additional acceleration/jerk limiter here delayed and clipped the model
    request, then falsely counted that shaping as EPS saturation. Tire grip is
    not inferred from a handling.meta coefficient or imposed as an OEM limit.
    """
    if not math.isfinite(requested) or not math.isfinite(max_wheel_angle) or not 0 < max_wheel_angle < 90:
        raise ValueError('Invalid GTA steering request or lock')
    maximum = math.tan(math.radians(max_wheel_angle)) / steering_length(wheelbase, speed)
    result = max(-maximum, min(maximum, requested))
    return result, abs(result-requested) > 1e-9


class TurnRateController:
    """Outer turn-response feedback around the native measured-angle servo.

    A matching wheel angle alone does not establish matching turn radius.
    Feedforward retains the identified Krieger geometry; measured yaw corrects
    residual tire/bank/gain errors. Curvature and correction are +right.
    """
    def __init__(self, wheelbase, dt, max_wheel_angle=40.):
        self.wheelbase = wheelbase
        self.dt = dt
        self.max_wheel_angle = max_wheel_angle
        self.kp = .1
        self.ki = .35
        self.reset()

    def reset(self):
        self.integral = 0.
        self.measured_curvature = None
        self.correction = 0.
        self.previous_desired = 0.

    def update(self, desired, speed, yaw_rate, active=True, override=False):
        feedforward = road_wheel_angle(desired, self.wheelbase, speed)
        if not active or override or speed < 3. or not math.isfinite(yaw_rate):
            self.reset()
            return feedforward
        # GTA's entity world-Z yaw is +left. Never infer achieved curvature
        # from the same approximate wheel model used to request steering.
        measured = -yaw_rate/speed
        if self.measured_curvature is None:
            self.measured_curvature = measured
        else:
            alpha = self.dt/(.1+self.dt)
            self.measured_curvature += alpha*(measured-self.measured_curvature)
        maximum = math.tan(math.radians(self.max_wheel_angle))/steering_length(self.wheelbase, speed)
        # The learned correction represents turn gain, not a permanent wheel
        # offset. Scale it with the requested curvature so a left-turn trim
        # cannot keep steering left after an unwind or direction reversal.
        # Near straight ahead only proportional feedback is used; avoid
        # amplifying a noisy curvature ratio around zero.
        if abs(self.previous_desired) > .0001:
            self.integral *= desired/self.previous_desired
        else:
            self.integral = 0.
        self.integral = max(-maximum, min(maximum, self.integral))
        self.previous_desired = desired
        error = desired-self.measured_curvature
        proposed = self.integral+self.ki*error*self.dt if abs(desired) > .0001 else 0.
        command = desired+self.kp*error+proposed
        # Conditional integration at physical wheel lock, including unwinding
        # out of saturation. Overrides/inactivity reset before re-engagement.
        if abs(command) <= maximum or command*error < 0:
            self.integral = max(-maximum, min(maximum, proposed))
        self.correction = self.kp*error+self.integral
        command = max(-maximum, min(maximum, desired+self.correction))
        return road_wheel_angle(command, self.wheelbase, speed)
