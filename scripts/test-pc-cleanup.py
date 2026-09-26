"""Exercise the patched cleanup boundary without starting driving processes."""
import ast
import os
import tempfile
from pathlib import Path

source = Path('/data/openpilot/frogpilot/common/frogpilot_utilities.py').read_text()
tree = ast.parse(source)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'delete_file')
namespace = {'os': os, 'Path': Path}
exec(compile(ast.Module(body=[function], type_ignores=[]), '<patched cleanup>', 'exec'), namespace)
delete = namespace['delete_file']
os.environ['GTA_SIMULATION'] = '1'
with tempfile.TemporaryDirectory(dir='/data') as local, tempfile.TemporaryDirectory() as external:
    inside, outside = Path(local), Path(external)
    sentinel = outside / 'preserve.txt'
    sentinel.write_text('preserve')
    link = inside / 'theme'
    link.symlink_to(outside, target_is_directory=True)
    delete(link)
    assert sentinel.read_text() == 'preserve' and not link.is_symlink()
    for forbidden in (sentinel, Path('/data'), Path('/data/example/..')):
        try:
            delete(forbidden)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Unprotected deletion: {forbidden}')
    link.symlink_to(outside, target_is_directory=True)
    try:
        delete(link / sentinel.name)
    except ValueError:
        pass
    else:
        raise AssertionError('Parent symlink escaped owned storage')
    child = inside / 'assets'
    child.mkdir()
    (child / 'test.txt').write_text('temporary')
    delete(child)
    assert not child.exists() and sentinel.exists()
print('PASS: owned cleanup, symlink target preservation, root and traversal boundaries')
