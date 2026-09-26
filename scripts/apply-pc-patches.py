"""Apply narrowly scoped PC simulation support to the pinned Linux checkout."""
from pathlib import Path
import os
import shutil
from gta_camera_patch import patch_modeld
from gta_turn_rate_patch import patch_angle_feedback
from gta_big_model_patch import patch_big_model
from gta_delay_patch import patch_gta_delay
from gta_regular_model_patch import patch_regular_model

ROOT = Path(os.environ.get('GTA_OPENPILOT_ROOT', '/data/openpilot')).resolve()
gta_module = ROOT / 'tools/gta'
gta_module.mkdir(exist_ok=True)
(gta_module / '__init__.py').touch()
shutil.copyfile(Path(__file__).resolve().parents[1] / 'bridge/gta_interface.py', gta_module / 'gta_interface.py')
shutil.copyfile(Path(__file__).resolve().parents[1] / 'bridge/gta_lateral.py', gta_module / 'gta_lateral.py')
shutil.copyfile(Path(__file__).resolve().parents[1] / 'bridge/gta_camera.py', gta_module / 'gta_camera.py')
for module in ('gta_big_model.py', 'gta_trt.py', 'gta_regular_model.py'):
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'bridge' / module, gta_module / module)

def replace_once(relative: str, before: str, after: str) -> None:
    path = ROOT / relative
    content = path.read_text()
    if after in content:
        return
    if content.count(before) != 1:
        raise RuntimeError(f'Unexpected upstream source in {relative}; review the pin before patching')
    path.write_text(content.replace(before, after, 1))

lagd_path = ROOT / 'selfdrive/locationd/lagd.py'
lagd_path.write_text(patch_gta_delay(lagd_path.read_text()))

regular_modeld_path = ROOT / 'selfdrive/modeld/modeld.py'
regular_modeld_path.write_text(patch_regular_model(regular_modeld_path.read_text()))

replace_once('system/manager/process_config.py',
    'elif TICI:\n  procs.append(NativeProcess("ui", "selfdrive/ui", ["./ui"], always_run, watchdog_max_dt=5)),',
    'elif TICI:\n  procs.append(NativeProcess("ui", "selfdrive/ui", ["./ui"], always_run, watchdog_max_dt=5)),\n'
    'elif PC and os.getenv("GTA_SIMULATION") == "1":\n'
    '  procs.append(NativeProcess("ui", "selfdrive/ui", ["./ui"], always_run))')

replace_once('frogpilot/common/frogpilot_functions.py',
    'def update_boot_logo(frogpilot=False, stock=False):\n  boot_logo_location',
    'def update_boot_logo(frogpilot=False, stock=False):\n'
    '  # A desktop simulation has no comma device boot partition.\n'
    '  if HARDWARE.get_device_type() == "pc":\n'
    '    return\n'
    '  boot_logo_location')

replace_once('system/manager/manager.py',
    '  frogpilot_api.register_device(build_metadata)',
    '  if os.getenv("GTA_SIMULATION") != "1":\n'
    '    frogpilot_api.register_device(build_metadata)')

replace_once('frogpilot/common/frogpilot_utilities.py',
    'def delete_file(path, print_error=True, report=True):\n  path = Path(path)\n',
    'def delete_file(path, print_error=True, report=True):\n'
    '  path = Path(path)\n'
    '  if os.getenv("GTA_SIMULATION") == "1":\n'
    '    # Simulation assets are owned by the unprivileged Linux user.\n'
    '    # Resolve the parent only: removing a theme symlink must not remove its target.\n'
    '    import shutil\n'
    '    path = Path(os.path.abspath(path))\n'
    '    candidate = path.parent.resolve() / path.name\n'
    '    roots = (Path("/data"), Path("/cache"), Path("/persist"))\n'
    '    if not any(candidate.is_relative_to(root) and candidate != root for root in roots):\n'
    '      raise ValueError(f"Refusing simulation deletion outside owned storage: {path}")\n'
    '    if path.is_symlink() or path.is_file():\n'
    '      path.unlink()\n'
    '    elif path.is_dir():\n'
    '      shutil.rmtree(path)\n'
    '    elif print_error:\n'
    '      print(f"File not found: {path}")\n'
    '    return\n')

replace_once('selfdrive/modeld/modeld.py',
    "os.environ['DEV'] = 'QCOM' if TICI else 'CPU'",
    "os.environ['DEV'] = 'QCOM' if TICI else 'CPU'\n"
    "if not TICI and os.getenv('GTA_SIMULATION') == '1' and os.getenv('GTA_MODEL_BACKEND') == 'CUDA':\n"
    "  os.environ['DEV'] = 'CUDA'")

replace_once('selfdrive/modeld/modeld.py',
    "POLICY_PKL_PATH = Path(__file__).parent / 'models/driving_policy_tinygrad.pkl'\n",
    "POLICY_PKL_PATH = Path(__file__).parent / 'models/driving_policy_tinygrad.pkl'\n"
    "if os.getenv('GTA_SIMULATION') == '1' and os.getenv('GTA_MODEL_BACKEND') == 'CUDA':\n"
    "  VISION_PKL_PATH = Path(__file__).parent / 'models/driving_vision_gta_cuda.pkl'\n"
    "  POLICY_PKL_PATH = Path(__file__).parent / 'models/driving_policy_gta_cuda.pkl'\n")

replace_once('frogpilot/common/frogpilot_variables.py',
    'import math\n', 'import math\nimport os\n')
replace_once('frogpilot/common/frogpilot_variables.py',
    '    toggle.block_user = (self.development_branch or branch == "MAKE-PRS-HERE" or self.vetting_branch) and not self.frogs_go_moo\n',
    '    toggle.block_user = (self.development_branch or branch == "MAKE-PRS-HERE" or self.vetting_branch) and not self.frogs_go_moo\n'
    '    # Game simulation does not have a registered comma development device.\n'
    '    if os.getenv("GTA_SIMULATION") == "1" and os.getenv("SIMULATION") == "1" and HARDWARE.get_device_type() == "pc":\n'
    '      toggle.block_user = False\n')

replace_once('opendbc/car/car_helpers.py',
    'interfaces = load_interfaces(interface_names)\n',
    'interfaces = load_interfaces(interface_names)\n'
    'if os.getenv("GTA_SIMULATION") == "1" and os.getenv("SIMULATION") == "1":\n'
    '  from openpilot.tools.gta.gta_interface import CarInterface as GTACarInterface\n'
    '  interfaces["GTA_V"] = GTACarInterface\n')

lateral_old = ('    if self.CP.brand == "gta":\n'
    '      # GTA has no EPS torque/ISO actuation envelope. The game input range remains bounded.\n'
    '      self.desired_curvature, curvature_limited = float(new_desired_curvature), False\n'
    '    else:\n'
    '      self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)\n')
lateral_previous = ('    if self.CP.brand == "gta":\n'
    '      from openpilot.tools.gta.gta_lateral import shape_curvature\n'
    '      self.desired_curvature, curvature_limited = shape_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)\n'
    '    else:\n'
    '      self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)\n')
lateral_new = ('    if self.CP.brand == "gta":\n'
    '      from openpilot.tools.gta.gta_lateral import shape_curvature\n'
    '      from openpilot.tools.gta.gta_interface import MAX_WHEEL_ANGLE_DEG\n'
    '      self.desired_curvature, curvature_limited = shape_curvature(CS.vEgo, new_desired_curvature, self.CP.wheelbase, MAX_WHEEL_ANGLE_DEG)\n'
    '    else:\n'
    '      self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)\n')
lateral_content = (ROOT/'selfdrive/controls/controlsd.py').read_text()
if lateral_new not in lateral_content:
    if lateral_previous in lateral_content:
        replace_once('selfdrive/controls/controlsd.py', lateral_previous, lateral_new)
    elif lateral_old in lateral_content:
        replace_once('selfdrive/controls/controlsd.py', lateral_old, lateral_new)
    else:
        replace_once('selfdrive/controls/controlsd.py',
            '\n    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)\n',
            '\n'+lateral_new)

# A simulator's road-wheel angle has no steering column ratio or sensor offset.
# Keep the real angle controller/logs, but do not use OEM parameter learning to
# reinterpret a degree-valued actuator. Geometry is calibrated on the Krieger.
replace_once('selfdrive/controls/lib/latcontrol_angle.py',
    '    self.use_steer_limited_by_safety = CP.brand == "tesla"\n',
    '    self.use_steer_limited_by_safety = CP.brand == "tesla"\n'
    '    self.gta_wheelbase = CP.wheelbase if CP.brand == "gta" else None\n')
# Normalize the old GTA blocks before adding their current form. This also
# removes duplicates from a prior chained patch migration; upstream stays put.
for relative, anchor, old, new in [
    ('selfdrive/controls/lib/latcontrol_angle.py',
     '      angle_steers_des += params.angleOffsetDeg\n',
     '      if self.gta_wheelbase is not None:\n'
     '        from openpilot.tools.gta.gta_lateral import road_wheel_angle\n'
     '        angle_steers_des = road_wheel_angle(desired_curvature, self.gta_wheelbase)\n',
     '      if self.gta_wheelbase is not None:\n'
     '        from openpilot.tools.gta.gta_lateral import road_wheel_angle\n'
     '        angle_steers_des = road_wheel_angle(desired_curvature, self.gta_wheelbase, CS.vEgo)\n'),
    ('selfdrive/controls/controlsd.py',
     '    self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)\n',
     '    if self.CP.brand == "gta":\n'
     '      self.curvature = -math.tan(math.radians(CS.steeringAngleDeg)) / self.CP.wheelbase\n',
     '    if self.CP.brand == "gta":\n'
     '      from openpilot.tools.gta.gta_lateral import road_curvature\n'
     '      self.curvature = road_curvature(CS.steeringAngleDeg, self.CP.wheelbase, CS.vEgo)\n'),
]:
    path = ROOT/relative
    content = path.read_text()
    if relative.endswith('latcontrol_angle.py') and 'self.gta_turn_rate.update(' in content:
        continue
    normalized = content.replace(old, '').replace(new, '')
    if normalized.count(anchor) != 1:
        raise RuntimeError(f'Unexpected GTA lateral patch anchor in {relative}')
    updated = normalized.replace(anchor, anchor+new, 1)
    if updated != content:
        path.write_text(updated)

replace_once('selfdrive/controls/lib/latcontrol_angle.py',
    '    if self.use_steer_limited_by_safety:\n',
    '    if self.gta_wheelbase is not None:\n'
    '      # A road-wheel tracking error is not EPS torque saturation. GTA\n'
    '      # reports saturation only when the requested angle exceeds the\n'
    '      # installed car steering lock; native feedback handles response.\n'
    '      angle_control_saturated = False\n'
    '      curvature_limited = bool(active and curvature_limited)\n'
    '    elif self.use_steer_limited_by_safety:\n')

# User-requested game-only exception. Require both simulation launch flags and
# the explicit GTA profile; ordinary vehicle profiles keep the upstream check.
replace_once('selfdrive/selfdrived/selfdrived.py',
    '    self.excessive_actuation = self.params.get("Offroad_ExcessiveActuation") is not None\n',
    '    self.excessive_actuation_enabled = not (\n'
    '      os.getenv("GTA_SIMULATION") == "1" and os.getenv("SIMULATION") == "1" and\n'
    '      self.CP.brand == "gta" and self.CP.carFingerprint == "GTA_V")\n'
    '    self.excessive_actuation = self.excessive_actuation_enabled and self.params.get("Offroad_ExcessiveActuation") is not None\n')
replace_once('selfdrive/selfdrived/selfdrived.py',
    '    if self.calibrated_pose is not None:\n'
    '      excessive_actuation = self.excessive_actuation_check.update(self.sm, CS, self.calibrated_pose)\n',
    '    if self.excessive_actuation_enabled and self.calibrated_pose is not None:\n'
    '      excessive_actuation = self.excessive_actuation_check.update(self.sm, CS, self.calibrated_pose)\n')
replace_once('selfdrive/selfdrived/selfdrived.py',
    '    if self.excessive_actuation:\n'
    '      self.events.add(EventName.excessiveActuation)\n',
    '    if self.excessive_actuation_enabled and self.excessive_actuation:\n'
    '      self.events.add(EventName.excessiveActuation)\n')

replace_once('frogpilot/common/frogpilot_variables.py',
    '    pcm_cruise = CP.pcmCruise\n',
    '    pcm_cruise = CP.pcmCruise and CP.brand != "gta"\n')
replace_once('frogpilot/common/frogpilot_variables.py',
    'toggle.car_make in {"gm", "toyota"} or hyundai_canfd',
    'toggle.car_make in {"gm", "toyota", "gta"} or hyundai_canfd')
replace_once('frogpilot/common/frogpilot_variables.py',
    'condition=quality_of_life_longitudinal and toggle.car_make == "toyota" and pcm_cruise)',
    'condition=quality_of_life_longitudinal and ((toggle.car_make == "toyota" and pcm_cruise) or CP.brand == "gta"))')
replace_once('frogpilot/ui/qt/offroad/frogpilot_settings.h',
    '  bool hasPCMCruise = false;\n', '  bool hasPCMCruise = false;\n  bool isGTA = false;\n')
replace_once('frogpilot/ui/qt/offroad/frogpilot_settings.cc',
    '    hasPCMCruise = CP.getPcmCruise();\n',
    '    isGTA = CP.getBrand() == "gta";\n    hasPCMCruise = CP.getPcmCruise() && !isGTA;\n')
replace_once('frogpilot/ui/qt/offroad/longitudinal_settings.cc',
    '      setVisible &= parent->isGM || parent->isHKGCanFd || parent->isToyota;\n',
    '      setVisible &= parent->isGM || parent->isHKGCanFd || parent->isToyota || parent->isGTA;\n')
replace_once('frogpilot/ui/qt/offroad/longitudinal_settings.cc',
    '      setVisible &= parent->hasPCMCruise;\n      setVisible &= parent->isToyota;\n',
    '      setVisible &= (parent->hasPCMCruise && parent->isToyota) || parent->isGTA;\n')

modeld_path = ROOT/'selfdrive/modeld/modeld.py'
modeld_source = modeld_path.read_text()
modeld_patched = patch_modeld(modeld_source)
modeld_patched = patch_big_model(modeld_patched)
if modeld_source != modeld_patched:
    modeld_path.write_text(modeld_patched)

angle_path = ROOT/'selfdrive/controls/lib/latcontrol_angle.py'
angle_source = angle_path.read_text()
angle_patched = patch_angle_feedback(angle_source)
if angle_source != angle_patched:
    angle_path.write_text(angle_patched)

replace_once('frogpilot/common/frogpilot_variables.py',
    '    toggle.model_name = self.default_values["DrivingModelName"]\n',
    '    toggle.model_name = self.default_values["DrivingModelName"]\n'
    '    if (os.getenv("GTA_SIMULATION") == os.getenv("SIMULATION") == "1" and os.getenv("GTA_BIG_MODEL")):\n'
    '      toggle.model_name = "Cinque Terre (Big)"\n')

replace_once('frogpilot/common/frogpilot_variables.py',
    '      toggle.model_name = "Cinque Terre (Big)"\n',
    '      toggle.model_name = "Cinque Terre (Big)"\n'
    '    elif (os.getenv("GTA_SIMULATION") == os.getenv("SIMULATION") == "1" and os.getenv("GTA_REGULAR_MODEL")):\n'
    '      toggle.model = "macrostiff"\n'
    '      toggle.model_name = "Macrostiff"\n')

print('PC simulation patches applied.')
