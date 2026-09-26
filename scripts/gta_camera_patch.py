"""Idempotent, GTA-only camera synchronization change for the pinned modeld."""

START = '    # Keep receiving frames until we are at least 1 frame ahead of previous extra frame\n'
END = '    sm.update(0)\n'
MARKER = '    # GTA publishes two views of one capture, paired by frame ID.\n'


def patch_modeld(source):
    if MARKER in source:
        return source
    if source.count(START) != 1:
        raise RuntimeError('Unexpected modeld camera synchronization source')
    first = source.index(START)
    last = source.index(END, first)
    original = source[first:last]
    branch = (
        MARKER +
        '    if (CP.brand == "gta" and os.getenv("GTA_SIMULATION") == "1" and\n'
        '        os.getenv("SIMULATION") == "1" and use_extra_client):\n'
        '      from openpilot.tools.gta.gta_camera import recv_matched_frames\n'
        '      pair = recv_matched_frames(vipc_client_main, vipc_client_extra, FrameMeta)\n'
        '      if pair is None:\n'
        '        continue\n'
        '      buf_main, meta_main, buf_extra, meta_extra = pair\n'
        '    else:\n' + ''.join('  '+line if line.strip() else line for line in original.splitlines(True)))
    return source[:first]+branch+source[last:]
