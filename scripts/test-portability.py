"""Source checks and real upstream patch regression without running the game/GPU."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PortableSourceTests(unittest.TestCase):
    def test_python_syntax(self):
        for folder in ('bridge', 'scripts'):
            for path in (ROOT/folder).glob('*.py'):
                with self.subTest(file=path.name):
                    ast.parse(path.read_text(encoding='utf-8-sig'))

    def test_no_original_machine_paths(self):
        for folder in ('bridge', 'scripts', 'native', 'config'):
            for path in (ROOT/folder).rglob('*'):
                if not path.is_file() or path.suffix not in ('.py','.ps1','.sh','.cpp','.h','.json','.txt') or path.name=='local.json':
                    continue
                with self.subTest(file=str(path.relative_to(ROOT))):
                    text=path.read_text(encoding='utf-8-sig')
                    for original in ('/mnt/'+'f/OpenPilot_GTAV_Enhanced', 'F:'+r'\OpenPilot_GTAV_Enhanced', 'C:'+r'\Users\frank'):
                        self.assertNotIn(original, text)

    def test_default_configuration_is_portable(self):
        config=json.loads((ROOT/'config/project.json').read_text())
        self.assertIsNone(config['gameDirectory'])
        self.assertIsNone(config['steamExecutable'])
        self.assertRegex(config['frogpilot']['commit'], r'^[0-9a-f]{40}$')
        self.assertRegex(config['ubuntu']['sha256'], r'^[0-9a-f]{64}$')
        model=json.loads((ROOT/'config/macrostiff-manifest.json').read_text())
        self.assertEqual(len(model['files']),4)
        for item in model['files']:
            self.assertEqual(Path(item['name']).name,item['name'])
            self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')

    def test_private_directories_are_ignored(self):
        rules=(ROOT/'.gitignore').read_text().splitlines()
        for rule in ('/runtime/','/reports/','/vendor/','/downloads/','/build/','/.venv/','/config/local.json'):
            self.assertIn(rule,rules)

def check_upstream(upstream):
    expected=json.loads((ROOT/'config/project.json').read_text())['frogpilot']['commit']
    actual=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if actual != expected:
        raise ValueError('Upstream test checkout must match the configured pin')
    files=['frogpilot/common/frogpilot_functions.py','frogpilot/common/frogpilot_utilities.py',
           'frogpilot/common/frogpilot_variables.py','frogpilot/ui/qt/offroad/frogpilot_settings.cc',
           'frogpilot/ui/qt/offroad/frogpilot_settings.h','frogpilot/ui/qt/offroad/longitudinal_settings.cc',
           'selfdrive/controls/controlsd.py','selfdrive/controls/lib/latcontrol_angle.py',
           'selfdrive/locationd/lagd.py','selfdrive/modeld/modeld.py','selfdrive/selfdrived/selfdrived.py',
           'system/manager/manager.py','system/manager/process_config.py','opendbc/car/car_helpers.py']
    with tempfile.TemporaryDirectory(prefix='FrogPilot patch test with spaces ') as directory:
        scratch=Path(directory); (scratch/'tools').mkdir()
        for name in files:
            source='opendbc_repo/'+name if name.startswith('opendbc/') else name
            data=subprocess.check_output(['git','-C',str(upstream),'show',f'{expected}:{source}'])
            target=scratch/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
        environment={**os.environ,'GTA_OPENPILOT_ROOT':str(scratch)}
        command=[sys.executable,str(ROOT/'scripts/apply-pc-patches.py')]
        subprocess.run(command,env=environment,check=True)
        hashes=lambda:{str(p.relative_to(scratch)):hashlib.sha256(p.read_bytes()).hexdigest() for p in scratch.rglob('*') if p.is_file()}
        first=hashes()
        subprocess.run(command,env=environment,check=True)
        if hashes()!=first: raise AssertionError('Patch application is not idempotent')
        for path in scratch.rglob('*.py'): ast.parse(path.read_text())
    print('Pinned upstream patches apply cleanly and idempotently in a path containing spaces.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--upstream',type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PortableSourceTests))
    if not result.wasSuccessful(): raise SystemExit(1)
    if args.upstream: check_upstream(args.upstream)
