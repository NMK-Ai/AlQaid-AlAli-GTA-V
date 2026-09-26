"""Fail closed on incompatible model selections and changed compiled weights."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'bridge'), str(ROOT / 'scripts')]
from gta_regular_model import selected_profile, model_paths, RegularModelStatus
from gta_regular_model_patch import patch_regular_model


class RegularModelContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.names = ('driving_vision_gta_cuda.pkl', 'driving_policy_gta_cuda.pkl',
                      'driving_vision_metadata.pkl', 'driving_policy_metadata.pkl')
        for name in self.names:
            (self.root/name).write_bytes(name.encode())
        self.profile = dict(id='macrostiff', name='Macrostiff', backend='CUDA', validated=True,
                            checkpoint={'vision': 'v', 'policy': 'p'},
                            artifacts={n: hashlib.sha256((self.root/n).read_bytes()).hexdigest() for n in self.names})
        self.save_profile()
        env = patch.dict(os.environ, {'GTA_SIMULATION': '1', 'SIMULATION': '1',
                        'GTA_REGULAR_MODEL': str(self.root), 'GTA_BIG_MODEL': '',
                        'GTA_REGULAR_MODEL_STATUS': str(self.root/'status.json')})
        env.start()
        self.addCleanup(env.stop)

    def save_profile(self):
        (self.root/'profile.json').write_text(json.dumps(self.profile))

    def test_only_simulation_selects_model(self):
        for key in ('GTA_SIMULATION', 'SIMULATION'):
            with patch.dict(os.environ, {key: '0'}):
                self.assertIsNone(selected_profile())
        with patch.dict(os.environ, {'GTA_REGULAR_MODEL': ''}):
            self.assertIsNone(model_paths())

    def test_verified_pair_and_metadata_are_selected_together(self):
        self.assertEqual(model_paths(), tuple(self.root/n for n in self.names))

    def test_changed_weights_or_metadata_fail_closed(self):
        for name in self.names:
            original = (self.root/name).read_bytes()
            (self.root/name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                selected_profile()
            (self.root/name).write_bytes(original)

    def test_unvalidated_or_other_backend_rejected(self):
        for key, value in [('validated', False), ('backend', 'QCOM'), ('id', 'other')]:
            original = self.profile[key]
            self.profile[key] = value
            self.save_profile()
            with self.assertRaisesRegex(ValueError, 'Unvalidated'):
                selected_profile()
            self.profile[key] = original

    def test_cannot_load_regular_and_big_simultaneously(self):
        with patch.dict(os.environ, {'GTA_BIG_MODEL': '/some/big/model'}):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                selected_profile()

    def test_heartbeat_identifies_actual_process_and_completed_runs(self):
        status = RegularModelStatus()
        status.publish()
        data = json.loads((self.root/'status.json').read_text())
        self.assertEqual(data['pid'], os.getpid())
        self.assertEqual(data['runs'], 1)
        self.assertEqual(data['artifacts'], self.profile['artifacts'])
        self.assertEqual(data['checkpoint'], self.profile['checkpoint'])

    def test_patch_is_idempotent_and_valid_on_installed_source(self):
        source = Path('/data/openpilot/selfdrive/modeld/modeld.py').read_text()
        candidate = patch_regular_model(source)
        ast.parse(candidate)
        self.assertEqual(candidate, patch_regular_model(candidate))
        self.assertIn('class ModelState:', candidate)
        self.assertIn('self.full_input_queues.enqueue', candidate)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
            patch_regular_model('incompatible upstream')


if __name__ == '__main__':
    unittest.main()
