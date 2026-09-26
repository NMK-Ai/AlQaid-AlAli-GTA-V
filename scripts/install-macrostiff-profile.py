"""Activate only the validated pair, with the project's Linux runtime stopped."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

project = Path(__file__).resolve().parents[1]
checkout = Path('/data/openpilot')
models = Path('/data/gta-models/macrostiff')
for entry in Path('/proc').iterdir():
    if entry.name.isdigit():
        try:
            command = (entry/'cmdline').read_bytes().replace(b'\0', b' ')
        except (FileNotFoundError, PermissionError):
            continue
        if command.startswith(b'selfdrive.modeld.modeld') or command.startswith(b'python manager.py'):
            raise RuntimeError('Stop the FrogPilot runtime before installation')
validation = json.loads((models/'validation.json').read_text())
assert validation['passed'] and len(validation['cases']) == 3
assert validation['pair_inference_ms']['95'] < 40
for name, expected in validation['artifacts'].items():
    assert hashlib.sha256((models/name).read_bytes()).hexdigest() == expected
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-macrostiff')
backup = project/'runtime/model-backups'/stamp
backup.mkdir(parents=True)
relative_files = ['selfdrive/modeld/modeld.py','frogpilot/common/frogpilot_variables.py']
for relative in relative_files:
    target = backup/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(checkout/relative,target)
selection = project/'runtime/model-profile.txt'
previous = selection.read_text().strip() if selection.exists() else 'default'
(backup/'model-profile.txt').write_text(previous+'\n')
profile = dict(id='macrostiff',name='Macrostiff',backend='CUDA',precision='FP32',validated=True,
               artifacts=validation['artifacts'],
               checkpoint=dict(vision='6a7d09ad-bcc9-43bc-916d-29287e60cee2/200',
                               policy='8c06e95e-d7c0-4fd9-ba02-9f0b6848785e/400'))
(models/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
patch_command = [sys.executable,str(project/'scripts/apply-pc-patches.py')]
subprocess.run(patch_command,check=True)
first = {r:hashlib.sha256((checkout/r).read_bytes()).hexdigest() for r in relative_files}
subprocess.run(patch_command,check=True)
assert first == {r:hashlib.sha256((checkout/r).read_bytes()).hexdigest() for r in relative_files}
selection.write_text('macrostiff\n')
report = dict(selected_profile='macrostiff',previous_profile=previous,backup=str(backup),
              artifacts=validation['artifacts'],patch_idempotence=True,restart_required=True)
(project/'reports/macrostiff-profile-install.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
