"""Cinque supercombo adapter for the real FrogPilot modeld in GTA simulation.

The temporal contract follows commaai/openpilot 68b5f8e and StarPilot Dom:
two images 200 ms apart, 32 past spatial features and 33 desire intervals.
No vision/planning outputs are synthesized.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np


class NearestCamera:
    """The pinned upstream NV12 warp/pack, with cached integer pixel maps."""
    def __init__(self, skip=4):
        self.frames = np.zeros((skip + 1, 6, 128, 256), np.uint8)
        self.key = None

    @staticmethod
    def pixel_map(matrix, width, height, source_width, source_height):
        x, y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        z = matrix[2, 0] * x + matrix[2, 1] * y + matrix[2, 2]
        xx = matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]
        yy = matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]
        xx = np.divide(xx, z, out=np.zeros_like(xx), where=z != 0)
        yy = np.divide(yy, z, out=np.zeros_like(yy), where=z != 0)
        return (np.rint(yy).clip(0, source_height - 1).astype(np.intp),
                np.rint(xx).clip(0, source_width - 1).astype(np.intp))

    def prepare(self, buf, matrix):
        matrix = np.asarray(matrix, dtype=np.float32)
        key = (buf.width, buf.height, buf.stride, buf.uv_offset, matrix.tobytes())
        if key != self.key:
            self.y_map = self.pixel_map(matrix, 512, 256, buf.width, buf.height)
            uv_matrix = matrix * np.array([[1, 1, .5], [1, 1, .5], [2, 2, 1]], np.float32)
            self.uv_map = self.pixel_map(uv_matrix, 256, 128, buf.width // 2, buf.height // 2)
            self.key = key
        raw = np.frombuffer(buf.data, np.uint8)
        y = raw[:buf.height * buf.stride].reshape(buf.height, buf.stride)[self.y_map]
        uv = raw[buf.uv_offset:buf.uv_offset + (buf.height // 2) * buf.stride].reshape(buf.height // 2, buf.stride)
        u = uv[:, :buf.width:2][self.uv_map]
        v = uv[:, 1:buf.width:2][self.uv_map]
        self.frames[:-1] = self.frames[1:]
        self.frames[-1] = np.stack((y[0::2, 0::2], y[1::2, 0::2], y[0::2, 1::2], y[1::2, 1::2], u, v))
        return np.concatenate((self.frames[0], self.frames[-1]), axis=0)[None]


class OrtCudaRunner:
    def __init__(self, root, values):
        # Dependencies are isolated from FrogPilot's pinned environment.
        sys.path.append('/data/gta-models/cuda-runtime')
        import onnxruntime as ort
        ort.preload_dlls(cuda=True, cudnn=True)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        self.session = ort.InferenceSession(str(root / 'driving_portable.onnx'), options,
            providers=[('CUDAExecutionProvider', {'enable_cuda_graph': os.getenv('GTA_ORT_CUDA_GRAPH', '0'), 'use_tf32': '0',
                        'cudnn_conv_algo_search': os.getenv('GTA_ORT_CONV_SEARCH', 'HEURISTIC'),
                        'cudnn_conv_use_max_workspace': os.getenv('GTA_ORT_CONV_WORKSPACE', '1')})])
        self.session.disable_fallback()
        if self.session.get_providers()[0] != 'CUDAExecutionProvider':
            raise RuntimeError('The big model did not initialize CUDA')
        self.binding = self.session.io_binding()
        self.device_inputs = {}
        for name, value in values.items():
            self.device_inputs[name] = ort.OrtValue.ortvalue_from_numpy(value, 'cuda', 0)
            self.binding.bind_ortvalue_input(name, self.device_inputs[name])
        spec = self.session.get_outputs()[0]
        self.output = ort.OrtValue.ortvalue_from_shape_and_type(spec.shape, np.float16, 'cuda', 0)
        self.binding.bind_ortvalue_output(spec.name, self.output)

    def __call__(self, values):
        for name, value in values.items():
            self.device_inputs[name].update_inplace(value)
        self.session.run_with_iobinding(self.binding)
        return self.output.numpy().astype(np.float32)


class SpatialHistory:
    def __init__(self, feature_shape=(1, 32, 32, 512), desire_shape=(1, 33, 8), skip=4):
        self.skip = skip
        self.feature_shape = tuple(feature_shape)
        self.desire_shape = tuple(desire_shape)
        self.feature_width = int(np.prod(feature_shape[2:]))
        self.features = np.zeros((skip * feature_shape[1], 1, self.feature_width), np.float16)
        self.desires = np.zeros((skip * desire_shape[1], 1, desire_shape[2]), np.float16)
        self.previous_feature = np.zeros((1, self.feature_width), np.float16)
        self.previous_desire = np.zeros(desire_shape[2], np.float32)

    def advance(self, desire):
        # Sample oldest-first at indices 0,4,... . The newest feature must be
        # 200 ms old: the network itself inserts the current image's feature.
        self.features[:-1] = self.features[1:]
        self.features[-1] = self.previous_feature
        desire = np.array(desire, dtype=np.float32, copy=True)
        desire[0] = 0
        pulse = np.where(desire - self.previous_desire > .99, desire, 0)
        self.previous_desire[:] = desire
        self.desires[:-1] = self.desires[1:]
        self.desires[-1, 0] = pulse
        return (self.features[::self.skip].reshape(self.feature_shape),
                self.desires.reshape(-1, self.skip, *self.desires.shape[1:]).max(axis=1).reshape(self.desire_shape))


def action_from_supercombo(output, previous_action, v_ego):
    from cereal import log
    from openpilot.selfdrive.controls.lib.drive_helpers import smooth_value
    acceleration = float(output['action'][0, 1])
    curvature = float(output['action'][0, 0]) / max(1., v_ego) ** 2
    stop = v_ego < .3 and acceleration < .1
    acceleration = smooth_value(acceleration, previous_action.desiredAcceleration, .3)
    if v_ego <= .3:
        curvature = previous_action.desiredCurvature
    return log.ModelDataV2.Action(desiredCurvature=curvature,
                                 desiredAcceleration=float(acceleration), shouldStop=bool(stop))


class CinqueModelState:
    def __init__(self, context):
        if not (os.getenv('GTA_SIMULATION') == os.getenv('SIMULATION') == '1'
                and os.getenv('GTA_MODEL_BACKEND') == 'CUDA'):
            raise RuntimeError('Cinque GTA adapter is restricted to CUDA game simulation')
        from openpilot.selfdrive.modeld.parse_model_outputs import Parser
        root = Path(os.environ['GTA_BIG_MODEL']).resolve()
        self.metadata = json.loads((root / 'metadata-fp16.json').read_text())
        if self.metadata['id'] != 'cinque-driving' or self.metadata['compiled_float_inputs'] != 'float16':
            raise ValueError('Unsupported big-model profile')
        self.vision_input_names = ['img', 'big_img']
        shapes = {k: tuple(v['shape']) for k, v in self.metadata['inputs'].items()}
        for name in self.vision_input_names:
            if shapes[name] != (1, 12, 128, 256):
                raise ValueError(f'Unexpected camera shape: {name} {shapes[name]}')
        self.frames = {name: NearestCamera(self.metadata['frame_skip']) for name in self.vision_input_names}
        self.history = SpatialHistory(shapes['features_buffer'], shapes['desire_pulse'], self.metadata['frame_skip'])
        self.numpy_inputs = {k: np.zeros(shapes[k], np.uint8 if 'img' in k else np.float16) for k in sorted(shapes)}
        self.slices = {k: slice(*v) for k, v in self.metadata['output_slices'].items()}
        self.parser = Parser()
        self.vision_output = np.empty(0, np.float32)
        from .gta_trt import TrtRunner
        self.infer = TrtRunner(root, self.numpy_inputs)
        # Materialize driver/graph state before subscribing to live frames.
        for _ in range(3):
            if not np.isfinite(self.infer(self.numpy_inputs)).all():
                raise RuntimeError('Cinque warmup returned non-finite output')
        self.last_timings = {}
        self.status_path = Path(os.environ['GTA_BIG_MODEL_STATUS']) if os.getenv('GTA_BIG_MODEL_STATUS') else None
        self.last_status = 0.
        self.runs = 0

    def run(self, bufs, transforms, inputs, prepare_only):
        start = time.perf_counter()
        for name in self.vision_input_names:
            self.numpy_inputs[name][:] = self.frames[name].prepare(bufs[name], transforms[name])
        features, desires = self.history.advance(inputs['desire_pulse'])
        self.numpy_inputs['features_buffer'][:] = features
        self.numpy_inputs['desire_pulse'][:] = desires
        self.numpy_inputs['traffic_convention'][:] = inputs['traffic_convention']
        self.numpy_inputs['action_t'][:] = inputs['action_t']
        if prepare_only:
            return None
        prepared = time.perf_counter()
        output = self.infer(self.numpy_inputs).reshape(-1)
        inferred = time.perf_counter()
        if not np.isfinite(output).all():
            raise RuntimeError('Non-finite Cinque output')
        self.history.previous_feature[:] = output[self.slices['hidden_state']]
        parsed = {k: output[None, v].copy() for k, v in self.slices.items()}
        self.parser.parse_outputs(parsed)
        self.parser.parse_mdn('action', parsed, in_N=0, out_N=0, out_shape=(2,))
        if os.getenv('SEND_RAW_PRED'):
            parsed['raw_pred'] = output.copy()
        self.last_timings = {'preprocess_ms':(prepared-start)*1000,
                             'inference_ms':(inferred-prepared)*1000,
                             'parse_ms':(time.perf_counter()-inferred)*1000}
        self.runs += 1
        if self.status_path and time.monotonic()-self.last_status >= 1:
            self.last_status = time.monotonic()
            status = dict(id=self.metadata['id'], name='Cinque Terre (Big)', backend='TensorRT',
                          pid=os.getpid(), monotonic=self.last_status, runs=self.runs,
                          source_sha256=self.metadata['source_sha256'],
                          checkpoint=self.metadata['checkpoint'], timings=self.last_timings)
            temporary=self.status_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(status)+'\n')
            temporary.replace(self.status_path)
        return parsed
