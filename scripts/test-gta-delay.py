"""Exercise the genuine lag estimator with the staged simulation-only patch."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from cereal import car
from gta_delay_patch import patch_gta_delay

source = Path('/data/openpilot/selfdrive/locationd/lagd.py').read_text()
candidate = patch_gta_delay(source)
namespace = {'__name__': 'candidate_lagd'}
exec(compile(candidate, 'candidate-lagd.py', 'exec'), namespace)
Estimator = namespace['LateralLagEstimator']


class DelayTest(unittest.TestCase):
    def estimator(self, brand, delay):
        e = Estimator(car.CarParams(brand=brand, steerActuatorDelay=delay), .01)
        e.frogpilot_toggles = SimpleNamespace(use_custom_steerActuatorDelay=False)
        return e

    def test_gta_prior_is_not_doubled_by_real_car_fallback(self):
        e = self.estimator('gta', .15)
        self.assertAlmostEqual(e.initial_lag, .15)
        self.assertAlmostEqual(e.get_msg(True).liveDelay.lateralDelay, .15)

    def test_other_cars_retain_upstream_prior(self):
        e = self.estimator('honda', .8)
        self.assertAlmostEqual(e.initial_lag, 1.)
        self.assertAlmostEqual(e.get_msg(True).liveDelay.lateralDelay, 1.)

    def test_estimated_delay_still_takes_over(self):
        e = self.estimator('gta', .15)
        e.block_avg.valid_blocks = e.min_valid_block_count
        e.block_avg.get = lambda: (.19, .01, .19, .01)
        m = e.get_msg(True).liveDelay
        self.assertEqual(str(m.status), 'estimated')
        self.assertAlmostEqual(m.lateralDelay, .19)

    def test_custom_ui_override_is_preserved(self):
        e = self.estimator('gta', .15)
        e.frogpilot_toggles = SimpleNamespace(use_custom_steerActuatorDelay=True, steerActuatorDelay=.22)
        self.assertAlmostEqual(e.get_msg(True).liveDelay.lateralDelay, .22)

    def test_patch_is_idempotent_and_rejects_unknown_source(self):
        self.assertEqual(patch_gta_delay(candidate), candidate)
        with self.assertRaises(RuntimeError): patch_gta_delay('different source')


if __name__ == '__main__':
    unittest.main()
