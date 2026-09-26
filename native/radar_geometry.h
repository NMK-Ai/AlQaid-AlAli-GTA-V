#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace gta_radar {
constexpr int max_points = 16;
// Virtual bumper radar reference: 1.52 m ahead of the camera at y=1.10.
// This matches radard's radar-to-camera translation without modifying fusion.
constexpr float sensor_y = 2.62f, sensor_z = .65f, range = 150.f;
struct Vec {
  float x=0, y=0, z=0;
  Vec operator+(Vec b) const { return {x+b.x,y+b.y,z+b.z}; }
  Vec operator-(Vec b) const { return {x-b.x,y-b.y,z-b.z}; }
  Vec operator*(float k) const { return {x*k,y*k,z*k}; }
  float dot(Vec b) const { return x*b.x+y*b.y+z*b.z; }
};
struct Box {
  Vec origin, right, forward, up, lo, hi;
  Vec local(Vec world) const { auto d=world-origin; return {d.dot(right),d.dot(forward),d.dot(up)}; }
  Vec center() const { auto c=(lo+hi)*.5f; return origin+right*c.x+forward*c.y+up*c.z; }
};
inline bool in_view(Vec point) {
  return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z) &&
    point.y > .5f && point.y <= range && std::abs(point.x) <= 30.f &&
    std::abs(point.x) <= point.y*.7002075f && std::abs(point.z) <= 3.f; // +/-35 degrees
}
// Segment/OBB intersection also handles distant vehicles that GTA's shape
// probe may omit. Includes vertical separation (bridges and overpasses).
inline bool intersect(Vec start, Vec end, const Box& box, float& entry) {
  auto a=box.local(start), b=box.local(end), d=b-a;
  const float p[3]={a.x,a.y,a.z}, v[3]={d.x,d.y,d.z};
  const float lo[3]={box.lo.x,box.lo.y,box.lo.z}, hi[3]={box.hi.x,box.hi.y,box.hi.z};
  float first=0, last=1;
  for (int i=0;i<3;++i) {
    if (std::abs(v[i]) < 1e-6f) { if (p[i]<lo[i] || p[i]>hi[i]) return false; }
    else {
      float entry_t=(lo[i]-p[i])/v[i], exit_t=(hi[i]-p[i])/v[i];
      if (entry_t>exit_t) std::swap(entry_t,exit_t);
      first=std::max(first,entry_t); last=std::min(last,exit_t);
      if (first>last) return false;
    }
  }
  entry=first;
  return true;
}
inline bool visible_result(int result, bool hit, int hit_entity, int target) {
  return result == 2 && (!hit || hit_entity == target);
}
#pragma pack(push,1)
struct Point { uint32_t id=0; uint64_t tick_ms=0; float d=0, y=0, v=0; };
struct Packet {
  uint32_t magic=0x5247504f, version=1;
  uint64_t sequence=0, tick_ms=0;
  uint32_t vehicle=0, valid=0, count=0;
  Point points[max_points];
};
#pragma pack(pop)
static_assert(sizeof(Point)==24 && sizeof(Packet)==420);
}
