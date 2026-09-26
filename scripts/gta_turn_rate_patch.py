"""Patch the real angle controller without changing other vehicle profiles."""


def patch_angle_feedback(source):
    if 'self.gta_turn_rate.update(' in source:
        return source
    anchor = '    self.gta_wheelbase = CP.wheelbase if CP.brand == "gta" else None\n'
    if source.count(anchor) != 1:
        raise RuntimeError('Unexpected GTA angle-controller initialization')
    source = source.replace(anchor, anchor+
        '    self.gta_turn_rate = None\n'
        '    if self.gta_wheelbase is not None:\n'
        '      from openpilot.tools.gta.gta_lateral import TurnRateController\n'
        '      self.gta_turn_rate = TurnRateController(self.gta_wheelbase, dt)\n'
        '\n'
        '  def reset(self):\n'
        '    super().reset()\n'
        '    if self.gta_turn_rate is not None:\n'
        '      self.gta_turn_rate.reset()\n', 1)
    old = ('      if self.gta_wheelbase is not None:\n'
           '        from openpilot.tools.gta.gta_lateral import road_wheel_angle\n'
           '        angle_steers_des = road_wheel_angle(desired_curvature, self.gta_wheelbase, CS.vEgo)\n')
    new = ('      if self.gta_turn_rate is not None:\n'
           '        # GTA camera-frame motion is measured directly, including bank.\n'
           '        yaw_rate = -calibrated_pose.angular_velocity.z if calibrated_pose is not None else CS.yawRate\n'
           '        angle_steers_des = self.gta_turn_rate.update(desired_curvature, CS.vEgo, yaw_rate,\n'
           '                                                      override=CS.steeringPressed)\n')
    if source.count(old) != 1:
        raise RuntimeError('Unexpected GTA angle conversion')
    source = source.replace(old, new, 1)
    source = source.replace('    if not active:\n      angle_log.active = False\n',
        '    if not active:\n'
        '      if self.gta_turn_rate is not None:\n'
        '        self.gta_turn_rate.reset()\n'
        '      angle_log.active = False\n', 1)
    return source
