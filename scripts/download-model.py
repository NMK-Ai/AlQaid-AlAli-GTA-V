"""Fetch immutable upstream model files and verify them before any pickle load."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[1]

def download(destination=Path('/data/gta-models/macrostiff')):
    manifest = json.loads((PROJECT/'config/macrostiff-manifest.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    revision = manifest['revision']
    for item in manifest['files']:
        target = destination/item['name']
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']:
            continue
        folder = 'uncompiled' if target.suffix == '.onnx' else 'compiled'
        url = f'https://raw.githubusercontent.com/FrogAi/FrogPilot-Resources/{revision}/{folder}/macrostiff_{target.name}'
        print(f'Downloading {target.name}', flush=True)
        temporary = target.with_suffix(target.suffix+'.download')
        digest = hashlib.sha256()
        try:
            with urlopen(url, timeout=120) as response, temporary.open('wb') as output:
                while block := response.read(1024*1024):
                    digest.update(block)
                    output.write(block)
            if temporary.stat().st_size != item['bytes'] or digest.hexdigest() != item['sha256']:
                raise ValueError(f'Model download verification failed: {target.name}')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    (destination/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')

if __name__ == '__main__':
    download()
