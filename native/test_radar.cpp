// Deterministic game API doubles: run the actual sensor's asynchronous state
// machine and geometry without taking control of the user's GTA session.
#include <map>
#include <cstdlib>
#include <iostream>
#include <fstream>
#include "radar_geometry.h"
using Vehicle=int; using Hash=unsigned; using BOOL=int; using Entity=int;
struct Vector3 { float x=0,y=0,z=0; };
struct Car { Vector3 p,v; unsigned model=1; };
static std::map<int,Car> cars;
namespace ENTITY {
bool DOES_ENTITY_EXIST(int e) { return cars.count(e)>0; }
Vector3 GET_ENTITY_COORDS(int e,bool) { return cars.at(e).p; }
Vector3 GET_ENTITY_VELOCITY(int e) { return cars.at(e).v; }
unsigned GET_ENTITY_MODEL(int e) { return cars.at(e).model; }
Vector3 GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(int e,float x,float y,float z) {
  auto p=cars.at(e).p; return {p.x+x,p.y+y,p.z+z};
}
}
namespace GAMEPLAY {
void GET_MODEL_DIMENSIONS(unsigned,Vector3* lo,Vector3* hi) { *lo={-1,-2,0}; *hi={1,2,1.5f}; }
}
namespace WORLDPROBE {
struct Ray { int polls=0; bool blocked=false; };
static std::map<int,Ray> rays;
static int serial=0,started=0;
static bool wall=false, pending_forever=false;
int _0x7EE9F5D83DD4F90E(float,float,float,float,float,float,int,Entity,int) {
  rays[++serial]={0,wall}; ++started; return serial;
}
int _GET_RAYCAST_RESULT(int id,BOOL* hit,Vector3*,Vector3*,Entity* entity) {
  auto found=rays.find(id); if(found==rays.end()) return 0;
  if(pending_forever || found->second.polls++==0) return 1;
  *hit=found->second.blocked; *entity=0; rays.erase(found); return 2;
}
}
#include "radar_sensor.h"
static void check(bool ok,const char* reason) {
  if(!ok) { std::cerr<<reason<<'\n'; std::exit(1); }
}
int main() {
  using namespace gta_radar;
  check(in_view({0,150,0}) && !in_view({0,151,0}),"range boundary");
  check(!in_view({10,5,0}) && !in_view({0,-10,0}) && !in_view({0,10,8}),"FOV/behind/overpass");
  Box b{{0,20,0},{1,0,0},{0,1,0},{0,0,1},{-1,-2,0},{1,2,2}};
  float entry=0;
  check(intersect({0,0,1},{0,30,1},b,entry) && std::abs(entry-.6f)<1e-6f,"box near surface");
  check(!intersect({3,0,1},{3,30,1},b,entry),"parallel segment beside box");
  b.right={0,1,0}; b.forward={-1,0,0};
  check(intersect({0,0,1},{0,30,1},b,entry) && std::abs(entry-19.f/30)<1e-6f,"rotated box");
  check(!visible_result(1,false,0,2) && !visible_result(0,false,0,2),"unfinished ray is not clear");
  check(visible_result(2,true,2,2) && !visible_result(2,true,3,2),"target hit vs obstruction");

  cars={{1,{{0,0,0},{0,20,0}}},{2,{{-.5f,35,0},{0,15,0}}},{3,{{-.5f,75,0},{0,15,0}}}};
  int vehicles[]={1,2,3}; RadarSensor sensor;
  sensor.update(1,true,1000,vehicles,3);
  check(sensor.packet.valid && sensor.packet.count==0,"pending probes must not invent detections");
  sensor.update(1,true,1016,vehicles,3);
  sensor.update(1,true,1033,vehicles,3);
  sensor.update(1,true,1050,vehicles,3);
  check(sensor.packet.count==1,"near vehicle must occlude farther one");
  auto point=sensor.packet.points[0];
  check(point.y>0 && point.v==-5,"left sign and world relative velocity");
  check(std::abs(point.d-(35-2-sensor_y))<.01,"range uses bounding surface, not car center");
  std::ofstream file("radar-native-fixture.bin",std::ios::binary);
  file.write(reinterpret_cast<const char*>(&sensor.packet),sizeof(sensor.packet)); file.close();
  WORLDPROBE::wall=true;
  for(uint64_t t=1066;t<=1234;t+=16) sensor.update(1,true,t,vehicles,3);
  check(sensor.packet.count==0,"wall occlusion must remove cached detection");
  WORLDPROBE::wall=false;
  for(uint64_t t=1250;t<=1418;t+=16) sensor.update(1,true,t,vehicles,3);
  check(sensor.packet.count==1 && sensor.packet.points[0].id==point.id,"occlusion preserves stable identity");
  cars.erase(2);
  for(uint64_t t=1450;t<=1818;t+=16) sensor.update(1,true,t,vehicles,3);
  check(sensor.packet.count==1 && sensor.packet.points[0].id!=point.id,"removed lead reveals farther vehicle with different ID");
  cars[2]={{-.5f,35,0},{0,15,0}};
  for(uint64_t t=1850;t<=2066;t+=16) sensor.update(1,true,t,vehicles,3);
  check(sensor.packet.count==1 && sensor.packet.points[0].id>point.id,"reused handle must receive new identity");
  WORLDPROBE::pending_forever=true;
  for(uint64_t t=2100;t<=2516;t+=16) sensor.update(1,true,t,vehicles,3);
  check(sensor.packet.count==0,"stuck asynchronous probe cannot keep old lead alive");
  check(!sensor.packet.valid,"all probes stuck must report a sensor fault");
  sensor.update(1,false,2600,vehicles,3);
  check(!sensor.packet.valid && sensor.packet.count==0,"disabled camera/vehicle invalidates sensor");
  std::cout<<"Radar geometry, occlusion, asynchronous polling, identity and age checks passed\n";
}
