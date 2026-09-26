"""Exercise the installed selfdrived branches with simulated and ordinary profiles."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

source = ast.parse(Path('/data/openpilot/selfdrive/selfdrived/selfdrived.py').read_text())
cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'SelfdriveD')
init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
assignments = [n for n in init.body if isinstance(n, ast.Assign) and any(
    isinstance(t, ast.Attribute) and t.attr in {'excessive_actuation_enabled', 'excessive_actuation'}
    for t in n.targets)]
branches = [n for method in cls.body if isinstance(method, ast.FunctionDef)
            for n in method.body if isinstance(n, ast.If)
            and 'self.excessive_actuation_enabled' in ast.unparse(n.test)]
assert len(assignments) == len(branches) == 2
code = compile(ast.Module(body=assignments + branches, type_ignores=[]), '<installed selfdrived branches>', 'exec')
for brand, fingerprint, gta, simulation, disabled in [
    ('gta', 'GTA_V', '1', '1', True),
    ('gta', 'GTA_V', '0', '1', False),
    ('gta', 'GTA_V', '1', '0', False),
    ('honda', 'CIVIC', '1', '1', False),
    ('gta', 'OTHER', '1', '1', False),
]:
    for stored in (None, 'old fault'):
        check = Mock()
        check.update.return_value = 'longitudinal'
        obj = SimpleNamespace(CP=SimpleNamespace(brand=brand, carFingerprint=fingerprint),
                              params=SimpleNamespace(get=lambda key: stored),
                              calibrated_pose=object(), excessive_actuation_check=check,
                              sm=object(), events=Mock())
        with patch.dict(os.environ, GTA_SIMULATION=gta, SIMULATION=simulation):
            exec(code, {'self': obj, 'os': os, 'CS': object(),
                        'set_offroad_alert': Mock(), 'EventName': SimpleNamespace(excessiveActuation='fault')})
        assert obj.excessive_actuation_enabled is not disabled
        assert obj.excessive_actuation is not disabled
        assert check.update.call_count == int(not disabled)
        assert obj.events.add.call_count == int(not disabled)
print('10 installed-branch cases passed: GTA skips new and stored faults; other launch/profile combinations retain both.')
