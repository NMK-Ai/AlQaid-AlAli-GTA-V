"""Publish GTA vehicle state directly through FrogPilot's normal messaging API."""
import time
from cereal import car, custom, messaging
from openpilot.common.params import Params
from openpilot.frogpilot.common.frogpilot_variables import get_frogpilot_toggles, update_frogpilot_toggles
from openpilot.frogpilot.controls.frogpilot_card import FrogPilotCard
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from gta_interface import CarInterface
from gta_cruise import GTACruise


class GTAVehicle:
    def __init__(self):
        self.params = Params()
        self.cp = CarInterface.get_params()
        self.fp = CarInterface.get_frogpilot_params()
        self.pm = messaging.PubMaster(['carState', 'carParams', 'carOutput', 'frogpilotCarState',
                                      'frogpilotCarParams', 'pandaStates', 'liveTracks'])
        self.sm = messaging.SubMaster(['carControl', 'selfdriveState', 'frogpilotPlan',
                                      'frogpilotSelfdriveState', 'liveCalibration', 'frogpilotOnroadEvents'])
        self.last_params = self.last_panda = self.next_tracks = 0.
        self.radar_valid, self.radar_count = False, 0
        self.last_speed = 0.
        self.last_tick = 0
        self.accel = 0.
        self.last_armed = False
        self.previous_buttons = {}
        self.cruise_speed = 13.4112  # Initial user-adjustable 30 mph set speed.
        self.cruise = GTACruise()
        self.drive_mode = 0
        self.publish_params()
        update_frogpilot_toggles()
        self.frogpilot_card = FrogPilotCard(self.cp, self.fp)

    def publish_params(self):
        cp_bytes, fp_bytes = self.cp.to_bytes(), self.fp.to_bytes()
        self.cp.clear_write_flag()
        self.fp.clear_write_flag()
        if self.params.get('CarParams') is None or getattr(self, 'last_profile', None) != (cp_bytes, fp_bytes):
            self.params.put('CarParams', cp_bytes)
            self.params.put('FrogPilotCarParams', fp_bytes)
            self.params.put('CarParamsPersistent', cp_bytes)
            self.params.put('FrogPilotCarParamsPersistent', fp_bytes)
            self.last_profile = (cp_bytes, fp_bytes)
        # Params writes fsync. Rewriting four unchanged keys every second was
        # stalling the same thread that must publish carState at 100 Hz.
        for key, value in [('CarMake', 'GTA'), ('CarModel', 'GTA_V')]:
            if self.params.get(key) != value:
                self.params.put(key, value)
        for key in ['UbloxAvailable', 'ControlsReady']:
            if not self.params.get_bool(key):
                self.params.put_bool(key, True)
        for service, value in [('carParams', self.cp), ('frogpilotCarParams', self.fp)]:
            m = messaging.new_message(service, valid=True)
            setattr(m, service, value)
            self.pm.send(service, m)

    def send_panda_state(self, state):
        m = messaging.new_message('pandaStates', 1, valid=True)
        m.pandaStates[0] = {'ignitionLine': bool(state.ignition), 'pandaType': 'blackPanda',
                            'controlsAllowed': bool(state.valid), 'safetyModel': 'allOutput',
                            'safetyParam': 0, 'alternativeExperience': self.fp.alternativeExperience}
        self.pm.send('pandaStates', m)

    def update(self, state, t, radar):
        now = time.monotonic()
        self.sm.update(0)
        toggles = get_frogpilot_toggles(self.sm)
        if now-self.last_params >= 1.:
            self.fp.alternativeExperience = (ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL if toggles.always_on_lateral else 0)
            self.frogpilot_card.always_on_lateral_set = bool(toggles.always_on_lateral)
            self.publish_params()
            self.last_params = now
        if now-self.last_panda >= .1:
            self.send_panda_state(state)
            self.last_panda = now
        t = t or {}
        flags = t.get('flags', 0)
        master = bool(flags & 8) and state.valid
        armed = bool(flags & 2048) and master
        self.cruise_speed = self.cruise.update(t, armed, now, toggles, self.sm['frogpilotPlan'].slcSpeedLimit)
        speed = t.get('speed', 0.)
        tick = t.get('tick_ms', 0)
        if tick != self.last_tick:
            dt = (tick-self.last_tick) / 1000.
            if .005 < dt < .2:
                self.accel = .3 * (speed-self.last_speed)/dt + .7*self.accel
            self.last_tick, self.last_speed = tick, speed
        cs = car.CarState.new_message()
        cs.canValid = bool(state.valid)
        cs.canTimeout = not state.valid
        cs.vEgo = cs.vEgoRaw = cs.vEgoCluster = speed
        cs.aEgo = self.accel
        cs.standstill = speed < .05
        mode_pressed = bool(t.get('drive_mode_key', False))
        if mode_pressed and not self.previous_buttons.get('drive_mode', False):
            self.drive_mode = (self.drive_mode+1) % 3
        self.previous_buttons['drive_mode'] = mode_pressed
        cs.gearShifter = 'drive'
        cs.gasPressed = t.get('gas', 0.) > .08
        cs.brakePressed = t.get('brake', 0.) > .08
        cs.brake = t.get('brake', 0.)
        # Actual steering-angle field sampled before the next native write.
        cs.steeringAngleDeg = t.get('wheel_angle_deg', 0.)
        cs.steerFaultTemporary = bool(state.valid) and not bool(flags & 67108864)
        nudge = t.get('nudge', 0.)
        cs.steeringPressed = bool(flags & 16) or bool(nudge)
        cs.steeringTorque = -2000.*nudge if nudge else (-2000.*t.get('steer_input', 0.) if flags & 16 else 0.)
        cs.leftBlinker, cs.rightBlinker = bool(flags & 32), bool(flags & 64)
        cs.leftBlindspot, cs.rightBlindspot = bool(flags & 16777216), bool(flags & 33554432)
        cs.yawRate = t.get('wz', 0.)
        cs.cruiseState.available = master
        cs.cruiseState.enabled = armed
        cs.cruiseState.speed = self.cruise_speed
        cs.vCruise = cs.vCruiseCluster = self.cruise_speed*3.6
        events = []
        if armed != self.last_armed:
            events.append({'type': 'setCruise' if armed else 'cancel', 'pressed': False})
        self.last_armed = armed
        for bit, name in [(4096, 'accelCruise'), (8192, 'decelCruise'), (16384, 'gapAdjustCruise'), (131072, 'lkas')]:
            pressed = bool(flags & bit)
            if pressed != self.previous_buttons.get(name, False):
                events.append({'type': name, 'pressed': pressed})
            self.previous_buttons[name] = pressed
        for bit, name in [(262144, 'experimental'), (524288, 'personality')]:
            pressed = bool(flags & bit)
            if pressed and not self.previous_buttons.get(name, False):
                if name == 'experimental':
                    self.frogpilot_card.handle_experimental_mode(self.sm, toggles)
                else:
                    value = int(self.params.get('LongitudinalPersonality', return_default=True))
                    self.params.put('LongitudinalPersonality', (value+1) % 3)
            self.previous_buttons[name] = pressed
        for bit, attribute in [(1048576, 'force_coast'), (2097152, 'pause_lateral'),
                               (4194304, 'pause_longitudinal'), (8388608, 'traffic_mode_enabled')]:
            pressed = bool(flags & bit)
            if pressed and not self.previous_buttons.get(attribute, False):
                setattr(self.frogpilot_card, attribute, not getattr(self.frogpilot_card, attribute))
            self.previous_buttons[attribute] = pressed
        cs.buttonEvents = events
        fp_state = custom.FrogPilotCarState.new_message()
        fp_state.ecoGear, fp_state.sportGear = self.drive_mode == 1, self.drive_mode == 2
        fp_state.distancePressed = bool(flags & 16384)
        fp_state = self.frogpilot_card.update(cs, fp_state, self.sm, toggles)
        self.last_state = fp_state
        for service, value in [('carState', cs), ('frogpilotCarState', fp_state)]:
            m = messaging.new_message(service, valid=bool(state.valid))
            setattr(m, service, value)
            self.pm.send(service, m)
        output = messaging.new_message('carOutput', valid=bool(state.valid))
        # Report only what the native adapter actually applied, not proposed output.
        if flags & 128:
            output.carOutput.actuatorsOutput.steeringAngleDeg = cs.steeringAngleDeg
            output.carOutput.actuatorsOutput.accel = self.accel
        self.pm.send('carOutput', output)
        if now >= self.next_tracks:
            tracks = radar.message(t, state.valid)
            self.radar_valid, self.radar_count = tracks.valid, len(tracks.liveTracks.points)
            self.pm.send('liveTracks', tracks)
            self.next_tracks = now+.05 if now-self.next_tracks > .05 else self.next_tracks+.05
