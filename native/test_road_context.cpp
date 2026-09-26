#include "road_context_packet.h"
#include <fstream>
int main() {
  gta_road::Packet p;
  p.sequence=7;p.tick_ms=1000;p.vehicle=123;p.flags=gta_road::Enabled|gta_road::Node|gta_road::Edge|gta_road::Navigation|gta_road::Waypoint;
  p.ego={100,200,20};p.node={101,201,20};p.node_lanes=3;p.forward_lanes=2;p.backward_lanes=1;
  p.median_gap=1.5f;p.waypoint={200,300,20};p.direction=3;p.junction_distance_raw=123.f;
  std::ofstream out("road-context-native-fixture.bin",std::ios::binary);
  out.write(reinterpret_cast<const char*>(&p),sizeof(p));
  return out.good()?0:1;
}
