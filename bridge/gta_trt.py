"""Fixed-shape TensorRT inference with owned buffers on a dedicated CUDA stream."""
import ctypes as c
from pathlib import Path
import sys

import numpy as np


class TrtRunner:
    def __init__(self, root, values):
        sys.path.append('/data/gta-models/trt-runtime')
        import tensorrt as trt
        self.cuda = c.CDLL('/data/gta-models/cuda-runtime/nvidia/cuda_runtime/lib/libcudart.so.12')
        self.cuda.cudaMalloc.argtypes = [c.POINTER(c.c_void_p), c.c_size_t]
        self.cuda.cudaFree.argtypes = [c.c_void_p]
        self.cuda.cudaMemcpyAsync.argtypes = [c.c_void_p,c.c_void_p,c.c_size_t,c.c_int,c.c_void_p]
        self.cuda.cudaStreamCreateWithPriority.argtypes = [c.POINTER(c.c_void_p),c.c_uint,c.c_int]
        self.cuda.cudaStreamSynchronize.argtypes = [c.c_void_p]
        self.cuda.cudaStreamDestroy.argtypes = [c.c_void_p]
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine((Path(root) / 'driving_gta_trt.plan').read_bytes())
        if self.engine is None:
            raise RuntimeError('Cannot deserialize the Cinque CUDA engine')
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError('Cannot create Cinque execution context')
        self.stream = c.c_void_p()
        self.check(self.cuda.cudaStreamCreateWithPriority(c.byref(self.stream), 1, -1))
        self.buffers = {}
        self.input_specs = {}
        self.output = None
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(name)))
            if any(d < 1 for d in shape):
                raise ValueError(f'Dynamic tensor not supported: {name} {shape}')
            size = int(np.prod(shape)) * dtype.itemsize
            pointer = c.c_void_p()
            self.check(self.cuda.cudaMalloc(c.byref(pointer), size))
            self.buffers[name] = (pointer,size)
            if not self.context.set_tensor_address(name,pointer.value):
                raise RuntimeError(f'Cannot bind {name}')
            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.input_specs[name] = (shape,dtype)
            else:
                if self.output is not None:
                    raise ValueError('Unexpected multiple model outputs')
                self.output = np.empty(shape,dtype)
                self.output_name = name
        if set(values) != set(self.input_specs):
            raise ValueError('Unexpected Cinque input names')

    def close(self):
        if getattr(self, 'stream', None):
            self.cuda.cudaStreamSynchronize(self.stream)
            for pointer, _ in getattr(self, 'buffers', {}).values():
                self.cuda.cudaFree(pointer)
            self.buffers = {}
            self.cuda.cudaStreamDestroy(self.stream)
            self.stream = None

    def __del__(self):
        self.close()

    @staticmethod
    def check(result):
        if result:
            raise RuntimeError(f'CUDA runtime error {result}')

    def __call__(self, values):
        for name,(shape,dtype) in self.input_specs.items():
            array = values[name]
            if array.shape != shape or array.dtype != dtype or not array.flags.c_contiguous:
                raise ValueError(f'Incorrect input buffer: {name}')
            pointer,size = self.buffers[name]
            self.check(self.cuda.cudaMemcpyAsync(pointer,c.c_void_p(array.ctypes.data),size,1,self.stream))
        if not self.context.execute_async_v3(self.stream.value):
            raise RuntimeError('TensorRT inference failed')
        pointer,size = self.buffers[self.output_name]
        self.check(self.cuda.cudaMemcpyAsync(c.c_void_p(self.output.ctypes.data),pointer,size,2,self.stream))
        self.check(self.cuda.cudaStreamSynchronize(self.stream))
        return self.output.astype(np.float32)
