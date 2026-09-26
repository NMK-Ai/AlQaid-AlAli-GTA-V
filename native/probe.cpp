// Runtime compatibility probe. This intentionally implements no driving controls.
#include <windows.h>
#include <cstdio>
#include "main.h"
#include "natives.h"

static void ScriptMain() {
  FILE* log = std::fopen("OpenPilotGTA-probe.log", "a");
  if (log) {
    std::fprintf(log, "OpenPilotGTA native script started; runtime game enum=%d\n", int(getGameVersion()));
    std::fflush(log);
  }
  ULONGLONG last_write = 0;
  while (true) {
    // The probe never operates in an online session.
    if (NETWORK::NETWORK_IS_GAME_IN_PROGRESS()) {
      if (log) { std::fprintf(log, "Online session: probe stopped\n"); std::fclose(log); }
      return;
    }
    const ULONGLONG now = GetTickCount64();
    if (log && now - last_write >= 1000) {
      const Ped ped = PLAYER::PLAYER_PED_ID();
      const bool playing = PLAYER::IS_PLAYER_PLAYING(PLAYER::PLAYER_ID());
      const bool in_vehicle = playing && PED::IS_PED_IN_ANY_VEHICLE(ped, false);
      std::fprintf(log, "tick_ms=%llu playing=%d vehicle=%d pause=%d\n",
                   now, playing, in_vehicle, UI::IS_PAUSE_MENU_ACTIVE());
      std::fflush(log);
      last_write = now;
    }
    WAIT(0);
  }
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(module);
    scriptRegister(module, ScriptMain);
  } else if (reason == DLL_PROCESS_DETACH) {
    scriptUnregister(module);
  }
  return TRUE;
}
