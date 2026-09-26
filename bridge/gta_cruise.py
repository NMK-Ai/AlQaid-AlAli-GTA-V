"""Virtual cruise switch semantics with FrogPilot's configured tap/hold steps."""
import math


class GTACruise:
    def __init__(self):
        self.speed = 13.4112
        self.was_set = False
        self.was_cruise = False
        self.direction = 0
        self.pressed_at = self.next_repeat = 0.
        self.shift = False

    def step(self, direction, long_press, toggles):
        unit = 1/3.6 if toggles.is_metric else .44704
        interval = toggles.cruise_increase_long if long_press else toggles.cruise_increase
        if not long_press and direction > 0 and toggles.reverse_cruise_increase:
            interval = 5
        delta = max(1., interval) * unit
        if interval % 5 == 0 and not math.isclose(self.speed/delta, round(self.speed/delta), abs_tol=1e-5):
            self.speed = (math.ceil if direction > 0 else math.floor)(self.speed/delta)*delta
        else:
            self.speed += direction*delta
        if long_press and toggles.set_speed_offset > 0:
            # FrogPilot stores this offset in kph, regardless of display units.
            self.speed += toggles.set_speed_offset/3.6
            if direction < 0:
                self.speed -= delta
        self.speed = min(150., max(1., self.speed))

    def update(self, t, cruise, now, toggles, speed_limit=0.):
        setting = bool(t.get('set_pressed', False))
        shift = bool(t.get('shift_pressed', False))
        if (setting and not self.was_set) or (cruise and not self.was_cruise and not self.was_set):
            if not shift:
                self.speed = max(1., speed_limit if toggles.set_speed_limit and speed_limit > 0 else t.get('speed', 0.))
        self.was_set, self.was_cruise = setting, cruise
        flags = t.get('flags', 0)
        direction = int(bool(flags & 4096))-int(bool(flags & 8192))
        if direction != self.direction:
            if self.direction and now-self.pressed_at < .5:
                self.step(self.direction, self.shift, toggles)
            self.direction = direction
            self.pressed_at, self.next_repeat, self.shift = now, now+.5, shift
        elif direction and now >= self.next_repeat:
            self.step(direction, True, toggles)
            self.next_repeat = now+.5
        return self.speed
