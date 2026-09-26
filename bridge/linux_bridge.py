"""Feed live GTA cameras/CAN into the genuine FrogPilot processes."""
import argparse
import json
import math
import signal
import socket
import threading
import time
from pathlib import Path

from cereal import messaging
from msgq.visionipc import VisionStreamType
from openpilot.common.params import Params
from openpilot.tools.sim.lib.common import SimulatorState, vec3
from gta_vehicle import GTAVehicle
from gta_interface import actuators_to_game, PEDAL_INPUT_DEADZONE, BRAKE_ACCEL_PER_UNIT
from gta_sensors import GTASensors
from gta_pose import GTAPose
from gta_radar import RadarReceiver
from protocol import WIDTH, HEIGHT, NV12_SIZE, VERSION, receive_exact, receive_json, send_json

parser = argparse.ArgumentParser()
parser.add_argument('--enable-controls', action='store_true', help='Still requires F8 and fresh valid model/control output')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
token = (ROOT / 'runtime/bridge-token').read_text().strip()
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())
params = Params()
params.put_bool('AlphaLongitudinalEnabled', True)
car = GTAVehicle()
sensors = GTASensors(dual_camera=True)
pose = GTAPose()
radar = RadarReceiver()
pose_pm = messaging.PubMaster(['livePose'])
sm = messaging.SubMaster(['carControl', 'selfdriveState', 'modelV2', 'carState', 'onroadEvents', 'radarState',
                          'longitudinalPlan'])
latest = None
received_at = 0.
camera_at = 0.
frame_ticks = {}
frame_id = 0
connection = None
state = SimulatorState()
state.velocity = vec3(0, 0, 0)

def receive_frames():
    global latest, received_at, camera_at, frame_id, connection
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 8765))
        server.listen(1)
        server.settimeout(.5)
        print('Waiting for authenticated local Windows capture on port 8765', flush=True)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(2)
                try:
                    hello = receive_json(conn)
                    if hello != {'protocol': VERSION, 'token': token}:
                        raise ValueError('Invalid local transport handshake')
                    connection = conn
                    while not stop.is_set():
                        header = receive_json(conn)
                        size = header.get('bytes')
                        if size not in (0, NV12_SIZE * 2):
                            raise ValueError('Unexpected image size')
                        telemetry = header.get('telemetry')
                        if telemetry is not None:
                            if telemetry.get('version') != VERSION or not all(math.isfinite(float(v)) for v in telemetry.values()):
                                raise ValueError('Invalid vehicle data')
                        if size:
                            if header['width'] != WIDTH or header['height'] != HEIGHT:
                                raise ValueError('Camera geometry differs from calibrated projection')
                            payload = receive_exact(conn, size)
                            frame_id = int(header['frame_id'])
                            if frame_id < 0:
                                raise ValueError('Negative frame ID')
                            stamp = time.monotonic_ns()
                            frame_ticks[frame_id] = (int(header['capture_tick_ms']), time.monotonic())
                            for old in list(frame_ticks):
                                if old < frame_id-100:
                                    del frame_ticks[old]
                            for offset, stream, service in (
                                (0, VisionStreamType.VISION_STREAM_ROAD, 'roadCameraState'),
                                (NV12_SIZE, VisionStreamType.VISION_STREAM_WIDE_ROAD, 'wideRoadCameraState')):
                                sensors.camerad.vipc_server.send(stream, payload[offset:offset+NV12_SIZE], frame_id, stamp, stamp)
                                msg = messaging.new_message(service, valid=True)
                                camera = getattr(msg, service)
                                camera.frameId = frame_id
                                camera.timestampSof = stamp
                                camera.timestampEof = stamp
                                camera.transform = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
                                sensors.camerad.pm.send(service, msg)
                            camera_at = time.monotonic()
                        latest = telemetry
                        radar.update(header.get('radar'), time.monotonic())
                        received_at = time.monotonic()
                except (OSError, ConnectionError, ValueError, KeyError) as e:
                    print(f'Capture disconnected: {e}', flush=True)
                finally:
                    connection = None
                    latest = None
                    radar.update(None, time.monotonic())

threading.Thread(target=receive_frames, daemon=True).start()
print('Bridge running; controls permitted:', args.enable_controls, flush=True)
last_armed = False
button_until = 0.
last_sensor = last_gps = last_report = 0.
next_pose = 0.
last_telemetry_seq = -1
last_velocity = None
last_velocity_time = 0.
acceleration = (0., 0., 0.)
next_tick = time.monotonic()
last_valid_time = -10.
loop_count = 0
loop_started = next_tick
max_loop_ms = 0.
try:
    while not stop.is_set():
        now = time.monotonic()
        t = latest
        fresh = bool(t and now-received_at < .2 and now-camera_at < .2)
        flags = t['flags'] if t else 0
        state.valid = fresh and bool(flags & 1) and bool(flags & 4) and not bool(flags & 2)
        if state.valid:
            last_valid_time = now
        # Keep the processes warm through brief capture/menu interruptions.
        # Actuation still uses state.valid and the independent native watchdog.
        state.ignition = state.valid or now-last_valid_time < 3.
        sm.update(0)
        state.is_engaged = bool(sm['selfdriveState'].active)
        armed = state.valid and bool(flags & 8)
        last_armed = armed
        if t:
            state.velocity = vec3(t['vx'], t['vy'], t['vz'])
            state.steering_angle = t['wheel_angle_deg']
            state.user_gas = t['gas']
            state.user_brake = t['brake']
            state.user_torque = -t['steer_input'] * 2000 if flags & 16 else 0
            state.left_blinker, state.right_blinker = bool(flags & 32), bool(flags & 64)
            if t['sequence'] != last_telemetry_seq:
                dt = (t['tick_ms']-last_velocity_time)/1000
                velocity = (t['vx'], t['vy'], t['vz'])
                if last_velocity is not None and .005 < dt < .2:
                    acceleration = tuple(max(-30, min(30, (v-p)/dt)) for v, p in zip(velocity, last_velocity))
                last_velocity, last_velocity_time = velocity, t['tick_ms']
                last_telemetry_seq = t['sequence']
            h = math.radians(t['heading'])
            forward = (-math.sin(h), math.cos(h))
            right = (math.cos(h), math.sin(h))
            ax = acceleration[0]*forward[0] + acceleration[1]*forward[1]
            ay = acceleration[0]*right[0] + acceleration[1]*right[1]
            wx = t['wx']*forward[0] + t['wy']*forward[1]
            wy = t['wx']*right[0] + t['wy']*right[1]
            # locationd converts phone sensor vectors to device axes as [-z,-y,-x].
            state.imu.accelerometer = vec3(acceleration[2]+9.81, -ay, -ax)
            state.imu.gyroscope = vec3(t['wz'], -wy, -wx)
            state.imu.bearing = (-t['heading']) % 360
        car.update(state, t, radar)
        sensors.send_imu_message(state)
        pose.update(t, state.valid, now)
        if now >= next_pose:
            pose_pm.send('livePose', pose.message(now, state.valid))
            next_pose = now+.05 if now-next_pose > .05 else next_pose+.05
        if now-sensors.last_dmon_update >= .05:
            sensors.send_fake_driver_monitoring()
            sensors.last_dmon_update = now
        if now-sensors.last_perp_update >= .25:
            sensors.send_peripheral_state()
            sensors.last_perp_update = now
        if state.valid and now-last_gps >= .1:
            gps = messaging.new_message('gpsLocationExternal', valid=True)
            gps.gpsLocationExternal = {
                'unixTimestampMillis': int(time.time()*1000), 'flags': 1,
                'horizontalAccuracy': 1., 'verticalAccuracy': 1., 'speedAccuracy': .1, 'bearingAccuracyDeg': .1,
                'vNED': [t['vy'], t['vx'], -t['vz']], 'bearingDeg': state.imu.bearing,
                'latitude': 32.753085 + t['py']/111320,
                'longitude': -117.209539 + t['px']/(111320*math.cos(math.radians(32.753085))),
                'altitude': t['pz'], 'speed': state.speed, 'source': 'ublox'}
            sensors.pm.send('gpsLocationExternal', gps)
            last_gps = now
        current_model = sm['modelV2']
        model_tick, model_time = frame_ticks.get(current_model.frameId, (0, 0.))
        cc = sm['carControl']
        outputs_fresh = all(now-sm.recv_time[s] < .2 and sm.valid[s] for s in ('carControl', 'selfdriveState', 'modelV2'))
        ready = args.enable_controls and armed and outputs_fresh and now-model_time < .2
        lat_active = ready and cc.latActive
        long_active = ready and state.is_engaged and bool(flags & 2048) and cc.longActive
        # Bit 2 acknowledges engagement even when a pedal/steering override
        # temporarily suppresses an axis. Native must not interpret that as Cancel.
        mode = int(lat_active) | (int(long_active) << 1) | (4 if outputs_fresh and sm['selfdriveState'].enabled else 0)
        active = bool(mode & 3)
        steer, throttle, brake = actuators_to_game(cc.actuators.steeringAngleDeg, cc.actuators.accel,
                                                 lat_active, long_active, speed=state.speed,
                                                 stopping=cc.actuators.longControlState == 'stopping')
        if not all(math.isfinite(x) for x in (steer, throttle, brake)):
            active, mode, steer, throttle, brake = False, 0, 0., 0., 0.
        conn = connection
        if conn:
            # Inactive heartbeats use the latest frame. Active commands reference
            # the actual model frame, so an old prediction cannot appear fresh.
            capture_tick = model_tick if active else frame_ticks.get(frame_id, (0, 0))[0]
            try:
                send_json(conn, {'vehicle': t['vehicle'] if t else 0, 'capture_tick_ms': capture_tick,
                                 'mode': mode, 'steer': steer, 'throttle': throttle, 'brake': brake,
                                 'events': [str(e.name) for e in sm['onroadEvents']],
                                 'alert': sm['selfdriveState'].alertText2})
            except (OSError, ConnectionError):
                pass
        if now-last_report > 1:
            report = {'valid': state.valid, 'protocol': VERSION, 'frame': frame_id, 'model_frame': current_model.frameId,
                      'bridge_hz': loop_count/max(.001, now-loop_started), 'max_loop_ms': max_loop_ms,
                      'model_seconds': current_model.modelExecutionTime, 'model_valid': sm.valid['modelV2'],
                      'speed_mps': state.speed, 'armed': armed, 'openpilot_active': state.is_engaged,
                      'controls_requested': bool(active), 'controls_applied': bool(flags & 128),
                      'lateral_applied': bool(flags & 65536), 'longitudinal_applied': bool(flags & 32768),
                      'camera': bool(flags & 4), 'pose_source': 'gta_camera_motion',
                      'radar_valid': car.radar_valid, 'radar_points': car.radar_count,
                      'radar_rejects_while_vehicle_valid': dict(radar.rejects),
                      'radar_lead': bool(car.radar_valid and sm.valid['radarState'] and
                                         now-sm.recv_time['radarState'] < .2 and
                                         sm['radarState'].leadOne.status and sm['radarState'].leadOne.radar),
                      'radar_lead_distance': sm['radarState'].leadOne.dRel,
                      'radar_lead_relative_speed': sm['radarState'].leadOne.vRel,
                      'left_blinker': bool(flags & 32), 'right_blinker': bool(flags & 64),
                      'personality': str(sm['selfdriveState'].personality),
                      'drive_mode': ['normal', 'eco', 'sport'][car.drive_mode],
                      'coast': car.last_state.forceCoast, 'pause_lateral': car.last_state.pauseLateral,
                      'pause_longitudinal': car.last_state.pauseLongitudinal, 'traffic': car.last_state.trafficModeEnabled,
                      'lateral_requested': bool(lat_active), 'longitudinal_requested': bool(long_active),
                      'cruise_master': armed, 'cruise_enabled': bool(flags & 2048),
                      'cruise_speed_mps': car.cruise_speed,
                      'experimental_mode': bool(sm['selfdriveState'].experimentalMode),
                      'model_accel': sm['modelV2'].action.desiredAcceleration,
                      'model_should_stop': bool(sm['modelV2'].action.shouldStop),
                      'planner_accel': sm['longitudinalPlan'].aTarget,
                      'planner_should_stop': bool(sm['longitudinalPlan'].shouldStop),
                      'actuator_accel': cc.actuators.accel,
                      'pedal_input_deadzone': PEDAL_INPUT_DEADZONE,
                      'brake_input_deadzone': 0.,
                      'brake_accel_per_unit': BRAKE_ACCEL_PER_UNIT,
                      'long_control_state': str(cc.actuators.longControlState),
                      'coasting_instead_of_premature_hold': bool(long_active and 0 <= state.speed <= 1 and
                          cc.actuators.accel < 0 and cc.actuators.longControlState != 'stopping'),
                      'events': [str(e.name) for e in sm['onroadEvents']],
                      'wheel_angle_deg': t.get('wheel_angle_deg', 0.) if t else 0.,
                      'vehicle_model': t.get('model', 0) if t else 0,
                      'spawn_status': t.get('spawn_status', 0) if t else 0,
                      'wheel_angle_valid': bool(flags & 67108864),
                      'wheel_left_z': t.get('wheel_left_z', 0.) if t else 0.,
                      'wheel_right_z': t.get('wheel_right_z', 0.) if t else 0.,
                      'yaw_rate': t.get('wz', 0.) if t else 0.,
                      'wheelbase': t.get('wheelbase', 0.) if t else 0.,
                      'applied_steer': t.get('applied_steer', 0.) if t else 0.,
                      'requested_angle_deg': cc.actuators.steeringAngleDeg,
                      'manual_steering': bool(flags & 16),
                      'manual_gas': t.get('gas', 0.) if t else 0.,
                      'manual_brake': t.get('brake', 0.) if t else 0.,
                      'steer': steer, 'throttle': throttle, 'brake': brake}
            (ROOT/'reports/bridge-status.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            last_report = now
            loop_started, loop_count, max_loop_ms = now, 0, 0.
        # Absolute deadlines avoid accumulating scheduler oversleep into a
        # 90-95 Hz stream and tripping selfdrived's real lag detector.
        next_tick += .01
        finished = time.monotonic()
        loop_count += 1
        max_loop_ms = max(max_loop_ms, (finished-now)*1000)
        if finished-next_tick > .1:
            next_tick = finished
        stop.wait(max(0., next_tick-finished))
finally:
    stop.set()
    state.ignition = False
    car.send_panda_state(state)
