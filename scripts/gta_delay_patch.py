"""Keep the simulation delay prior separate from the real-car fallback."""
def patch_gta_delay(source):
    before = '    self.initial_lag = CP.steerActuatorDelay + 0.2\n'
    after = ('    # GTA publishes measured game motion without locationd filtering.\n'
             '    # Its profile supplies the observed command-to-motion prior.\n'
             '    self.initial_lag = CP.steerActuatorDelay + (0.0 if CP.brand == "gta" else 0.2)\n')
    if after in source:
        return source
    if source.count(before) != 1:
        raise RuntimeError('Unexpected lagd delay prior; review upstream before patching')
    return source.replace(before, after, 1)
