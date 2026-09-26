#include "angle_servo.h"
#include <cstdio>
#include <deque>

// Preserve the installed controller for before/after model comparisons.
struct LegacyServo {
  float integral = 0, output = 0;
  float update(float desired, float measured, float dt) {
    integral = std::clamp(integral+(desired-measured)*.005f*dt, -1.f, 1.f);
    output = std::clamp(desired/120.f+integral, output-2.5f*dt, output+2.5f*dt);
    return std::clamp(output, -1.f, 1.f);
  }
};

struct Plant {
  float measured = 0;
  std::deque<float> pending;
  Plant(int delay_steps) : pending(delay_steps, 0.f) {}
  void step(float input, float gain, float lag, float dt) {
    pending.push_back(input);
    const float delayed = pending.front();
    pending.pop_front();
    // Exact discretization, physical +/-40 degree Krieger wheel lock.
    measured += (1-std::exp(-dt/lag))*(std::clamp(gain*delayed,-40.f,40.f)-measured);
  }
};

int main() {
  double old_total = 0, new_total = 0;
  int cases = 0;
  float worst_ratio = 0;
  float worst_increase = 0;
  for (float speed : {0.f, 10.f, 20.f, 30.f, 40.f, 55.f}) {
    for (float uncertainty : {.8f, 1.f, 1.2f}) {
      // Independent approximate plant trend, not a copy of the lookup table.
      const float gain = (120+2.5f*std::min(speed,40.f))*uncertainty;
      for (float lag : {.03f, .1f, .2f}) for (float delay : {0.f, .033f, .1f}) {
        for (float dt : {1.f/30, 1.f/60}) {
          AngleServo servo;
          LegacyServo legacy;
          Plant actual(int(std::round(delay/dt))), old(int(std::round(delay/dt)));
          double new_error = 0, old_error = 0;
          for (int step = 0; step < int(30/dt); ++step) {
            const float t = step*dt;
            const float target = 4*std::sin(1.2f*t)+2*std::sin(3.5f*t);
            const float output = servo.update(target, actual.measured, dt, speed);
            if (!std::isfinite(output) || std::abs(output)>1) return 1;
            actual.step(output,gain,lag,dt);
            old.step(legacy.update(target,old.measured,dt),gain,lag,dt);
            if (t>2) {
              new_error += std::pow(actual.measured-target,2);
              old_error += std::pow(old.measured-target,2);
            }
          }
          const float ratio = float(std::sqrt(new_error/old_error));
          worst_ratio = std::max(worst_ratio,ratio);
          const float sample_count = float(int(30/dt)-int(2/dt)-1);
          const float new_rms = float(std::sqrt(new_error/sample_count));
          const float old_rms = float(std::sqrt(old_error/sample_count));
          worst_increase = std::max(worst_increase, new_rms-old_rms);
          // An almost perfectly matched legacy plant can make a ratio
          // arbitrarily large. Bound regression in actual degrees instead.
          if (new_rms-old_rms > .3f) {
            std::printf("regression speed %.1f gain %.1f lag %.3f delay %.3f dt %.3f RMS old %.3f new %.3f\n",speed,gain,lag,delay,dt,old_rms,new_rms);
            return 2;
          }
          if (speed>=20) {new_total+=new_error;old_total+=old_error;}
          ++cases;
          // Steady offsets must converge in both directions despite uncertain
          // gain and lag, including a physical-lock request and recovery.
          for (float target : {5.f, -5.f, 40.f, -40.f, 0.f}) {
            for (int step=0;step<int(25/dt);++step)
              actual.step(servo.update(target,actual.measured,dt,speed),gain,lag,dt);
            if (std::abs(actual.measured-target)>.2f) return 3;
          }
          servo.reset();
          if (servo.output!=0 || servo.integral!=0) return 4;
        }
      }
    }
  }
  // Invalid telemetry releases the actuator, including invalid speed/config.
  for (int field=0;field<5;++field) {
    AngleServo servo;
    servo.update(5,0,.033f,30);
    if (field==4) servo.full_scale_degrees=NAN;
    if (servo.update(field==0?NAN:5,field==1?NAN:0,field==2?NAN:.033f,field==3?NAN:30)!=0 || servo.integral!=0) return 5;
  }
  const double improvement = std::sqrt(new_total/old_total);
  std::printf("%d delayed-plant cases; high-speed RMS ratio %.3f; worst increase %.3f deg; worst ratio %.3f\n",cases,improvement,worst_increase,worst_ratio);
  if (improvement>.8) return 6;
  return 0;
}
