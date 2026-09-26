import math
import unittest
from collections import deque

from gta_lateral import TurnRateController, road_wheel_angle, road_curvature


class TurnRateTests(unittest.TestCase):
    def test_recorded_inside_wall_unwind(self):
        # Airport frame 9508: desired -.0065, actual yaw .1079 at 10.2589 m/s.
        controller = TurnRateController(2.5986464, .01)
        original = road_wheel_angle(-.0065, 2.5986464, 10.2589)
        corrected = controller.update(-.0065, 10.2589, .1079)
        self.assertGreater(corrected, 0.)
        self.assertLess(corrected, original)
        # Mirror geometry must correct equally in the opposite direction.
        mirror = TurnRateController(2.5986464, .01)
        self.assertAlmostEqual(mirror.update(.0065, 10.2589, -.1079), -corrected)

    def test_matching_turn_keeps_exact_feedforward(self):
        for speed in (5., 15., 35.):
            for desired in (-.01, .01):
                controller = TurnRateController(2.5986464, .01)
                for _ in range(100):
                    result = controller.update(desired, speed, -desired*speed)
                self.assertAlmostEqual(result, road_wheel_angle(desired, 2.5986464, speed))

    def test_override_low_speed_invalid_yaw_and_inactive_reset(self):
        for changes in ({'override':True}, {'active':False}, {'speed':0.}, {'yaw_rate':math.nan}):
            c = TurnRateController(2.5986464, .01)
            for _ in range(100): c.update(-.01, 15., .3)
            self.assertNotEqual(c.integral, 0.)
            kwargs = dict(desired=-.01, speed=15., yaw_rate=.3)
            kwargs.update(changes)
            result = c.update(**kwargs)
            self.assertEqual(c.integral, 0.)
            self.assertIsNone(c.measured_curvature)
            self.assertAlmostEqual(result, road_wheel_angle(-.01, 2.5986464, kwargs['speed']))

    def test_delayed_uncertain_turn_response_converges_both_directions(self):
        worst_steady = 0.
        for speed in (5., 15., 25., 35.):
            for actual_k in (.008, .011, .016, .022):
                for delay in (.05, .15, .3):
                    for target in (-.01, .01):
                        c=TurnRateController(2.5986464,.01)
                        q=deque([0.]*round(delay/.01));angle=yaw=0.
                        for _ in range(2000):
                            command=c.update(target,speed,yaw)
                            self.assertLessEqual(abs(command),40.+1e-9)
                            q.append(command);delayed=q.popleft()
                            angle+=(1-math.exp(-.01/.08))*(delayed-angle)
                            wanted_yaw=math.tan(math.radians(angle))*speed/(2.5986464+actual_k*speed**2)
                            yaw+=(1-math.exp(-.01/.12))*(wanted_yaw-yaw)
                        error=abs(-yaw/speed-target)
                        worst_steady=max(worst_steady,error)
                        self.assertLess(error,.00005,(speed,actual_k,delay,target,error))
        print('Worst steady curvature error across 96 delayed plants:',worst_steady)

    def test_physical_lock_does_not_wind_up_and_recovers(self):
        c=TurnRateController(2.5986464,.01)
        for _ in range(1000):
            angle=c.update(-1.,25.,0.)
            self.assertLessEqual(abs(angle),40.+1e-9)
        self.assertEqual(c.integral,0.)
        self.assertAlmostEqual(c.update(0.,25.,0.),0.)

    def test_speed_ramps_reversals_and_unwind_remain_bounded(self):
        # Compare the candidate against identical delayed tire plants, through
        # acceleration, turn reversal, and a sustained turn followed by unwind.
        # This is a stability regression, not a substitute for GTA road data.
        worst_overshoot = 0.
        for actual_k in (.008,.0135,.022):
            for delay in (.05,.15,.3):
                c=TurnRateController(2.5986464,.01)
                q=deque([0.]*round(delay/.01)); angle=yaw=0.
                for i in range(6000):
                    t=i*.01
                    speed=5.+30.*min(t/20.,1.) if t<30 else max(5.,35.-2.*(t-30.))
                    desired=-.008 if t<15 else (.008 if t<30 else (0. if t<40 else -.008))
                    command=c.update(desired,speed,yaw)
                    self.assertLessEqual(abs(command),40.)
                    q.append(command); angle+=(1-math.exp(-.01/.08))*(q.popleft()-angle)
                    wanted=math.tan(math.radians(angle))*speed/(2.5986464+actual_k*speed**2)
                    yaw+=(1-math.exp(-.01/.12))*(wanted-yaw)
                    achieved=-yaw/speed
                    worst_overshoot=max(worst_overshoot,abs(achieved))
                    self.assertLess(abs(achieved),.014,(actual_k,delay,t))
                    if 39<t<40 or 59<t<60:
                        self.assertLess(abs(achieved-desired),.0004,(actual_k,delay,t))
        print('Worst curvature through speed ramps/reversals:',worst_overshoot)


if __name__ == '__main__':
    unittest.main()
