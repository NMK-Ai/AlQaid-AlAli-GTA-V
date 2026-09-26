#pragma once
#include <windows.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "main.h"

// Enhanced field discovery documented by ScriptHookVDotNetEnhanced:
// source/core/NativeMemory.cs (SteeringScaleOffset/SteeringAngleOffset) and
// source/scripting_v3/GTA/Entities/Vehicles/Vehicle.cs (SteeringAngle, radians).
// No executable patching or guessed version-specific vehicle offsets.
class SteeringMemory {
  int angle_offset_ = 0;
public:
  bool initialize(FILE* log) {
    const auto base = reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (!base || dos->e_magic != IMAGE_DOS_SIGNATURE || int(getGameVersion()) < 1000) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
    const auto section = IMAGE_FIRST_SECTION(nt);
    const uint8_t pattern[] = {0x0f,0x56,0xf9,0xf3,0x0f,0x11,0xbe,0,0,0,0,0x48,0x8b,0x86};
    int matches = 0, found_offset = 0;
    for (unsigned s = 0; s < nt->FileHeader.NumberOfSections; ++s) {
      if (!(section[s].Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
      const uint8_t* bytes = base + section[s].VirtualAddress;
      const size_t size = section[s].Misc.VirtualSize;
      for (size_t i = 0; i + sizeof(pattern) <= size; ++i) {
        if (bytes[i] != pattern[0] || std::memcmp(bytes+i, pattern, 7) ||
            std::memcmp(bytes+i+11, pattern+11, 3)) continue;
        int scale = 0;
        std::memcpy(&scale, bytes+i+7, sizeof(scale));
        ++matches;
        found_offset = scale + 8;
      }
    }
    // Ambiguity or a changed game layout disables steering rather than writing
    // an arbitrary field. The current vehicle is validated again every frame.
    if (matches == 1 && found_offset >= 0x100 && found_offset < 0x3000 && found_offset % 4 == 0)
      angle_offset_ = found_offset;
    if (log) { std::fprintf(log, "steering field matches=%d angle_offset=0x%x valid=%d\n", matches, found_offset, angle_offset_ != 0); std::fflush(log); }
    return angle_offset_ != 0;
  }

  float* address(int vehicle) const {
    if (!angle_offset_ || !vehicle) return nullptr;
    auto base = getScriptHandleBaseAddress(vehicle);
    if (!base) return nullptr;
    auto ptr = reinterpret_cast<float*>(base + angle_offset_);
    MEMORY_BASIC_INFORMATION region{};
    if (!VirtualQuery(ptr, &region, sizeof(region)) || region.State != MEM_COMMIT ||
        region.Protect & (PAGE_GUARD | PAGE_NOACCESS) ||
        !(region.Protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE)) ||
        reinterpret_cast<uintptr_t>(ptr)+sizeof(float) > reinterpret_cast<uintptr_t>(region.BaseAddress)+region.RegionSize)
      return nullptr;
    return ptr;
  }

  bool read(int vehicle, float& degrees) const {
    auto ptr = address(vehicle);
    if (!ptr) return false;
    const float radians = *ptr;
    if (!std::isfinite(radians) || std::abs(radians) > 1.5f) return false;
    degrees = radians * (180.f / 3.141592653589793f);
    return true;
  }

  bool write(int vehicle, float degrees) const {
    auto ptr = address(vehicle);
    if (!ptr || !std::isfinite(degrees) || std::abs(degrees) > 70.f) return false;
    *ptr = degrees * (3.141592653589793f / 180.f);
    return true;
  }
};
