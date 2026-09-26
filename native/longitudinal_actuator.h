#pragma once

struct PedalOutput {
  float throttle = 0, brake = 0, hold = 0;
};

// GTA control 72 becomes reverse after stopping. An openpilot deceleration
// request must never become a request to drive backward. Use frame-scoped
// handbrake input for the final crawl/standstill; no persistent vehicle flags.
inline PedalOutput longitudinal_output(bool active, float forward_speed,
                                       float throttle, float brake) {
  if (!active) return {};
  if (brake > 0) {
    if (forward_speed <= 1.f) return {0, 0, 1};
    return {0, brake, 0};
  }
  return {throttle, 0, 0};
}
