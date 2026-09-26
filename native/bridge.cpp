// Local Story Mode simulator adapter. F7 enables lateral; F8 sets cruise.
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <Xinput.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include "main.h"
#include "natives.h"
#include "driving_state.h"
#include "steering_memory.h"
#include "spawn_car.h"
#include "angle_servo.h"
#include "longitudinal_actuator.h"
#include "radar_sensor.h"
#include "road_context_sensor.h"

static HMODULE adapter_module = nullptr;

#pragma pack(push, 1)
struct Telemetry {
  uint32_t magic = 0x5447504f, version = 4;
  uint64_t sequence = 0, tick_ms = 0;
  uint32_t frame = 0, vehicle = 0, model = 0, flags = 0;
  float speed = 0, steer_input = 0, gas = 0, brake = 0;
  float px = 0, py = 0, pz = 0, vx = 0, vy = 0, vz = 0;
  float pitch = 0, roll = 0, heading = 0, wx = 0, wy = 0, wz = 0;
  float cruise_speed = 13.4112f, wheelbase = 2.7f;
  float wheel_angle_deg = 0, wheel_left_z = 0, wheel_right_z = 0, applied_steer = 0;
  uint32_t spawn_status = 0;
};
struct Command {
  uint32_t magic = 0, version = 0;
  uint64_t sequence = 0, capture_tick_ms = 0;
  uint32_t vehicle = 0, active = 0;
  float steer = 0, throttle = 0, brake = 0;
};
#pragma pack(pop)
static_assert(sizeof(Telemetry) == 132);
static_assert(sizeof(Command) == 44);

static bool Foreground() {
  DWORD pid = 0;
  GetWindowThreadProcessId(GetForegroundWindow(), &pid);
  return pid == GetCurrentProcessId();
}
static bool Pressed(int key) {
  static bool was_down[256] = {};
  bool down = Foreground() && (GetAsyncKeyState(key) & 0x8000);
  bool edge = down && !was_down[key];
  was_down[key] = down;
  return edge;
}
static void StopCamera(Cam& camera) {
  if (camera) {
    CAM::RENDER_SCRIPT_CAMS(false, false, 0, true, false);
    CAM::DESTROY_CAM(camera, false);
    camera = 0;
  }
}

static void ScriptMain() {
  WSADATA data;
  if (WSAStartup(MAKEWORD(2,2), &data)) return;
  SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  sockaddr_in local{};
  local.sin_family = AF_INET;
  local.sin_port = htons(8767);
  local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (sock == INVALID_SOCKET || bind(sock, reinterpret_cast<sockaddr*>(&local), sizeof(local))) {
    if (sock != INVALID_SOCKET) closesocket(sock);
    WSACleanup();
    return;
  }
  u_long nonblocking = 1;
  ioctlsocket(sock, FIONBIO, &nonblocking);
  sockaddr_in destination = local;
  destination.sin_port = htons(8766);
  sockaddr_in road_destination=local;
  road_destination.sin_port=htons(8772);
  SOCKET road_socket=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
  if(road_socket!=INVALID_SOCKET) ioctlsocket(road_socket,FIONBIO,&nonblocking);
  FILE* log = std::fopen("OpenPilotGTA-bridge.log", "a");
  if (log) { std::fprintf(log, "bridge protocol=4 runtime=%d; F6 camera, F7 master, F8 set/resume, F9 cancel, F10 off, F12 stock Krieger, +/- speed\n", int(getGameVersion())); std::fflush(log); }
  SteeringMemory steering;
  steering.initialize(log);
  OpenPilotCar openpilot_car;
  AngleServo angle_servo;
  wchar_t settings[MAX_PATH] = {};
  if (GetModuleFileNameW(adapter_module, settings, MAX_PATH)) {
    if (auto slash = std::wcsrchr(settings, L'\\')) *(slash + 1) = L'\0';
    wcscat_s(settings, L"OpenPilotGTA.ini");
  }
  RadarSensor radar;
  RoadContextSensor road_context;
  int nearby_vehicles[1024] = {};
  int nearby_count = 0;
  uint64_t radar_max_ms = 0;
  // Frame-rate response evidence; buffered and flushed with the existing
  // once-per-second log. Preserve each session's independent measurements.
  char steering_trace_path[96];
  std::snprintf(steering_trace_path, sizeof(steering_trace_path), "OpenPilotGTA-steering-%llu.csv", GetTickCount64());
  FILE* steering_trace = std::fopen(steering_trace_path, "w");
  if (steering_trace) std::fprintf(steering_trace, "tick_ms,vehicle,model,speed,desired,measured,bias,input_gain,integral,lat_active,manual_steer\n");
  uint64_t previous_tick = GetTickCount64(), next_tuning_read = 0;
  Cam camera = 0;
  Vehicle previous_vehicle = 0;
  int front_left_bone = -1, front_right_bone = -1;
  DrivingState driving;
  bool left = false, right = false;
  float cruise_speed = 13.4112f, wheelbase = 2.7f;
  uint64_t next_speed_repeat = 0;
  uint64_t next_blindspot_check = 0;
  bool left_blindspot = false, right_blindspot = false;
  uint64_t sequence = 0, last_command_ms = 0, last_log_ms = 0, last_sequence = 0;
  Command command{};
  while (!NETWORK::NETWORK_IS_GAME_IN_PROGRESS()) {
    const uint64_t now = GetTickCount64();
    const bool master_before = driving.master, cruise_before = driving.cruise;
    float steering_dt = std::min(.1f, (now-previous_tick)/1000.f);
    previous_tick = now;
    if (now >= next_tuning_read) {
      wchar_t value[64];
      GetPrivateProfileStringW(L"Steering", L"FullScaleDegrees", L"120", value, 64, settings);
      angle_servo.full_scale_degrees = std::clamp(std::wcstof(value, nullptr), 10.f, 240.f);
      GetPrivateProfileStringW(L"Steering", L"IntegralGain", L"0.005", value, 64, settings);
      angle_servo.integral_gain = std::clamp(std::wcstof(value, nullptr), .001f, .08f);
      GetPrivateProfileStringW(L"Steering", L"ProportionalGain", L"0.3", value, 64, settings);
      angle_servo.proportional_gain = std::clamp(std::wcstof(value, nullptr), 0.f, .5f);
      next_tuning_read = now+1000;
    }
    Telemetry t;
    t.sequence = ++sequence;
    t.tick_ms = now;
    t.frame = GAMEPLAY::GET_FRAME_COUNT();
    Ped ped = PLAYER::PLAYER_PED_ID();
    Vehicle vehicle = PED::IS_PED_IN_ANY_VEHICLE(ped, false) ? PED::GET_VEHICLE_PED_IS_IN(ped, false) : 0;
    bool valid = vehicle && PLAYER::IS_PLAYER_PLAYING(PLAYER::PLAYER_ID()) &&
      !PLAYER::IS_PLAYER_DEAD(PLAYER::PLAYER_ID()) && VEHICLE::GET_PED_IN_VEHICLE_SEAT(vehicle, -1) == ped;
    bool paused = UI::IS_PAUSE_MENU_ACTIVE() || !CAM::IS_SCREEN_FADED_IN();
    if (Pressed(VK_F12) && PLAYER::IS_PLAYER_PLAYING(PLAYER::PLAYER_ID()) && !PLAYER::IS_PLAYER_DEAD(PLAYER::PLAYER_ID())) {
      driving.off();
      openpilot_car.request(ped, vehicle, paused, now);
    }
    const Vehicle spawned_car = openpilot_car.update(ped, vehicle, paused, now, log);
    if (spawned_car) { vehicle = spawned_car; valid = true; }
    t.spawn_status = openpilot_car.status;
    if (vehicle != previous_vehicle || !valid) {
      driving.off();
      left = right = false;
      StopCamera(camera);
      previous_vehicle = vehicle;
      if (valid) {
        front_left_bone = ENTITY::GET_ENTITY_BONE_INDEX_BY_NAME(vehicle, "wheel_lf");
        front_right_bone = ENTITY::GET_ENTITY_BONE_INDEX_BY_NAME(vehicle, "wheel_rf");
        int front = front_left_bone;
        int rear = ENTITY::GET_ENTITY_BONE_INDEX_BY_NAME(vehicle, "wheel_lr");
        if (front >= 0 && rear >= 0) {
          Vector3 a = ENTITY::GET_WORLD_POSITION_OF_ENTITY_BONE(vehicle, front);
          Vector3 b = ENTITY::GET_WORLD_POSITION_OF_ENTITY_BONE(vehicle, rear);
          float length = std::sqrt((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y)+(a.z-b.z)*(a.z-b.z));
          if (length > 1 && length < 10) wheelbase = length;
        }
      }
    }
    // Poll a bounded number of local packets per frame; never block the game.
    for (int i = 0; i < 32; ++i) {
      Command candidate{};
      int received = recv(sock, reinterpret_cast<char*>(&candidate), sizeof(candidate), 0);
      if (received < 0) break;
      if (received != sizeof(Command) || candidate.magic != 0x4347504f || candidate.version != 4 ||
          candidate.sequence <= last_sequence || candidate.vehicle != uint32_t(vehicle) ||
          candidate.capture_tick_ms > now || now - candidate.capture_tick_ms > 250 ||
          !std::isfinite(candidate.steer) || !std::isfinite(candidate.throttle) || !std::isfinite(candidate.brake) ||
          std::abs(candidate.steer) > 70 || candidate.throttle < 0 || candidate.throttle > 1 ||
          candidate.brake < 0 || candidate.brake > 1 || candidate.active > 7) continue;
      command = candidate;
      last_sequence = candidate.sequence;
      last_command_ms = now;
    }
    bool camera_key = Pressed(VK_F6), master_key = Pressed(VK_F7), arm_key = Pressed(VK_F8);
    bool cancel_key = Pressed(VK_F9), off_key = Pressed(VK_F10);
    bool foreground = Foreground();
    // Read physical input separately from the values injected by this script.
    float manual_steer = 0, manual_gas = 0, manual_brake = 0;
    bool gamepad_handbrake = false;
    if (foreground) {
      manual_steer = ((GetAsyncKeyState('D') | GetAsyncKeyState(VK_RIGHT)) & 0x8000 ? 1.f : 0.f) -
        ((GetAsyncKeyState('A') | GetAsyncKeyState(VK_LEFT)) & 0x8000 ? 1.f : 0.f);
      manual_gas = (GetAsyncKeyState('W') | GetAsyncKeyState(VK_UP)) & 0x8000 ? 1.f : 0.f;
      manual_brake = (GetAsyncKeyState('S') | GetAsyncKeyState(VK_DOWN)) & 0x8000 ? 1.f : 0.f;
      for (DWORD index=0; index<4; ++index) {
        XINPUT_STATE input{};
        if (XInputGetState(index, &input) != ERROR_SUCCESS) continue;
        if (std::abs(int(input.Gamepad.sThumbLX)) > XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE)
          manual_steer = std::clamp(input.Gamepad.sThumbLX / 32767.f, -1.f, 1.f);
        manual_gas = std::max(manual_gas, input.Gamepad.bRightTrigger / 255.f);
        manual_brake = std::max(manual_brake, input.Gamepad.bLeftTrigger / 255.f);
        gamepad_handbrake |= (input.Gamepad.wButtons & XINPUT_GAMEPAD_A) != 0;
      }
    }
    bool steering_override = gamepad_handbrake || std::abs(manual_steer) > .08f ||
      (foreground && (GetAsyncKeyState(VK_SPACE) & 0x8000));
    bool pedal_override = manual_gas > .08f || manual_brake > .08f;
    bool manual = steering_override || pedal_override;
    if ((camera_key || spawned_car) && valid && !paused) {
      driving.off();
      if (camera) StopCamera(camera);
      else {
        camera = CAM::CREATE_CAM("DEFAULT_SCRIPTED_CAMERA", true);
        // Wide pinhole camera. The transport derives the narrow camera using K.
        CAM::SET_CAM_FOV(camera, float(2 * std::atan(604.0 / 567.0) * 180.0 / 3.141592653589793));
        CAM::ATTACH_CAM_TO_ENTITY(camera, vehicle, 0, 1.1f, .85f, true);
        CAM::SET_CAM_ACTIVE(camera, true);
        CAM::RENDER_SCRIPT_CAMS(true, false, 0, true, false);
      }
    }
    bool fresh = last_command_ms && now - last_command_ms <= 200 &&
      command.capture_tick_ms <= now && now - command.capture_tick_ms <= 250;
    if (master_key && valid && camera && fresh && !paused && !steering_override) {
      driving.toggle_master();
    }
    if (arm_key && valid && camera && fresh && !paused && !manual) {
      driving.set(now);
      if (!(GetAsyncKeyState(VK_SHIFT) & 0x8000))
        cruise_speed = std::max(1.f, ENTITY::GET_ENTITY_SPEED(vehicle));
    }
    // Background driving is requested by the user. Physical game inputs are
    // still sampled only while GTA is focused; unrelated typing cannot steer.
    driving.update(now, command.active, valid && !paused && camera && fresh,
      cancel_key, manual_brake > .08f, off_key || gamepad_handbrake ||
      (foreground && (GetAsyncKeyState(VK_SPACE) & 0x8000)));
    if (log && ((master_before && !driving.master) || (cruise_before && !driving.cruise))) {
      const char* reason = !valid ? "vehicle_unavailable" : paused ? "paused" : !camera ? "camera_off" :
        !fresh ? (now-command.capture_tick_ms > 250 ? "camera_stale" : "command_stale") :
        off_key ? "all_off" : (gamepad_handbrake || (foreground && (GetAsyncKeyState(VK_SPACE) & 0x8000))) ? "handbrake" :
        master_key ? "master_button" : cancel_key ? "cancel_button" : manual_brake > .08f ? "brake" :
        spawned_car ? "spawn_car" : "controller_disabled";
      std::fprintf(log, "disengage tick=%llu reason=%s master=%d cruise=%d foreground=%d command_age=%llu camera_age=%llu mode=%u\n",
        now, reason, driving.master, driving.cruise, foreground, now-last_command_ms, now-command.capture_tick_ms, command.active);
      std::fflush(log);
      if (steering_trace) std::fflush(steering_trace);
    }
    int speed_direction = foreground ? (((GetAsyncKeyState(VK_OEM_PLUS) | GetAsyncKeyState(VK_ADD)) & 0x8000 ? 1 : 0) -
      ((GetAsyncKeyState(VK_OEM_MINUS) | GetAsyncKeyState(VK_SUBTRACT)) & 0x8000 ? 1 : 0)) : 0;
    if (speed_direction && now >= next_speed_repeat) {
      float step = GetAsyncKeyState(VK_SHIFT) & 0x8000 ? 2.2352f : .44704f;
      cruise_speed = std::clamp(cruise_speed + speed_direction*step, 1.f, 150.f);
      next_speed_repeat = now + 200;
    } else if (!speed_direction) next_speed_repeat = 0;
    // Sample the physics state BEFORE applying this frame's command. Never
    // report a just-written setpoint as measured actuator response.
    bool wheel_angle_valid = valid && steering.read(vehicle, t.wheel_angle_deg);
    const uint32_t vehicle_model = valid ? ENTITY::GET_ENTITY_MODEL(vehicle) : 0;
    const float vehicle_speed = valid ? ENTITY::GET_ENTITY_SPEED(vehicle) : 0;
    const float calibrated_speed = vehicle_model == 3630826055u ? vehicle_speed : 0;
    bool lat_active = wheel_angle_valid && driving.lateral(command.active, steering_override);
    bool long_active = driving.longitudinal(command.active, pedal_override);
    if (lat_active) {
      // GTA recalculates steering angle from its input before physics, so direct
      // angle writes are overwritten. Close the loop through the real input.
      VEHICLE::SET_VEHICLE_STEER_BIAS(vehicle, angle_servo.update(command.steer, t.wheel_angle_deg, steering_dt, calibrated_speed));
    } else angle_servo.reset();
    if (steering_trace && valid && wheel_angle_valid && camera && !paused)
      std::fprintf(steering_trace, "%llu,%u,%u,%.4f,%.4f,%.4f,%.6f,%.3f,%.6f,%d,%d\n",
        now, uint32_t(vehicle), vehicle_model, vehicle_speed, command.steer, t.wheel_angle_deg,
        angle_servo.output, angle_servo.input_gain(calibrated_speed), angle_servo.integral, lat_active, steering_override);
    const bool active = lat_active || long_active;
    PedalOutput pedals;
    float forward_speed = valid ? ENTITY::GET_ENTITY_SPEED_VECTOR(vehicle, true).y : 0;
    if (active) {
      if (long_active) {
        pedals = longitudinal_output(true, forward_speed, command.throttle, command.brake);
        CONTROLS::_SET_CONTROL_NORMAL(0, 71, pedals.throttle);
        CONTROLS::_SET_CONTROL_NORMAL(0, 72, pedals.brake);
        CONTROLS::_SET_CONTROL_NORMAL(0, 76, pedals.hold);
        driving.long_was_applied = true;
      }
    }
    if (valid) {
      t.vehicle = vehicle;
      t.model = ENTITY::GET_ENTITY_MODEL(vehicle);
      t.speed = ENTITY::GET_ENTITY_SPEED(vehicle);
      t.steer_input = manual_steer;
      t.applied_steer = lat_active ? command.steer : 0;
      if (front_left_bone >= 0 && front_right_bone >= 0) {
        // Original game native _GET_ENTITY_BONE_ROTATION_LOCAL (v1734+).
        // Retain raw bone values for diagnostics only. Wheel spin changes Euler
        // decomposition: these Z values are NOT steering-angle feedback.
        Vector3 l = invoke<Vector3>(0xBD8D32550E5CEBFE, vehicle, front_left_bone);
        Vector3 r = invoke<Vector3>(0xBD8D32550E5CEBFE, vehicle, front_right_bone);
        t.wheel_left_z = std::isfinite(l.z) ? l.z : 0;
        t.wheel_right_z = std::isfinite(r.z) ? r.z : 0;
      }
      t.gas = manual_gas;
      t.brake = manual_brake;
      Vector3 p = ENTITY::GET_ENTITY_COORDS(vehicle, true), v = ENTITY::GET_ENTITY_VELOCITY(vehicle);
      Vector3 r = ENTITY::GET_ENTITY_ROTATION(vehicle, 2), w = ENTITY::GET_ENTITY_ROTATION_VELOCITY(vehicle);
      t.px=p.x; t.py=p.y; t.pz=p.z; t.vx=v.x; t.vy=v.y; t.vz=v.z;
      t.pitch=r.x; t.roll=r.y; t.heading=r.z; t.wx=w.x; t.wy=w.y; t.wz=w.z;
      if (now >= next_blindspot_check) {
        left_blindspot = right_blindspot = false;
        nearby_count = worldGetAllVehicles(nearby_vehicles, 1024);
        float heading = r.z * 3.141592653589793f / 180.f;
        for (int i=0; i<nearby_count; ++i) {
          if (nearby_vehicles[i] == vehicle || !ENTITY::DOES_ENTITY_EXIST(nearby_vehicles[i])) continue;
          Vector3 other = ENTITY::GET_ENTITY_COORDS(nearby_vehicles[i], true);
          float dx = other.x-p.x, dy = other.y-p.y;
          if (std::abs(other.z-p.z) > 3) continue;
          float longitudinal = -std::sin(heading)*dx + std::cos(heading)*dy;
          float lateral = std::cos(heading)*dx + std::sin(heading)*dy;
          if (longitudinal > -10 && longitudinal < 6) {
            left_blindspot |= lateral < -1.2f && lateral > -5.0f;
            right_blindspot |= lateral > 1.2f && lateral < 5.0f;
          }
        }
        next_blindspot_check = now + 100;
      }
      if (camera) {
        CAM::SET_CAM_ROT(camera, r.x, r.y, r.z, 2);
        UI::HIDE_HUD_AND_RADAR_THIS_FRAME();
      }
      if (Pressed(VK_OEM_4)) { left = !left; right = false; }
      if (Pressed(VK_OEM_6)) { right = !right; left = false; }
      VEHICLE::SET_VEHICLE_INDICATOR_LIGHTS(vehicle, 1, left);
      VEHICLE::SET_VEHICLE_INDICATOR_LIGHTS(vehicle, 0, right);
    }
    t.flags = (valid ? 1 : 0) | (paused ? 2 : 0) | (camera ? 4 : 0) | (driving.master ? 8 : 0) |
      (steering_override ? 16 : 0) | (left ? 32 : 0) | (right ? 64 : 0) | (active ? 128 : 0) |
      (arm_key ? 256 : 0) | (cancel_key ? 512 : 0) | (!foreground ? 1024 : 0) |
      (driving.cruise ? 2048 : 0) | (speed_direction > 0 ? 4096 : 0) | (speed_direction < 0 ? 8192 : 0) |
      (foreground && (GetAsyncKeyState('B') & 0x8000) ? 16384 : 0) |
      (long_active ? 32768 : 0) | (lat_active ? 65536 : 0) |
      (foreground && (GetAsyncKeyState('L') & 0x8000) ? 131072 : 0) |
      (foreground && (GetAsyncKeyState(VK_F5) & 0x8000) ? 262144 : 0) |
      (foreground && (GetAsyncKeyState(VK_F4) & 0x8000) ? 524288 : 0) |
      (foreground && (GetAsyncKeyState(VK_F1) & 0x8000) ? 1048576 : 0) |
      (foreground && (GetAsyncKeyState(VK_F2) & 0x8000) ? 2097152 : 0) |
      (foreground && (GetAsyncKeyState(VK_F3) & 0x8000) ? 4194304 : 0) |
      (foreground && (GetAsyncKeyState(VK_F11) & 0x8000) ? 8388608 : 0) |
      (left_blindspot ? 16777216 : 0) | (right_blindspot ? 33554432 : 0) |
      (wheel_angle_valid ? 67108864 : 0);
    t.cruise_speed = cruise_speed;
    t.wheelbase = wheelbase;
    sendto(sock, reinterpret_cast<const char*>(&t), sizeof(t), 0, reinterpret_cast<sockaddr*>(&destination), sizeof(destination));
    const uint64_t radar_start = GetTickCount64();
    if (radar.update(vehicle, valid && camera && !paused, now, nearby_vehicles, nearby_count))
      sendto(sock, reinterpret_cast<const char*>(&radar.packet), sizeof(radar.packet), 0,
        reinterpret_cast<sockaddr*>(&destination), sizeof(destination));
    radar_max_ms = std::max(radar_max_ms, GetTickCount64()-radar_start);
    if(road_socket!=INVALID_SOCKET && road_context.update(vehicle,camera,valid&&camera&&!paused,now))
      sendto(road_socket,reinterpret_cast<const char*>(&road_context.packet),sizeof(road_context.packet),0,
        reinterpret_cast<sockaddr*>(&road_destination),sizeof(road_destination));
    if (log && now - last_log_ms >= 1000) {
      std::fprintf(log, "tick=%llu vehicle=%u flags=%u speed=%.3f camera=%d active=%d command_age=%llu target=%.4f angle=%.4f bias=%.5f forward=%.3f gas=%.4f brake=%.4f hold=%.0f\n",
        now, t.vehicle, t.flags, t.speed, camera != 0, active, now-last_command_ms, command.steer, t.wheel_angle_deg, angle_servo.output,
        forward_speed, pedals.throttle, pedals.brake, pedals.hold);
      std::fflush(log);
      std::fprintf(log, "radar tick=%llu valid=%u points=%u max_update_ms=%llu\n", now,
        radar.packet.valid, radar.packet.count, radar_max_ms);
      std::fflush(log);
      radar_max_ms = 0;
      last_log_ms = now;
      if (steering_trace) std::fflush(steering_trace);
    }
    WAIT(0);
  }
  StopCamera(camera);
  closesocket(sock);
  if(road_socket!=INVALID_SOCKET) closesocket(road_socket);
  WSACleanup();
  if (steering_trace) std::fclose(steering_trace);
  if (log) { std::fprintf(log, "Stopped: online session\n"); std::fclose(log); }
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) { adapter_module = module; DisableThreadLibraryCalls(module); scriptRegister(module, ScriptMain); }
  else if (reason == DLL_PROCESS_DETACH) scriptUnregister(module);
  return TRUE;
}
