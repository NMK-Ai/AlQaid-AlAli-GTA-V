"""Select regular CUDA model artifacts without replacing FrogPilot's ModelState."""
def patch_regular_model(source):
    marker = '  # GTA_REGULAR_MODEL_PATHS'
    if marker in source:
        return source
    replacements = [
        ("POLICY_METADATA_PATH = Path(__file__).parent / 'models/driving_policy_metadata.pkl'\n",
         "POLICY_METADATA_PATH = Path(__file__).parent / 'models/driving_policy_metadata.pkl'\n"
         "if os.getenv('GTA_SIMULATION') == os.getenv('SIMULATION') == '1' and os.getenv('GTA_REGULAR_MODEL'):\n"
         "  # GTA_REGULAR_MODEL_PATHS\n"
         "  from openpilot.tools.gta.gta_regular_model import model_paths\n"
         "  VISION_PKL_PATH, POLICY_PKL_PATH, VISION_METADATA_PATH, POLICY_METADATA_PATH = model_paths()\n"),
        ('      self.policy_run = pickle.load(f)\n',
         '      self.policy_run = pickle.load(f)\n'
         '    self.gta_regular_status = None\n'
         '    if os.getenv("GTA_SIMULATION") == os.getenv("SIMULATION") == "1" and os.getenv("GTA_REGULAR_MODEL"):\n'
         '      from openpilot.tools.gta.gta_regular_model import RegularModelStatus\n'
         '      self.gta_regular_status = RegularModelStatus()\n'),
        ('    return combined_outputs_dict\n',
         '    if self.gta_regular_status is not None:\n'
         '      self.gta_regular_status.publish()\n'
         '    return combined_outputs_dict\n')]
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError('Unexpected regular modeld source; review before patching')
        source = source.replace(before, after, 1)
    return source
