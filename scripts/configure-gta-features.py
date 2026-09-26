"""Apply the user's requested simulation features once and preserve prior values."""
import json
from pathlib import Path
from openpilot.common.params import Params

root = Path(__file__).resolve().parents[1]
record = root / 'runtime/gta-feature-setup.json'
p = Params()
if not record.exists():
    desired = {'AlwaysOnLateral': True, 'ExperimentalMode': False, 'LaneChanges': True,
               'NudgelessLaneChange': True, 'UbloxAvailable': True}
    prior = {k: p.get(k) for k in desired}
    record.write_text(json.dumps({'previous': prior, 'requested': desired}, indent=2, default=str))
    for key, value in desired.items():
        p.put_bool(key, value)
    # No commands were applied during the Honda bring-up. Preserve its false
    # excessive-actuation latch before starting the corrected GTA profile.
    old = p.get('Offroad_ExcessiveActuation')
    if old is not None:
        (root / 'reports/honda-bringup-excessive-actuation.txt').write_text(str(old))
        p.remove('Offroad_ExcessiveActuation')
    print('Requested GTA features configured; previous values preserved.')
else:
    print('Feature preferences already initialized; preserving subsequent UI changes.')

# New explicit user preferences. Apply once, retaining prior values and any
# subsequent choices made in the actual UI.
override_record = root / 'runtime/gta-override-setup.json'
if not override_record.exists():
    desired = {'DisengageOnAccelerator': False, 'AlwaysOnLateral': True, 'PauseAOLOnBrake': 0}
    previous = {k: p.get(k) for k in desired}
    override_record.write_text(json.dumps({'previous': previous, 'requested': desired}, indent=2, default=str))
    for key, value in desired.items():
        if isinstance(value, bool):
            p.put_bool(key, value)
        else:
            p.put(key, value)
    print('Accelerator override and steering-through-braking preferences configured.')
