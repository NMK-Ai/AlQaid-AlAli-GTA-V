#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
#include "main.h"

// Enable the game's Story Mode DLC-vehicle switch. Layout/signature references:
// ikt32/GTAVAddonLoader NativeMemory.cpp/.hpp, Enhanced support by Chiheb-Bacha.
// Discover the global from shop_controller bytecode, never a hardcoded index.
namespace StoryDlc {
inline bool readable(const void* pointer, size_t size) {
  auto cursor = reinterpret_cast<uintptr_t>(pointer);
  if (!cursor || size > UINTPTR_MAX-cursor) return false;
  const auto end = cursor+size;
  while (cursor < end) {
    MEMORY_BASIC_INFORMATION r{};
    if (!VirtualQuery(reinterpret_cast<void*>(cursor), &r, sizeof(r)) || r.State != MEM_COMMIT ||
        r.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return false;
    const auto next = reinterpret_cast<uintptr_t>(r.BaseAddress)+r.RegionSize;
    if (next <= cursor) return false;
    cursor = next;
  }
  return true;
}
template<class T> bool read(const uint8_t* pointer, T& value) {
  if (!readable(pointer, sizeof(T))) return false;
  std::memcpy(&value, pointer, sizeof(T));
  return true;
}
inline std::vector<const uint8_t*> matches(const uint8_t* bytes, size_t size, const std::vector<int>& pattern) {
  std::vector<const uint8_t*> found;
  if (!readable(bytes, size) || size < pattern.size()) return found;
  for (size_t i = 0; i + pattern.size() <= size; ++i) {
    bool match = true;
    for (size_t j = 0; j < pattern.size(); ++j)
      if (pattern[j] >= 0 && bytes[i+j] != pattern[j]) { match = false; break; }
    if (match) found.push_back(bytes+i);
  }
  return found;
}
inline bool enable(FILE* log) {
  if (int(getGameVersion()) < 1000) return false;
  auto base = reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
  auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
  auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
  auto sections = IMAGE_FIRST_SECTION(nt);
  std::vector<const uint8_t*> found;
  for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i) {
    if (!(sections[i].Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
    auto part = matches(base+sections[i].VirtualAddress, sections[i].Misc.VirtualSize,
                        {0x48,0x03,0x05,-1,-1,-1,-1,0x4c,0x85,0xc0,0x0f,0x84,-1,-1,-1,-1,0xe9});
    found.insert(found.end(), part.begin(), part.end());
  }
  if (found.size() != 1) return false;
  int32_t displacement = 0;
  if (!read(found[0]+3, displacement)) return false;
  const auto table = found[0]+7+displacement;
  const uint8_t* entries = nullptr;
  int count = 0;
  if (!read(table, entries) || !read(table+24, count) || count <= 0 || count > 4096) return false;
  const uint8_t* header = nullptr;
  for (int i = 0; i < count; ++i) {
    uint32_t hash = 0;
    if (!read(entries+i*16+12, hash)) return false;
    if (hash == 0x39da738b) { if (!read(entries+i*16, header)) return false; break; }
  }
  if (!header) return false;
  uint32_t name_hash = 0, code_length = 0;
  const uint8_t* pages = nullptr;
  if (!read(header+0x58, name_hash) || name_hash != 0x39da738b ||
      !read(header+0x1c, code_length) || !code_length || code_length > 16*1024*1024 ||
      !read(header+0x10, pages)) return false;
  // Flatten pages so a signature or its operand can cross a page boundary.
  std::vector<uint8_t> code(code_length);
  for (uint32_t offset = 0; offset < code_length; offset += 0x4000) {
    const uint8_t* page = nullptr;
    size_t size = (std::min)(uint32_t(0x4000), code_length-offset);
    if (!read(pages+(offset/0x4000)*8, page) || !readable(page, size)) return false;
    std::memcpy(code.data()+offset, page, size);
  }
  found = matches(code.data(), code.size(), {0x2d,-1,-1,-1,-1,0x2c,-1,-1,-1,0x56,-1,-1,0x71,0x2e,-1,-1,0x62});
  if (found.size() != 1 || found[0]+20 > code.data()+code.size()) return false;
  uint32_t index = uint32_t(found[0][17]) | uint32_t(found[0][18]) << 8 | uint32_t(found[0][19]) << 16;
  if (index >= 0x1000000) return false;
  auto global = getGlobalPtr(index);
  MEMORY_BASIC_INFORMATION region{};
  if (!readable(global, sizeof(*global)) || !VirtualQuery(global, &region, sizeof(region)) ||
      !(region.Protect & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE)) || *global > 1) return false;
  const auto previous = *global;
  *global = 1;
  if (log) { std::fprintf(log, "Story Mode DLC vehicles enabled: discovered global=%u previous=%llu\n", index, previous); std::fflush(log); }
  return true;
}
}
