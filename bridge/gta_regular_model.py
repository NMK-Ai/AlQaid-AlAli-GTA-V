"""Verified regular-model paths and live identity for the GTA CUDA runtime."""
import hashlib
import json
import os
from pathlib import Path
import time


def selected_profile():
    if not (os.getenv('GTA_SIMULATION') == os.getenv('SIMULATION') == '1'):
        return None
    selection = os.getenv('GTA_REGULAR_MODEL')
    if not selection:
        return None
    if os.getenv('GTA_BIG_MODEL'):
        raise ValueError('Select exactly one driving model')
    root = Path(selection).resolve()
    profile = json.loads((root/'profile.json').read_text())
    if profile.get('id') != 'macrostiff' or profile.get('backend') != 'CUDA' or not profile.get('validated'):
        raise ValueError('Unvalidated regular model profile')
    required = ('driving_vision_gta_cuda.pkl', 'driving_policy_gta_cuda.pkl',
                'driving_vision_metadata.pkl', 'driving_policy_metadata.pkl')
    for name in required:
        actual = hashlib.sha256((root/name).read_bytes()).hexdigest()
        if actual != profile['artifacts'].get(name):
            raise ValueError(f'Regular model artifact changed: {name}')
    return root, profile


def model_paths():
    selected = selected_profile()
    if selected is None:
        return None
    root, _ = selected
    return tuple(root/name for name in ('driving_vision_gta_cuda.pkl', 'driving_policy_gta_cuda.pkl',
                                       'driving_vision_metadata.pkl', 'driving_policy_metadata.pkl'))


class RegularModelStatus:
    def __init__(self):
        root, self.profile = selected_profile()
        self.root = str(root)
        self.runs = 0
        self.last = -10.
        self.path = Path(os.getenv('GTA_REGULAR_MODEL_STATUS', '/dev/shm/gta-regular-model-status.json'))

    def publish(self):
        self.runs += 1
        now = time.monotonic()
        if now-self.last < 1:
            return
        self.last = now
        value = dict(id=self.profile['id'], name=self.profile['name'], backend='CUDA',
                     pid=os.getpid(), monotonic=now, runs=self.runs, root=self.root,
                     artifacts=self.profile['artifacts'], checkpoint=self.profile['checkpoint'])
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(value))
        tmp.replace(self.path)
