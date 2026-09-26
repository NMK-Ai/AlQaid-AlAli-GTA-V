"""Exercise actual cereal messages and the pinned FrogPilot RadarD, offline."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from gta_radar import RadarReceiver
from test_radar import packet
from cereal import car, log, custom
from openpilot.selfdrive.controls import radard
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, N


class SM(dict):
    def __init__(self, speed, lead_probability=.99):
        md=log.ModelDataV2.new_message()
        md.position.x=[float(i*5) for i in range(33)]
        md.position.y=[0.]*33
        md.velocity.x=[speed]
        md.init('laneLines',4)
        for lane,y in zip(md.laneLines,(-5.,-1.8,1.8,5.)):
            lane.x=list(md.position.x); lane.y=[y]*33
        md.init('leadsV3',2)
        for i,lead in enumerate(md.leadsV3):
            lead.prob=lead_probability if i==0 else 0.
            lead.x=[31.52]; lead.y=[-.5]; lead.v=[speed-5.]; lead.a=[0.]
            lead.xStd=[1.]; lead.yStd=[.5]; lead.vStd=[1.]
        cs=car.CarState.new_message(vEgo=speed)
        super().__init__(modelV2=md,carState=cs,frogpilotPlan=custom.FrogPilotPlan.new_message())
        self.seen={'modelV2':True}; self.logMonoTime={'modelV2':1,'carState':1}
        self.recv_frame={'carState':0}; self.valid=True
    def all_checks(self): return self.valid


class FusionTests(unittest.TestCase):
    def setUp(self):
        toggles=SimpleNamespace(lead_detection_probability=.5, human_lane_changes=False, adjacent_lead_tracking=False)
        self.mock=patch.object(radard,'get_frogpilot_toggles',return_value=toggles)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def test_real_fusion_uses_distance_velocity_and_left_sign(self):
        r=RadarReceiver(); r.update(packet(),10.)
        msg=r.message(dict(vehicle=123,tick_ms=1000),True,10.01)
        self.assertTrue(msg.valid)
        # Serialization verifies optional NaNs and actual schema compatibility.
        with log.Event.from_bytes(msg.to_bytes()) as decoded:
            rd=radard.RadarD(.05); sm=SM(20.)
            for i in range(5):
                sm.recv_frame['carState']=i
                rd.update(sm,decoded.liveTracks)
            lead=rd.radar_state.leadOne
            self.assertTrue(lead.status and lead.radar and rd.radar_state_valid)
            self.assertEqual(lead.radarTrackId,7)
            self.assertAlmostEqual(lead.dRel,30.)
            self.assertAlmostEqual(lead.yRel,.5)
            self.assertAlmostEqual(lead.vRel,-5.)
            self.assertAlmostEqual(lead.vLead,15.)

    def test_stopped_car_low_speed_and_stale_removal(self):
        p=packet(); p['points'][0].update(d=15.,y=0.,v=-2.)
        r=RadarReceiver(); r.update(p,10.)
        t=dict(vehicle=123,tick_ms=1000)
        rd=radard.RadarD(); sm=SM(2.,0.)
        rd.update(sm,r.message(t,True,10.01).liveTracks)
        self.assertTrue(rd.radar_state.leadOne.radar)
        self.assertAlmostEqual(rd.radar_state.leadOne.vLead,0.)
        stale=r.message(t,True,10.3); sm.valid=stale.valid
        rd.update(sm,stale.liveTracks)
        self.assertFalse(rd.radar_state.leadOne.status)
        self.assertFalse(rd.radar_state_valid)
        self.assertTrue(rd.radar_state.radarErrors.radarUnavailableTemporary)
        self.assertEqual(rd.tracks,{})

    def test_fused_radar_lead_reaches_real_longitudinal_solver(self):
        r=RadarReceiver(); r.update(packet(),10.)
        rd=radard.RadarD(); sm=SM(20.)
        rd.update(sm,r.message(dict(vehicle=123,tick_ms=1000),True,10.01).liveTracks)
        self.assertTrue(rd.radar_state.leadOne.radar)
        mpc=LongitudinalMpc(); mpc.set_cur_state(20.,0.)
        toggles=SimpleNamespace(human_following=False, lead_detection_probability=.5)
        for _ in range(5):
            mpc.update(25.,sm['modelV2'],rd.radar_state,
                       *[np.zeros(N+1) for _ in range(4)],1.5,-3.5,2.,toggles,False)
        self.assertEqual(mpc.solution_status,0)
        self.assertEqual(mpc.source,'lead0')
        self.assertAlmostEqual(mpc.lead_xv_0[0,0],30.)
        self.assertLess(float(mpc.a_solution[3]),0.)


if __name__=='__main__': unittest.main()
