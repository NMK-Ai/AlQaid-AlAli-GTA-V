#include "longitudinal_actuator.h"
#include <cstdlib>
#include <iostream>

static void check(bool ok, const char* message) {
  if (!ok) { std::cerr << message << '\n'; std::exit(1); }
}

int main() {
  // Recorded failed cleanup crossed zero and accelerated backward to -9.65
  // m/s while brake remained 1. These samples are useful for fault regression,
  // but the collision-contaminated run must not calibrate response gains.
  for (float speed : {7.012f, 2.f, 1.01f}) {
    const auto p = longitudinal_output(true, speed, 0, .4f);
    check(p.throttle == 0 && p.brake == .4f && p.hold == 0,
          "moving braking must preserve requested pressure");
  }
  for (float speed : {1.f, .4f, .01f, 0.f, -.019f, -.301f, -9.65f}) {
    const auto p = longitudinal_output(true, speed, 0, 1);
    check(p.throttle == 0 && p.brake == 0 && p.hold == 1,
          "stopping/reverse samples must not inject the reverse-capable pedal");
  }
  for (float speed : {0.f, 15.f}) {
    const auto p = longitudinal_output(true, speed, .35f, 0);
    check(p.throttle == .35f && p.brake == 0 && p.hold == 0,
          "positive acceleration releases hold immediately");
    const auto coast = longitudinal_output(true, speed, 0, 0);
    check(coast.throttle == 0 && coast.brake == 0 && coast.hold == 0,
          "zero pedals remain coasting");
  }
  const auto off = longitudinal_output(false, 0, .5f, 1);
  check(off.throttle == 0 && off.brake == 0 && off.hold == 0,
        "inactive or manual override must release all injected inputs");
  const auto conflict = longitudinal_output(true, 10, .5f, .2f);
  check(conflict.throttle == 0 && conflict.brake == .2f,
        "braking must take precedence over a simultaneous throttle request");
  std::cout << "Brake-to-reverse, hold release and override regressions passed\n";
}
