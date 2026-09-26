#pragma once
#include "radar_geometry.h"
#include <vector>
#include <map>

class RadarSensor {
  using Vec=gta_radar::Vec;
  using Box=gta_radar::Box;
  struct Candidate { Vehicle entity; Hash model; Vec position; float distance; Box box; };
  struct Track {
    uint32_t id=0; Hash model=0; int ray=0;
    uint64_t launched=0, seen=0;
    gta_radar::Point pending, visible;
    bool detected=false;
  };
  std::map<Vehicle,Track> tracks;
  uint32_t next_id=0;
  uint64_t next_scan=0, sequence=0;
  Vehicle ego=0;
  static Vec vec(Vector3 v) { return {v.x,v.y,v.z}; }
  static Box geometry(Vehicle v, Hash model, Vec position) {
    Box b; b.origin=position;
    b.right=vec(ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(v,1,0,0))-position;
    b.forward=vec(ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(v,0,1,0))-position;
    b.up=vec(ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(v,0,0,1))-position;
    Vector3 lo{},hi{}; GAMEPLAY::GET_MODEL_DIMENSIONS(model,&lo,&hi);
    b.lo=vec(lo); b.hi=vec(hi); return b;
  }
public:
  gta_radar::Packet packet;
  // Called once per game frame; never waits for a probe. A maximum of 16
  // asynchronous probes is launched per scan. Vehicle enumeration is shared
  // with the existing blind-spot scan by bridge.cpp.
  bool update(Vehicle vehicle, bool enabled, uint64_t now, const int* vehicles, int count) {
    if (!enabled || vehicle!=ego) {
      for (auto& pair:tracks) { pair.second.id=0; pair.second.seen=0; pair.second.detected=false; }
    }
    for (auto it=tracks.begin();it!=tracks.end();) {
      auto& t=it->second;
      if (t.ray) {
        BOOL hit=false; Vector3 end{},normal{}; Entity entity=0;
        int result=WORLDPROBE::_GET_RAYCAST_RESULT(t.ray,&hit,&end,&normal,&entity);
        if (result != 1) {
          t.detected = t.pending.id == t.id && now-t.launched <= 150 &&
            gta_radar::visible_result(result,hit!=0,entity,it->first);
          if (t.detected) t.visible=t.pending;
          t.ray=0;
        } else if (now-t.launched > 150) t.detected=false;
      }
      if ((!enabled || vehicle!=ego || now-t.seen>150) && !t.ray) it=tracks.erase(it);
      else ++it;
    }
    if (now<next_scan) return false;
    next_scan=now-next_scan>50 ? now+50 : next_scan+50;
    if (vehicle!=ego) { for(auto& pair:tracks) pair.second.detected=false; ego=vehicle; }
    packet={}; packet.sequence=++sequence; packet.tick_ms=now;
    packet.vehicle=enabled?uint32_t(vehicle):0; packet.valid=enabled?1:0;
    if (!enabled) return true;
    const Vec position=vec(ENTITY::GET_ENTITY_COORDS(vehicle,true));
    const Vec origin=vec(ENTITY::GET_OFFSET_FROM_ENTITY_IN_WORLD_COORDS(vehicle,0,gta_radar::sensor_y,gta_radar::sensor_z));
    const Box basis=geometry(vehicle,ENTITY::GET_ENTITY_MODEL(vehicle),position);
    const Vec ego_velocity=vec(ENTITY::GET_ENTITY_VELOCITY(vehicle));
    std::vector<Candidate> candidates;
    candidates.reserve(32);
    for(int i=0;i<count;++i) {
      const Vehicle other=vehicles[i];
      if(other==vehicle || !ENTITY::DOES_ENTITY_EXIST(other)) continue;
      Vec p=vec(ENTITY::GET_ENTITY_COORDS(other,true)), rel=p-origin;
      float forward=rel.dot(basis.forward), lateral=rel.dot(basis.right), height=rel.dot(basis.up);
      // Broad phase includes trucks whose center lies just outside the FOV.
      if(forward<=0 || forward>165 || std::abs(lateral)>40 || std::abs(height)>8) continue;
      candidates.push_back({other,ENTITY::GET_ENTITY_MODEL(other),p,rel.dot(rel),{}});
    }
    std::sort(candidates.begin(),candidates.end(),[](const auto& a,const auto& b){return a.distance<b.distance;});
    if(candidates.size()>32) candidates.resize(32);
    for(auto& c:candidates) c.box=geometry(c.entity,c.model,c.position);
    int selected=0, stalled=0;
    for(const auto& c:candidates) {
      if(selected>=gta_radar::max_points) break;
      const Vec target=c.box.center(); float entry=0;
      if(!gta_radar::intersect(origin,target,c.box,entry)) continue;
      const Vec surface=origin+(target-origin)*entry, rel=surface-origin;
      const Vec local={rel.dot(basis.right),rel.dot(basis.forward),rel.dot(basis.up)};
      if(!gta_radar::in_view(local)) continue;
      bool blocked=false;
      for(const auto& blocker:candidates) {
        float obstruction=0;
        if(blocker.entity!=c.entity && gta_radar::intersect(origin,target,blocker.box,obstruction) && obstruction < entry-.001f) {
          blocked=true; break;
        }
      }
      if(blocked) { auto old=tracks.find(c.entity); if(old!=tracks.end()) old->second.detected=false; continue; }
      // Continue polling retired probes until GTA releases their handles.
      // A stalled engine must not cause unbounded probes or allocations.
      if(!tracks.count(c.entity) && tracks.size()>=64) { packet.valid=0; continue; }
      ++selected;
      auto& t=tracks[c.entity];
      if(!t.id || t.model!=c.model || now-t.seen>150) {
        t.detected=false; t.id=++next_id; t.model=c.model;
      }
      t.seen=now;
      if(!t.ray) {
        Vec relative_velocity=vec(ENTITY::GET_ENTITY_VELOCITY(c.entity))-ego_velocity;
        t.pending={t.id,now,local.y,-local.x,relative_velocity.dot(basis.forward)};
        t.launched=now;
        t.ray=WORLDPROBE::_0x7EE9F5D83DD4F90E(origin.x,origin.y,origin.z,target.x,target.y,target.z,19,vehicle,7);
        if(!t.ray) t.detected=false;
      }
      if(!t.ray || now-t.launched>150) ++stalled;
      if(t.detected && now-t.visible.tick_ms<=150 && packet.count<gta_radar::max_points)
        packet.points[packet.count++]=t.visible;
    }
    if(selected>0 && stalled==selected) { packet.valid=0; packet.count=0; }
    return true;
  }
};
