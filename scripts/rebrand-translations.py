#!/usr/bin/env python3
"""Rebrand Arabic UI translations for the NMK-Ai / القائد الآلي distribution.

Applies the approved terminology (references/terminology.md) to translated
strings only:
  - openpilot / FrogPilot  -> القائد الآلي
  - comma family           -> NMK branding
  - connect.comma.ai       -> connect.nmk.ai

Never touches <source> elements (lookup keys), msgid lines, XML structure,
placeholders (%1, %n, \\n) or attribute names. Output is built by appending
(never splicing), so indices cannot shift. Idempotent: safe to re-run.

Usage: rebrand-translations.py [--report-only] [--translations-dir DIR]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

TRANSLATIONS = pathlib.Path('/data/openpilot/selfdrive/ui/translations')
TS_FILES = ['main_ar.ts']
PO_FILES = ['app_ar.po']

# Ordered plain replacements (longest / most specific first).
PLAIN = [
    ('connect.comma.ai', 'connect.nmk.ai'),
    ('comma.ai', 'NMK Ai'),
    ('Comma Connect', 'NMK Connect'), ('comma connect', 'NMK Connect'),
    ('Comma Prime', 'NMK Prime'), ('comma prime', 'NMK Prime'),
    ('Comma 3X', 'جهاز NMK'), ('comma 3X', 'جهاز NMK'),
    ('Comma 3', 'جهاز NMK'), ('comma 3', 'جهاز NMK'),
    ('FROGPILOT', 'القائد الآلي'),
    ('FrogPilot', 'القائد الآلي'),
    ('Frogpilot', 'القائد الآلي'),
    ('OpenPilot', 'القائد الآلي'),
    ('OPENPILOT', 'القائد الآلي'),
    ('openpilot', 'القائد الآلي'),
    # Grammar cleanups after brand substitution.
    ('لـ القائد الآلي', 'للقائد الآلي'),
    ('للقائد القائد الآلي', 'للقائد الآلي'),
]
# Standalone "comma" as a whole word (avoids commands, commas, etc.)
WORD_COMMA = re.compile(r'\b(?:comma|Comma|COMMA)\b')

TS_FULL = re.compile(
    r'^(?P<pre>\s*<(?:translation|numerusform)\b[^>]*>)(?P<text>.*)(?P<post></(?:translation|numerusform)>\s*)$')
TS_OPEN = re.compile(r'^(\s*<(?:translation|numerusform)\b[^>]*>)(.*)$')
TS_CLOSE = re.compile(r'</(?:translation|numerusform)>')
PO_MSGSTR = re.compile(r'^(msgstr(?:\[\d+\])?)\s+"(.*)"\s*$')
PO_CONT = re.compile(r'^"(.*)"\s*$')


def rebrand(text: str) -> str:
    for a, b in PLAIN:
        text = text.replace(a, b)
    text = WORD_COMMA.sub('NMK', text)
    text = text.replace('لـ القائد الآلي', 'للقائد الآلي')
    return text


def fix_ts(path: pathlib.Path, report_only: bool) -> int:
    """Rebrand translation text, including multi-line translation blocks."""
    changed = 0
    out: list[str] = []
    in_translation = False
    for line in path.read_text(encoding='utf-8').splitlines(keepends=False):
        if in_translation:
            close = TS_CLOSE.search(line)
            if close:
                text, post = line[:close.start()], line[close.start():]
                in_translation = False
            else:
                text, post = line, ''
            new = rebrand(text)
            if new != text:
                changed += 1
                line = new + post
            out.append(line)
            continue
        m = TS_FULL.match(line)
        if m and m.group('text'):
            new = rebrand(m.group('text'))
            if new != m.group('text'):
                changed += 1
                line = m.group('pre') + new + m.group('post')
            out.append(line)
            continue
        om = TS_OPEN.match(line)
        if om and not TS_CLOSE.search(line):
            new = rebrand(om.group(2))
            if new != om.group(2):
                changed += 1
                line = om.group(1) + new
            in_translation = True
        out.append(line)
    if changed and not report_only:
        path.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return changed


def fix_po(path: pathlib.Path, report_only: bool) -> tuple[int, list[str]]:
    """Rebrand msgstr blocks (incl. plural forms and continuations) safely."""
    lines = path.read_text(encoding='utf-8').splitlines(keepends=False)
    changed = 0
    untranslated: list[str] = []
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = PO_MSGSTR.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        prefix, text = m.group(1), m.group(2)
        block = [lines[i]]
        j = i + 1
        while j < len(lines):
            cm = PO_CONT.match(lines[j])
            if not cm:
                break
            text += cm.group(1)
            block.append(lines[j])
            j += 1
        new = rebrand(text)
        if new != text:
            changed += 1
            if not report_only:
                out.append(f'{prefix} "{new}"')
            else:
                out.extend(block)
        else:
            if not text.strip():
                untranslated.append(text)
            out.extend(block)
        i = j
    if changed and not report_only:
        path.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return changed, untranslated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--report-only', action='store_true')
    ap.add_argument('--translations-dir', default=str(TRANSLATIONS))
    args = ap.parse_args()
    root = pathlib.Path(args.translations_dir)

    total = 0
    for name in TS_FILES:
        p = root / name
        n = fix_ts(p, args.report_only)
        print(f'{name}: {n} translated strings rebranded')
        total += n
    for name in PO_FILES:
        p = root / name
        n, untranslated = fix_po(p, args.report_only)
        print(f'{name}: {n} msgstr rebranded, {len(untranslated)} empty msgstr')
        total += n
    mode = 'report' if args.report_only else 'applied'
    print(f'total changes: {total} ({mode})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
