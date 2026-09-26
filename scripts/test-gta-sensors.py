"""Exercise real cereal sensor messages and locationd's input-fault counting."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'bridge'))
from gta_sensors import GTASensors
from cereal.services import SERVICE_LIST
from openpilot.selfdrive.locationd.locationd import INPUT_INVALID_LIMIT


class SensorsTests(unittest.TestCase):
    def test_one_pair_per_100hz_bridge_update(self):
        recorded=[]
        sensors=GTASensors.__new__(GTASensors)
        sensors.pm=SimpleNamespace(send=lambda service,msg:recorded.append((service,msg)))
        vector=lambda x,y,z:SimpleNamespace(x=x,y=y,z=z)
        state=SimpleNamespace(valid=True,imu=SimpleNamespace(
            accelerometer=vector(9.81,0.,0.),gyroscope=vector(.2,.1,-.3)))
        for _ in range(100):
            sensors.send_imu_message(state)
        self.assertEqual(Counter(s for s,m in recorded),{'accelerometer':100,'gyroscope':100})
        for service,msg in recorded:
            sensor=getattr(msg,service)
            self.assertTrue(msg.valid)
            self.assertEqual(sensor.timestamp,msg.logMonoTime)
        self.assertAlmostEqual(recorded[1][1].gyroscope.gyroUncalibrated.v[0],.2,places=6)
        # Stale game state must not be stamped as a valid sensor observation.
        state.valid=False
        sensors.send_imu_message(state)
        self.assertFalse(recorded[-1][1].valid)
        self.assertFalse(recorded[-2][1].valid)

    def test_short_glitch_not_amplified_past_real_locationd_threshold(self):
        threshold=round(INPUT_INVALID_LIMIT*SERVICE_LIST['gyroscope'].frequency/20)-.5
        # The captured disagreement occupied nine 100 Hz updates. Repeating
        # each one five times trips a threshold intended for ~104 Hz hardware.
        self.assertGreater(9*5,threshold)
        self.assertLess(9,threshold)


if __name__=='__main__':
    unittest.main()
