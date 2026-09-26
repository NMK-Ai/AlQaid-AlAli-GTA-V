#!/usr/bin/env python3
"""rebrand_ar.py — NMK rebranding layer for FrogPilot-GTA / القائد الآلي.

Rules approved by Nasser (2026-09-25 17:28):
  openpilot / OpenPilot / OPENPILOT  -> القائد الآلي
  FrogPilot / FROGPILOT / frogpilot  -> NMK.AI
  comma / comma.ai                   -> NMK.AI
  sunnypilot / dragonpilot           -> القائد الآلي

Applies ONLY to translated message strings (msgstr) and selected UI source
strings in .po files; never touches code identifiers, file paths, comments
(#: lines), or placeholders.

Usage:
  python rebrand_ar.py --check <file.po>     # report only, no changes
  python rebrand_ar.py --apply <file.po>     # rewrite in place (backup .bak)
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

REPLACEMENTS = [
    (r'\bopenpilot\b', 'القائد الآلي'),
    (r'\bOpenPilot\b', 'القائد الآلي'),
    (r'\bOPENPILOT\b', 'القائد الآلي'),
    (r'\bFrogPilot\b', 'NMK.AI'),
    (r'\bFROGPILOT\b', 'NMK.AI'),
    (r'\bfrogpilot\b', 'NMK.AI'),
    (r'\bsunnypilot\b', 'القائد الآلي'),
    (r'\bdragonpilot\b', 'القائد الآلي'),
    (r'\bcomma\.ai\b', 'NMK.AI'),
    (r'\bcomma\b', 'NMK.AI'),
]

# Lines that must never be modified
SKIP_PREFIXES = ('#:', '#.', '#|', 'msgid ')  # keep msgid intact for matching


def rebrand_line(line: str):
    changed = []
    new = line
    for pat, rep in REPLACEMENTS:
        def sub(m, rep=rep):
            return rep
        out = re.sub(pat, sub, new)
        if out != new:
            changed.append((pat, rep))
        new = out
    return new, changed


def process(path: Path, apply: bool):
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines(keepends=True)
    in_msgstr = False
    total = 0
    details = {}
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith('msgid'):
            in_msgstr = False
        elif stripped.startswith('msgstr'):
            in_msgstr = True
        elif stripped.startswith('"') and in_msgstr:
            pass
        else:
            continue
        if not in_msgstr:
            continue
        new, changed = rebrand_line(line)
        if changed:
            total += 1
            for pat, rep in changed:
                details[f'{pat} -> {rep}'] = details.get(f'{pat} -> {rep}', 0) + 1
            lines[i] = new
    print(f'{path}: {total} msgstr lines affected')
    for k, v in sorted(details.items(), key=lambda x: -x[1]):
        print(f'  {k}: {v}x')
    if apply and total:
        shutil.copy2(path, path.with_suffix(path.suffix + '.bak'))
        path.write_text(''.join(lines), encoding='utf-8')
        print('APPLIED (backup saved)')
    elif not apply:
        print('CHECK ONLY (use --apply to change)')
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['--check', '--apply'])
    ap.add_argument('files', nargs='+')
    args = ap.parse_known_args()[0] if False else None
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('files', nargs='+')
    a = ap.parse_args()
    if a.check == a.apply:
        print('choose exactly one of --check / --apply'); sys.exit(2)
    grand = 0
    for f in a.files:
        grand += process(Path(f), a.apply)
    print(f'TOTAL: {grand} lines {"rebranded" if a.apply else "flagged"}')


if __name__ == '__main__':
    main()
