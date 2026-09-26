"""Sensor messages for the GTA bridge's 100 Hz update loop."""
from cereal import messaging
from openpilot.tools.sim.lib.simulated_sensors import SimulatedSensors


class GTASensors(SimulatedSensors):
    def send_imu_message(self, state):
        # The stock simulator emits five readings per 20 Hz update. Our loop
        # runs at 100 Hz already: that burst counted each short disagreement
        # five times and caused a long locationd input-invalid recovery.
        for service, field, sensor_id, vector in (
            ('accelerometer', 'acceleration', 4, state.imu.accelerometer),
            ('gyroscope', 'gyroUncalibrated', 5, state.imu.gyroscope),
        ):
            msg = messaging.new_message(service, valid=bool(state.valid))
            sensor = getattr(msg, service)
            sensor.sensor = sensor_id
            sensor.type = 0x10
            sensor.timestamp = msg.logMonoTime
            sensor.init(field)
            getattr(sensor, field).v = [vector.x, vector.y, vector.z]
            self.pm.send(service, msg)
