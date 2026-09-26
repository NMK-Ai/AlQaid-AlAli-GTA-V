#include "driving_state.h"
#include <cstdlib>
#include <iostream>

static void check(bool ok, const char* message) {
  if (!ok) { std::cerr << message << '\n'; std::exit(1); }
}
int main() {
  DrivingState d;
  d.set(1000);
  d.update(1020, 0, true, false, false, false);
  check(d.cruise, "engagement must tolerate controller startup");
  d.update(1100, 7, true, false, false, false);
  check(d.lateral(7, false) && d.longitudinal(7, false), "both axes engage");
  d.long_was_applied = true;
  for (uint64_t t = 1200; t < 6500; t += 10) {
    d.update(t, 5, true, false, false, false);
    check(d.master && d.cruise && d.lateral(5, false) && !d.longitudinal(5, true),
          "sustained accelerator override must keep engagement and steering");
  }
  check(d.longitudinal(7, false), "releasing accelerator resumes speed control");
  d.update(6500, 7, true, false, false, false);
  check(d.master && d.cruise && !d.lateral(7, true) && d.longitudinal(7, false),
        "manual steering releases only steering");
  check(d.lateral(7, false), "releasing steering resumes it");
  d.update(6600, 7, true, false, true, false);
  check(d.master && !d.cruise && d.lateral(1, false) && !d.longitudinal(7, false),
        "brake cancels speed while AOL keeps steering");
  check(!d.lateral(0, false), "without AOL a disabled controller cannot steer");
  d.set(6700);
  d.update(6800, 7, true, true, false, false);
  check(d.master && !d.cruise && d.lateral(1, false), "Cancel preserves AOL master");
  d.set(6900);
  d.update(7000, 7, true, false, false, true);
  check(!d.master && !d.cruise && !d.lateral(7, false), "All Off releases both axes");
  d.set(7100);
  d.update(7200, 7, false, false, false, false);
  check(!d.master && !d.longitudinal(7, false), "stale data releases both axes");
  d.set(7300); d.long_was_applied = true;
  d.update(7400, 1, true, false, false, false);
  check(d.master && !d.cruise, "controller disengagement cancels cruise");
  d.set(7500);
  d.update(10600, 0, true, false, false, false);
  check(!d.cruise, "failed engagement times out");
  std::cout << "Driving override, brake/AOL, cancel and watchdog regressions passed\n";
}
