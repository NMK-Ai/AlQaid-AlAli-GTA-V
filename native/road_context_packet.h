#pragma once
#include <cstdint>

namespace gta_road {
enum Flags : uint32_t { Enabled=1, Node=2, Properties=4, Edge=8,
  BoundaryA=16, BoundaryB=32, Waypoint=64, Navigation=128, Camera=256 };
#pragma pack(push,1)
struct Vec { float x=0,y=0,z=0; };
struct Projection { Vec local; float u=0,v=0; uint32_t valid=0; };
struct Packet {
  uint32_t magic=0x4441504f, version=1;
  uint64_t sequence=0,tick_ms=0;
  uint32_t vehicle=0,flags=0;
  float update_ms=0;
  Vec ego; float heading=0,speed=0;
  Vec node; float node_heading=0;
  int32_t node_lanes=0,density=0,node_properties=0;
  Vec edge_a,edge_b; int32_t forward_lanes=0,backward_lanes=0;
  float median_gap=0; // GET_CLOSEST_ROAD width is NOT full road width.
  Vec boundary_a,boundary_b;
  Vec waypoint; int32_t direction=-1;
  float junction_distance_raw=0,navigation_aux_raw=0;
  int32_t navigation_return=0;
  Vec camera,camera_rotation; float camera_fov=0;
  Projection projections[6];
};
#pragma pack(pop)
static_assert(sizeof(Packet)==344);
}
