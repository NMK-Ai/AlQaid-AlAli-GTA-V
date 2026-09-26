#pragma once
#include <cstdint>

// Engagement belongs to the driver; temporary axis overrides must not clear it.
struct DrivingState {
  bool master = false, cruise = false, long_was_applied = false;
  uint64_t engaged_at_ms = 0;

  void off() { master = cruise = long_was_applied = false; }
  void cancel() { cruise = long_was_applied = false; }
  void toggle_master() { master = !master; cancel(); }
  void set(uint64_t now) { master = cruise = true; long_was_applied = false; engaged_at_ms = now; }

  void update(uint64_t now, unsigned mode, bool available, bool cancel_pressed,
              bool brake_pressed, bool all_off) {
    if (!available || all_off) { off(); return; }
    // Mode bit 2 reports enabled, including override/pause states with no
    // longitudinal output. Give a new engagement time to reach selfdrived.
    if (cancel_pressed || brake_pressed ||
        (cruise && !(mode & 4) && (long_was_applied || now-engaged_at_ms > 3000))) cancel();
  }
  bool lateral(unsigned mode, bool steering_override) const {
    return master && (mode & 1) && !steering_override;
  }
  bool longitudinal(unsigned mode, bool pedal_override) const {
    return master && cruise && (mode & 2) && !pedal_override;
  }
};
