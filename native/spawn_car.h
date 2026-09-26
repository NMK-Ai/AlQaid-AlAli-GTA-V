#pragma once
#include "natives.h"
#include <cstdint>
#include <cstdio>
#include "dlc_vehicles.h"

// Nonblocking model streaming: never freeze the game waiting for a DLC asset.
class OpenPilotCar {
  Hash model_ = 0;
  uint64_t requested_at_ = 0;
public:
  // Status: 0 idle, 1 loading, 2 spawned, 3 unavailable, 4 no clear road,
  // 5 timeout, 6 stop the car first, 7 creation failed, 8 DLC switch unavailable.
  unsigned status = 0;
  Vehicle spawned = 0;
  void request(Ped ped, Vehicle current, bool paused, uint64_t now) {
    if (paused || (current && ENTITY::GET_ENTITY_SPEED(current) > .5f)) { status = 6; return; }
    if (requested_at_) return;
    model_ = GAMEPLAY::GET_HASH_KEY("krieger");
    if (!STREAMING::IS_MODEL_IN_CDIMAGE(model_) || !STREAMING::IS_MODEL_A_VEHICLE(model_)) { status = 3; return; }
    STREAMING::REQUEST_MODEL(model_);
    requested_at_ = now;
    status = 1;
  }
  Vehicle update(Ped ped, Vehicle current, bool paused, uint64_t now, FILE* log) {
    if (!requested_at_) return 0;
    if (paused || (current && ENTITY::GET_ENTITY_SPEED(current) > .5f)) { finish(6); return 0; }
    if (now-requested_at_ > 10000) { finish(5); return 0; }
    if (!STREAMING::HAS_MODEL_LOADED(model_)) return 0;
    if (!StoryDlc::enable(log)) { finish(8); return 0; }
    Vector3 position{};
    float heading = 0;
    bool clear = false;
    const Entity origin = current ? current : ped;
    for (float distance : {9.f, 15.f, 23.f, 32.f}) {
      Vector3 candidate = ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(origin, 0, distance, 0);
      if (PATHFIND::GET_CLOSEST_VEHICLE_NODE_WITH_HEADING(candidate.x, candidate.y, candidate.z,
            &position, &heading, 1, 3.f, 0) &&
          !VEHICLE::IS_ANY_VEHICLE_NEAR_POINT(position.x, position.y, position.z, 4.f)) { clear = true; break; }
    }
    if (!clear) { finish(4); return 0; }
    Vehicle car = invoke<Vehicle>(0xAF35D0D2583051B0, model_, position.x, position.y, position.z+.3f, heading, false, true, false);
    if (!car || !ENTITY::DOES_ENTITY_EXIST(car)) { finish(7); return 0; }
    ENTITY::SET_ENTITY_AS_MISSION_ENTITY(car, true, true);
    // A fresh vehicle has stock handling/mods. Do not alter handling, power,
    // traction, tires, or suspension: every calibration uses the same stock car.
    VEHICLE::SET_VEHICLE_MOD_KIT(car, 0);
    VEHICLE::SET_VEHICLE_NUMBER_PLATE_TEXT(car, "OPENPILT");
    invoke<BOOL>(0x49733E92263139D1, car, 5.f);
    PED::SET_PED_INTO_VEHICLE(ped, car, -1);
    VEHICLE::SET_VEHICLE_ENGINE_ON(car, true, true, false);
    // Preserve the previous vehicle, including any user car/save state.
    spawned = car;
    finish(2);
    if (log) { std::fprintf(log, "Spawned stock OpenPilot Krieger vehicle=%d model=%u\n", car, model_); std::fflush(log); }
    return car;
  }
private:
  void finish(unsigned result) { status = result; requested_at_ = 0; STREAMING::SET_MODEL_AS_NO_LONGER_NEEDED(model_); }
};
