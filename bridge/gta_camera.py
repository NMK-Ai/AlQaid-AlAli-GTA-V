"""Pair the narrow/wide views derived from exactly one GTA capture."""


def recv_matched_frames(main, extra, metadata):
    """Return a complete pair, or None on timeout/disconnect/backlog.

    The PC bridge publishes the same frame ID and timestamp for both views.
    Arrival intervals can be shorter than 25 ms after transport jitter; they
    are not a reliable way to decide whether the next frame is new.
    """
    main_buffer = main.recv()
    if main_buffer is None:
        return None
    main_meta = metadata(main)
    extra_buffer = extra.recv()
    if extra_buffer is None:
        return None
    extra_meta = metadata(extra)
    # Bound draining if a disconnected/changed stream cannot be paired. Never
    # return mismatched images or manufacture a new frame ID/timestamp.
    for _ in range(64):
        if main_meta.frame_id == extra_meta.frame_id:
            if main_meta.timestamp_sof != extra_meta.timestamp_sof:
                return None
            return main_buffer, main_meta, extra_buffer, extra_meta
        if main_meta.frame_id < extra_meta.frame_id:
            main_buffer = main.recv()
            if main_buffer is None:
                return None
            main_meta = metadata(main)
        else:
            extra_buffer = extra.recv()
            if extra_buffer is None:
                return None
            extra_meta = metadata(extra)
    return None
