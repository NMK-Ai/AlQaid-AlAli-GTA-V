"""Check the temporal, camera and message contracts independently of GPU timing."""
import ast
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
sys.path.insert(0, str(ROOT / 'scripts'))
from gta_big_model import SpatialHistory, NearestCamera, action_from_supercombo
from gta_big_model_patch import patch_big_model


class BigModelContracts(unittest.TestCase):
    def test_spatial_history_is_past_only_at_five_hz(self):
        history = SpatialHistory((1, 32, 2, 3))
        for step in range(1, 151):
            features, _ = history.advance(np.zeros(8))
            expected = np.maximum(np.arange(step - 128, step - 3, 4), 0)
            np.testing.assert_array_equal(features[0, :, 0, 0], expected)
            history.previous_feature.fill(step)

    def test_desire_is_rising_pulse_and_survives_interval(self):
        h = SpatialHistory((1, 32, 1))
        desire = np.zeros(8); desire[3] = 1
        for step in range(6):
            _, out = h.advance(desire)
            self.assertEqual(out.sum(), 1)
            self.assertEqual(out[0, -1 if step < 4 else -2, 3], 1)
        _, out = h.advance(np.zeros(8))
        _, out = h.advance(desire)
        self.assertEqual(out.sum(), 2)

    def test_nv12_layout_and_two_frames_200ms_apart(self):
        width, height, stride = 512, 256, 528
        raw = np.zeros(stride * height * 3 // 2, np.uint8)
        y = raw[:stride*height].reshape(height,stride)
        uv = raw[stride*height:].reshape(height//2,stride)
        y[:, :width] = (np.arange(height)[:,None]*3 + np.arange(width)[None,:]) % 251
        uv[:, :width:2] = 77; uv[:, 1:width:2] = 133
        buf = SimpleNamespace(width=width, height=height, stride=stride, uv_offset=stride*height, data=raw)
        camera = NearestCamera()
        first = camera.prepare(buf, np.eye(3, dtype=np.float32))
        self.assertFalse(first[0,:6].any())
        expected = np.stack((y[0::2,:width:2],y[1::2,:width:2],y[0::2,1:width:2],y[1::2,1:width:2],
                             uv[:,:width:2],uv[:,1:width:2]))
        np.testing.assert_array_equal(first[0,6:],expected)
        for _ in range(4):
            current = camera.prepare(buf,np.eye(3,dtype=np.float32))
        np.testing.assert_array_equal(current[0,:6],expected)

    def test_sampling_rounds_then_clips_like_upstream(self):
        matrix = np.array([[1,0,.6],[0,1,-.6],[0,0,1]],np.float32)
        yy, xx = NearestCamera.pixel_map(matrix,3,3,3,3)
        np.testing.assert_array_equal(xx,[[1,2,2]]*3)
        np.testing.assert_array_equal(yy,[[0]*3,[0]*3,[1]*3])

    def test_narrow_and_wide_geometry_are_distinct_and_contained(self):
        from openpilot.common.transformations.model import get_warp_matrix
        from openpilot.common.transformations.camera import DEVICE_CAMERAS
        cameras = DEVICE_CAMERAS[('pc','unknown')]
        narrow = get_warp_matrix(np.zeros(3),cameras.fcam.intrinsics,False)
        wide = get_warp_matrix(np.zeros(3),cameras.ecam.intrinsics,True)
        ratio = 567 / 2648
        crop = np.array([[ratio,0,964*(1-ratio)],[0,ratio,604*(1-ratio)],[0,0,1]])
        n = crop @ narrow
        self.assertAlmostEqual(n[0,0],567/910)
        self.assertAlmostEqual(wide[0,0],567/455)
        for transform in [n,wide]:
            points=transform@np.array([[0,511,511,0],[0,0,255,255],[1,1,1,1]])
            self.assertTrue(((points[:2]>=0)&(points[:2]<np.array([[1928],[1208]]))).all())

    def test_action_head_units_and_genuine_messages(self):
        from cereal import messaging, log
        from openpilot.selfdrive.modeld.parse_model_outputs import Parser
        from openpilot.selfdrive.modeld.fill_model_msg import fill_model_msg, PublishState
        metadata=json.loads(Path('/data/gta-models/cinque-driving/metadata.json').read_text())
        raw=np.zeros(18452,np.float32)
        raw[slice(*metadata['output_slices']['action'])]=[2.,-.5,0,0]
        out={k:raw[None,slice(*v)].copy() for k,v in metadata['output_slices'].items()}
        parser=Parser(); parser.parse_outputs(out)
        parser.parse_mdn('action',out,in_N=0,out_N=0,out_shape=(2,))
        action=action_from_supercombo(out,log.ModelDataV2.Action(),20.)
        self.assertAlmostEqual(action.desiredCurvature,.005)
        self.assertLess(action.desiredAcceleration,0)
        self.assertFalse(action.shouldStop)
        base=messaging.new_message('drivingModelData'); extended=messaging.new_message('modelV2')
        fill_model_msg(base,extended,out,action,PublishState(),1,1,1,0,100,0.02,True)
        self.assertEqual(len(extended.modelV2.position.x),33)
        self.assertEqual(len(extended.modelV2.leadsV3),3)
        self.assertAlmostEqual(extended.modelV2.action.desiredCurvature,.005)

    def test_patch_is_idempotent_and_valid_python(self):
        source=Path('/data/openpilot/selfdrive/modeld/modeld.py').read_text()
        patched=patch_big_model(source)
        ast.parse(patched)
        self.assertEqual(patched,patch_big_model(patched))


if __name__ == '__main__':
    unittest.main()
