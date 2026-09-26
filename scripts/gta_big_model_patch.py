"""Reversible, simulation-gated integration of a separately validated big model."""


def patch_big_model(source):
    marker = '  # GTA_BIG_MODEL_ADAPTER'
    if marker in source:
        return source
    old = '  model = ModelState(cl_context)'
    new = '''  # GTA_BIG_MODEL_ADAPTER
  use_gta_big_model = (os.getenv('GTA_SIMULATION') == os.getenv('SIMULATION') == '1'
                       and bool(os.getenv('GTA_BIG_MODEL')))
  if use_gta_big_model:
    from openpilot.tools.gta.gta_big_model import CinqueModelState
    model = CinqueModelState(cl_context)
  else:
    model = ModelState(cl_context)'''
    if source.count(old) != 1:
        raise ValueError('Unexpected model constructor source')
    source = source.replace(old, new, 1)
    old = "    plan = model_output['plan'][0]"
    new = '''    if (os.getenv('GTA_SIMULATION') == os.getenv('SIMULATION') == '1'
        and os.getenv('GTA_BIG_MODEL') and 'action' in model_output):
      from openpilot.tools.gta.gta_big_model import action_from_supercombo
      return action_from_supercombo(model_output, prev_action, v_ego)
    plan = model_output['plan'][0]'''
    if source.count(old) != 1:
        raise ValueError('Unexpected model action source')
    source = source.replace(old, new, 1)
    old = "      'traffic_convention': traffic_convention,\n    }"
    # Pinned Cinque upstream compensates a frame plus half the control interval.
    new = "      'traffic_convention': traffic_convention,\n      'action_t': np.array([lat_delay + 1.5 * DT_MDL, long_delay + 1.5 * DT_MDL], dtype=np.float32),\n    }"
    if source.count(old) != 1:
        raise ValueError('Unexpected model inputs source')
    source = source.replace(old, new, 1)
    old = '    prepare_only = vipc_dropped_frames > 0'
    if source.count(old) != 1:
        raise ValueError('Unexpected dropped-frame source')
    return source.replace(old, old + ' and not use_gta_big_model', 1)
