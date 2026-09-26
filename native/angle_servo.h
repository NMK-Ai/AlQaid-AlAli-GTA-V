#pragma once
#include <algorithm>
#include <cmath>

// Angle feedback around GTA's frame-scoped steering input. Stationary input
// gain is not its moving gain. The provisional stock-Krieger curve comes from
// measured angle / applied bias, separately from the car's yaw/understeer fit.
struct AngleServo {
  float full_scale_degrees = 120.f, integral_gain = .005f, slew_per_second = 2.5f;
  float proportional_gain = .3f;
  float integral = 0, output = 0;
  float input_gain(float speed) const {
    constexpr float speeds[] = {0, 10, 20, 30, 40};
    constexpr float gains[] = {120, 140, 165, 200, 225};
    const float v = std::clamp(std::abs(speed), 0.f, 40.f);
    for (int i = 1; i < 5; ++i) {
      if (v <= speeds[i]) {
        const float f = (v-speeds[i-1])/(speeds[i]-speeds[i-1]);
        return full_scale_degrees/120.f * (gains[i-1]+f*(gains[i]-gains[i-1]));
      }
    }
    return full_scale_degrees/120.f * gains[4];
  }
  void reset() { integral = output = 0; }
  float update(float desired, float measured, float dt, float speed = 0) {
    if (!std::isfinite(desired) || !std::isfinite(measured) || !std::isfinite(dt) ||
        !std::isfinite(speed) || !std::isfinite(full_scale_degrees) ||
        !std::isfinite(integral_gain) || !std::isfinite(proportional_gain) ||
        dt <= 0 || dt > .2f || full_scale_degrees < 10) { reset(); return 0; }
    float error = desired-measured;
    float proposed = integral + error*integral_gain*dt;
    const float gain = input_gain(speed);
    float feedforward = desired/gain;
    // Modest immediate feedback handles gain uncertainty; integral retains
    // zero steady-state error. Scale P by plant gain to avoid higher-speed
    // feedback amplification. No finite-difference derivative of noisy angles.
    float correction = proportional_gain*error/gain;
    // Conditional integration avoids windup at the game input's physical ends.
    if (std::abs(feedforward+correction+proposed) <= 1.f || (output >= 1 && error < 0) || (output <= -1 && error > 0))
      integral = std::clamp(proposed, -1.f, 1.f);
    float target = std::clamp(feedforward+correction+integral, -1.f, 1.f);
    output = std::clamp(target, output-slew_per_second*dt, output+slew_per_second*dt);
    return output;
  }
};
