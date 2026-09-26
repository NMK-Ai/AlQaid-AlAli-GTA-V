"""Compute the unchanged model in FP32, preserving every learned weight value."""
import hashlib
import json
from pathlib import Path

import onnx
from onnx import helper, TensorProto, numpy_helper
import numpy as np

root = Path('/data/gta-models/macrostiff')
manifest = json.loads((root/'source-manifest.json').read_text())
for item in manifest['files']:
    assert hashlib.sha256((root/item['name']).read_bytes()).hexdigest() == item['sha256']

report = {}
for kind in ('vision', 'policy'):
    source = root/f'driving_{kind}.onnx'
    model = onnx.load(source)
    # A half value is represented exactly in float32. Only arithmetic precision
    # changes: graph topology, normalization, shapes, and learned values do not.
    tensors = list(model.graph.initializer)
    for node in model.graph.node:
        for attr in node.attribute:
            if attr.type == onnx.AttributeProto.TENSOR:
                tensors.append(attr.t)
        if node.op_type == 'Cast':
            for attr in node.attribute:
                if attr.name == 'to' and attr.i == TensorProto.FLOAT16:
                    attr.i = TensorProto.FLOAT
    promoted = 0
    for tensor in tensors:
        if tensor.data_type == TensorProto.FLOAT16:
            values = numpy_helper.to_array(tensor)
            wide = values.astype(np.float32)
            np.testing.assert_array_equal(wide.astype(np.float16), values)
            tensor.CopyFrom(numpy_helper.from_array(wide, name=tensor.name))
            promoted += 1
    for info in list(model.graph.input)+list(model.graph.value_info)+list(model.graph.output):
        if info.type.tensor_type.elem_type == TensorProto.FLOAT16:
            info.type.tensor_type.elem_type = TensorProto.FLOAT
    onnx.checker.check_model(model)
    output = root/f'driving_{kind}_precise.onnx'
    onnx.save(model, output)
    report[kind] = dict(precision='FP32', promoted_tensors=promoted, unchanged_weight_values=True,
                        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        precise_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
(root/'precision.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
