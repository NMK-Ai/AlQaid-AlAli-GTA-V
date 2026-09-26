#pragma once
#include "road_context_packet.h"
#include <cmath>

// Read-only, 2 Hz diagnostics. No NPC tasks, routing mutations, handling
// writes, streaming waits, or connections to the driving control path.
class RoadContextSensor {
  uint64_t next=0,sequence=0;
  static gta_road::Vec vec(Vector3 p) { return {p.x,p.y,p.z}; }
  static bool finite(Vector3 p) { return std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z); }
public:
  gta_road::Packet packet;
  bool update(Vehicle vehicle, Cam camera, bool enabled, uint64_t now) {
    if(now<next) return false;
    next=now+500;
    packet={};packet.sequence=++sequence;packet.tick_ms=now;
    if(!enabled) return true;
    auto started=GetTickCount64();
    packet.vehicle=uint32_t(vehicle);packet.flags=gta_road::Enabled;
    Vector3 pos=ENTITY::GET_ENTITY_COORDS(vehicle,true);
    packet.ego=vec(pos);packet.heading=ENTITY::GET_ENTITY_HEADING(vehicle);
    packet.speed=ENTITY::GET_ENTITY_SPEED(vehicle);
    Vector3 node{};float heading=0;int lanes=0;
    if(invoke<BOOL>(0x80CA6A8B6C094CC4,pos.x,pos.y,pos.z,1,&node,&heading,&lanes,0,3.f,1.f)
       && finite(node)&&std::isfinite(heading)) {
      packet.node=vec(node);packet.node_heading=heading;packet.node_lanes=lanes;
      packet.flags|=gta_road::Node;
    }
    int density=0,properties=0;
    if(invoke<BOOL>(0x0568566ACBB5DEDC,pos.x,pos.y,pos.z,&density,&properties)) {
      packet.density=density;packet.node_properties=properties;packet.flags|=gta_road::Properties;
    }
    Vector3 a{},b{};int forward=0,backward=0;float gap=0;
    if(invoke<BOOL>(0x132F52BBA570FE92,pos.x,pos.y,pos.z,1.f,1,&a,&b,&forward,&backward,&gap,false)
       &&finite(a)&&finite(b)&&std::isfinite(gap)) {
      packet.edge_a=vec(a);packet.edge_b=vec(b);packet.forward_lanes=forward;packet.backward_lanes=backward;
      packet.median_gap=gap;packet.flags|=gta_road::Edge;
    }
    // Preserve the two raw boundary queries. Their side/geometry semantics
    // must be measured in Enhanced before any lane corridor is inferred.
    Vector3 boundary{};
    if(invoke<BOOL>(0xA0F8A7517A273C05,pos.x,pos.y,pos.z,packet.heading,&boundary)&&finite(boundary)) {
      packet.boundary_a=vec(boundary);packet.flags|=gta_road::BoundaryA;
    }
    if(invoke<BOOL>(0xA0F8A7517A273C05,pos.x,pos.y,pos.z,std::fmod(packet.heading+180.f,360.f),&boundary)&&finite(boundary)) {
      packet.boundary_b=vec(boundary);packet.flags|=gta_road::BoundaryB;
    }
    if(UI::IS_WAYPOINT_ACTIVE()) {
      const Blip blip=UI::GET_FIRST_BLIP_INFO_ID(8);
      if(UI::DOES_BLIP_EXIST(blip)) {
        Vector3 dest=UI::GET_BLIP_INFO_ID_COORD(blip);
        if(finite(dest)) {
          packet.waypoint=vec(dest);packet.flags|=gta_road::Waypoint;
          int direction=-1;float auxiliary=0,distance=0;
          packet.navigation_return=invoke<int>(0xF90125F1F79ECDF8,dest.x,dest.y,dest.z,false,&direction,&auxiliary,&distance);
          // Return value is not a documented success boolean. Keep units raw.
          if(std::isfinite(auxiliary)&&std::isfinite(distance)) {
            packet.direction=direction;packet.navigation_aux_raw=auxiliary;packet.junction_distance_raw=distance;
            packet.flags|=gta_road::Navigation;
          }
        }
      }
    }
    if(camera) {
      packet.camera=vec(CAM::GET_CAM_COORD(camera));packet.camera_rotation=vec(CAM::GET_CAM_ROT(camera,2));
      packet.camera_fov=CAM::GET_CAM_FOV(camera);packet.flags|=gta_road::Camera;
      // Known points relative to the attached camera (0,1.1,.85). The
      // screen projection independently checks rendered focal length.
      const gta_road::Vec offsets[6]={{-3,10,0},{3,10,0},{0,10,2},{0,10,-1},{-5,30,0},{5,30,0}};
      for(int i=0;i<6;++i) {
        auto& sample=packet.projections[i];sample.local=offsets[i];
        auto point=ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(vehicle,offsets[i].x,offsets[i].y+1.1f,offsets[i].z+.85f);
        float u=0,v=0;
        if(invoke<BOOL>(0x34E82F05DF2974F5,point.x,point.y,point.z,&u,&v)&&std::isfinite(u)&&std::isfinite(v)) {
          sample.u=u;sample.v=v;sample.valid=1;
        }
      }
    }
    packet.update_ms=float(GetTickCount64()-started);
    return true;
  }
};
