"""Exercise the actual FrogPilot state machine and AOL logic without publishing."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'bridge'))
os.environ['GTA_SIMULATION'] = os.environ['SIMULATION'] = '1'
from cereal import car, custom, log
from gta_interface import CarInterface
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.selfdrive.selfdrived.state import StateMachine, State
from openpilot.frogpilot.controls.frogpilot_card import FrogPilotCard


class OverrideTests(unittest.TestCase):
    def test_manual_overrides_preserve_enabled_and_resume(self):
        for event in [log.OnroadEvent.EventName.gasPressedOverride, log.OnroadEvent.EventName.steerOverride]:
            machine = StateMachine()
            machine.state = State.enabled
            events = Events()
            events.add(event)
            for _ in range(500):
                self.assertEqual(machine.update(events, Events(), True), (True, True))
                self.assertEqual(machine.state, State.overriding)
            self.assertEqual(machine.update(Events(), Events(), True), (True, True))
            self.assertEqual(machine.state, State.enabled)

    def test_brake_disables_cruise_but_aol_remains(self):
        machine = StateMachine()
        machine.state = State.enabled
        events = Events()
        events.add(log.OnroadEvent.EventName.pedalPressed)
        self.assertEqual(machine.update(events, Events(), True), (False, False))

        with patch('openpilot.frogpilot.controls.frogpilot_card.Params'), \
             patch('openpilot.frogpilot.controls.frogpilot_card.is_FrogsGoMoo', return_value=False):
            controller = FrogPilotCard(CarInterface.get_params(), CarInterface.get_frogpilot_params())
        controller.always_on_lateral_set = True
        controller.error_log = Path('/tmp/openpilot-gta-test-nonexistent-error-log')
        cs = car.CarState.new_message()
        cs.vEgo = 15.
        cs.gearShifter = 'drive'
        cs.brakePressed = True
        cs.cruiseState.available = True
        cs.cruiseState.enabled = False
        toggles = SimpleNamespace(always_on_lateral_main=True, always_on_lateral_lkas=False,
                                 always_on_lateral_pause_speed=0.)
        class Snapshot(dict):
            updated = {'frogpilotPlan': True}
        sm = Snapshot(frogpilotPlan=SimpleNamespace(lateralCheck=True),
                      liveCalibration=SimpleNamespace(calPerc=100),
                      selfdriveState=SimpleNamespace(alertType='userDisable'),
                      frogpilotSelfdriveState=SimpleNamespace(alertType=''))
        fp = controller.update(cs, custom.FrogPilotCarState.new_message(), sm, toggles)
        self.assertTrue(fp.alwaysOnLateralEnabled)
        cs.cruiseState.available = False
        fp = controller.update(cs, custom.FrogPilotCarState.new_message(), sm, toggles)
        self.assertFalse(fp.alwaysOnLateralEnabled)


if __name__ == '__main__':
    unittest.main()
