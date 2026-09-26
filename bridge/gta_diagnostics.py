"""Keep bounded evidence when native cruise/master switches off."""
from collections import deque


class DisengagementTrace:
    def __init__(self):
        self.states = deque(maxlen=90)
        self.commands = deque(maxlen=200)
        self.previous = None

    def command(self, packet, tick):
        self.commands.append({**packet, 'sent_tick_ms': tick})

    def telemetry(self, sample, keys=()):
        flags, tick = sample['flags'], sample['tick_ms']
        current = {'tick_ms':tick, 'flags':flags, 'speed':sample['speed'],
                   'vehicle':sample['vehicle'], 'brake':sample['brake'], 'keys':list(keys)}
        # A command newer than the native sample cannot explain that sample.
        commands = [c for c in list(self.commands) if c['sent_tick_ms'] <= tick
                    and c['vehicle'] == sample['vehicle']]
        command = commands[-1] if commands else None
        if command:
            current['command_age_ms'] = tick-command['sent_tick_ms']
            current['camera_age_ms'] = tick-command['capture_tick_ms']
            current['command_mode'] = command['mode']
        self.states.append(current)
        previous, self.previous = self.previous, flags
        if previous is None or not ((previous & 8 and not flags & 8) or (previous & 2048 and not flags & 2048)):
            return None
        reason, evidence = 'Native driving switched off; examining timing', 'unclassified'
        if not flags & 1:
            reason, evidence = 'Vehicle or driver unavailable', 'native flag'
        elif flags & 2:
            reason, evidence = 'Game paused or loading', 'native flag'
        elif not flags & 4:
            reason, evidence = 'Forward camera switched off', 'native flag'
        elif keys:
            reason, evidence = 'Driver pressed '+', '.join(keys), 'Windows key state'
        elif sample['brake'] > .08:
            reason, evidence = 'Brake cancelled cruise', 'native pedal reading'
        elif command and current['camera_age_ms'] > 250:
            reason, evidence = 'Camera/model frame became stale', 'Windows command timing; inferred'
        elif command and current['command_age_ms'] > 200:
            reason, evidence = 'Control connection became stale', 'Windows command timing; inferred'
        elif flags & 8 and command and not command['mode'] & 4:
            reason, evidence = 'FrogPilot disengaged speed control', 'controller acknowledgement'
            if command.get('alert'):
                reason += ': '+command['alert']
        return {'tick_ms':tick, 'reason':reason, 'evidence':evidence,
                'prior_flags':previous, 'state':current, 'history':list(self.states),
                'recent_commands':commands[-30:]}
