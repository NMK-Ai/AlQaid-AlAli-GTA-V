"""Check compiled CUDA pair against independent FP32 ONNX and FrogPilot parsing."""
import hashlib
import json
import os
from pathlib import Path
import pickle
import sys
import time

os.environ['DEV'] = 'CUDA'
sys.path.append('/data/gta-models/validation-deps')
import numpy as np
import cv2
import onnxruntime as ort
from tinygrad import Tensor
from openpilot.selfdrive.modeld.parse_model_outputs import Parser

root = Path('/data/gta-models/macrostiff')
project = Path(__file__).resolve().parents[1]
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
metadata, runners, sessions = {}, {}, {}
for kind in ('vision', 'policy'):
    assert 'test vs onnx passed' in (root/f'{kind}-precise-compile.log').read_text()
    metadata[kind] = pickle.loads((root/f'driving_{kind}_metadata.pkl').read_bytes())
    runners[kind] = pickle.loads((root/f'driving_{kind}_gta_cuda.pkl').read_bytes())
    sessions[kind] = ort.InferenceSession(str(root/f'driving_{kind}_precise.onnx'), options,
                                        providers=['CPUExecutionProvider'])

rng = np.random.default_rng(12987)
report = dict(reference='Independent ONNX Runtime CPU, same graph and exact weight values in FP32',
              rtol=1e-4, atol=1e-4, cases=[], precision=json.loads((root/'precision.json').read_text()))

def infer(kind, values):
    inputs = {k:Tensor(v, device='CUDA' if 'img' in k else 'NPY').realize() for k,v in values.items()}
    return runners[kind](**inputs).numpy().reshape(1,-1)

for case in ('gradient_camera', 'random_camera', 'gray_camera'):
    camera = {k: np.broadcast_to(np.arange(shape[-1],dtype=np.uint8),shape).copy() if case=='gradient_camera' else
              (rng.integers(0,256,shape,dtype=np.uint8) if case=='random_camera' else np.full(shape,128,np.uint8))
              for k,shape in metadata['vision']['input_shapes'].items()}
    actual_vision = infer('vision', camera)
    expected_vision = sessions['vision'].run(None, camera)[0].reshape(1,-1)
    np.testing.assert_allclose(actual_vision, expected_vision, rtol=1e-4, atol=1e-4)
    hidden = actual_vision[:,metadata['vision']['output_slices']['hidden_state']]
    policy = {k:np.zeros(shape,np.float32) for k,shape in metadata['policy']['input_shapes'].items()}
    policy['traffic_convention'][0,0] = 1
    policy['features_buffer'][:] = hidden[:,None,:]
    if case=='random_camera':
        policy['desire_pulse'][0,-1,3] = 1
    actual_policy = infer('policy', policy)
    expected_policy = sessions['policy'].run(None, policy)[0].reshape(1,-1)
    np.testing.assert_allclose(actual_policy, expected_policy, rtol=1e-4, atol=1e-4)
    outputs = {k:arr[:,s].copy() for kind,arr in [('vision',actual_vision),('policy',actual_policy)]
               for k,s in metadata[kind]['output_slices'].items()}
    outputs = Parser().parse_outputs(outputs)
    assert outputs['plan'].shape == (1,33,15)
    assert outputs['lead'].shape == (1,3,6,4)
    assert outputs['lane_lines'].shape == (1,4,33,2)
    assert all(np.isfinite(v).all() for v in outputs.values())
    report['cases'].append(dict(name=case, vision_max_error=float(np.max(np.abs(actual_vision-expected_vision))),
                               policy_max_error=float(np.max(np.abs(actual_policy-expected_policy))),
                               genuine_parser_passed=True))

timings = []
for i in range(110):
    start = time.perf_counter()
    infer('vision', camera)
    infer('policy', policy)
    if i>=10:
        timings.append((time.perf_counter()-start)*1000)
report['pair_inference_ms'] = {str(p):float(np.percentile(timings,p)) for p in (50,95,99,100)}
assert report['pair_inference_ms']['95'] < 40
report['passed'] = True
report['artifacts'] = {f'driving_{kind}{suffix}':hashlib.sha256((root/f'driving_{kind}{suffix}').read_bytes()).hexdigest()
                       for kind in ('vision','policy') for suffix in ('_gta_cuda.pkl','_metadata.pkl')}
(root/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
