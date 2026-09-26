"""Check exact pairing against jitter, dropped views, and disconnects."""
import sys
import os
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from gta_camera import recv_matched_frames
from gta_camera_patch import patch_modeld, MARKER, END


class Client:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.calls = 0

    def recv(self):
        self.calls += 1
        item = next(self.frames, None)
        if item is None:
            return None
        self.frame_id, self.timestamp_sof = item
        return ('image', self.frame_id)


def meta(client):
    return SimpleNamespace(frame_id=client.frame_id, timestamp_sof=client.timestamp_sof)


class PairingTests(unittest.TestCase):
    def test_recorded_jitter_does_not_skip_a_valid_pair(self):
        # Real roadCameraState receipt timestamps around a 220 ms model gap.
        times = [409405987619, 409430562349, 409503572171,
                 409523433163, 409583681294, 409628483655]
        frames = list(zip(range(4820, 4826), times))
        main, extra = Client(frames), Client(frames)
        paired = [recv_matched_frames(main, extra, meta) for _ in frames]
        self.assertEqual([p[1].frame_id for p in paired], list(range(4820, 4826)))
        self.assertEqual(main.calls, len(frames))
        self.assertEqual(extra.calls, len(frames))

    def test_main_conflation_drains_old_extra(self):
        pair = recv_matched_frames(Client([(5, 500)]), Client([(3, 300), (4, 400), (5, 500)]), meta)
        self.assertEqual((pair[1].frame_id, pair[3].frame_id), (5, 5))

    def test_missing_extra_advances_main_to_a_complete_pair(self):
        pair = recv_matched_frames(Client([(3, 300), (5, 500)]), Client([(5, 500)]), meta)
        self.assertEqual((pair[1].frame_id, pair[3].frame_id), (5, 5))

    def test_timeouts_never_reuse_previous_images(self):
        for main, extra in [(Client([]), Client([(1, 1)])),
                            (Client([(1, 1)]), Client([])),
                            (Client([(2, 2)]), Client([(1, 1)]))]:
            self.assertIsNone(recv_matched_frames(main, extra, meta))

    def test_mismatched_timestamps_rejected(self):
        self.assertIsNone(recv_matched_frames(Client([(1, 10)]), Client([(1, 11)]), meta))

    def test_unbounded_backlog_is_not_drained_forever(self):
        extra = Client([(x, x) for x in range(200)])
        self.assertIsNone(recv_matched_frames(Client([(199, 199)]), extra, meta))
        self.assertLessEqual(extra.calls, 65)


@unittest.skipUnless(Path('/data/openpilot/selfdrive/modeld/modeld.py').exists(), 'Run in the real FrogPilot environment')
class ModelIntegrationTests(unittest.TestCase):
    def test_pinned_model_patch_compiles_and_is_idempotent(self):
        source = Path('/data/openpilot/selfdrive/modeld/modeld.py').read_text()
        changed = patch_modeld(source)
        compile(changed, 'candidate-modeld.py', 'exec')
        self.assertEqual(patch_modeld(changed), changed)

    def test_real_model_camera_branch_requires_profile_and_both_flags(self):
        source = patch_modeld(Path('/data/openpilot/selfdrive/modeld/modeld.py').read_text())
        first = source.index(MARKER)
        camera_block = source[first:source.index(END, first)]
        # Execute the actual patched synchronization block, with deterministic
        # VisionIPC stand-ins. Nothing in the running model process is changed.
        for brand, gta, simulation in [('gta','1','1'), ('gta','0','1'),
                                       ('gta','1','0'), ('honda','1','1')]:
            frames = [(2,120_000_000),(3,180_000_000)]
            scope = dict(CP=SimpleNamespace(brand=brand), os=os, use_extra_client=True,
                         vipc_client_main=Client(frames), vipc_client_extra=Client(frames),
                         FrameMeta=meta, meta_main=SimpleNamespace(timestamp_sof=100_000_000),
                         meta_extra=SimpleNamespace(timestamp_sof=100_000_000),
                         cloudlog=SimpleNamespace(error=lambda *a:None,debug=lambda *a:None))
            with patch.dict(os.environ, GTA_SIMULATION=gta, SIMULATION=simulation), \
                 patch.dict(sys.modules, {'openpilot.tools.gta.gta_camera':sys.modules['gta_camera']}):
                exec('while True:\n'+camera_block+'    break\n', scope)
            expected = 2 if (brand,gta,simulation)==('gta','1','1') else 3
            self.assertEqual(scope['meta_main'].frame_id, expected)
            self.assertEqual(scope['meta_extra'].frame_id, expected)


if __name__ == '__main__':
    unittest.main()
