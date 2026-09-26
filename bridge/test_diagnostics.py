import unittest
from gta_diagnostics import DisengagementTrace


class DisengagementTests(unittest.TestCase):
    def test_records_stale_camera_without_future_command_contamination(self):
        trace=DisengagementTrace()
        sample=dict(tick_ms=1000,flags=1|4|8|2048,speed=20.,vehicle=1,brake=0.)
        trace.telemetry(sample)
        trace.command(dict(vehicle=1,capture_tick_ms=900,mode=7),1100)
        trace.command(dict(vehicle=1,capture_tick_ms=1250,mode=0),1310)
        event=trace.telemetry({**sample,'tick_ms':1300,'flags':1|4})
        self.assertEqual(event['state']['camera_age_ms'],400)
        self.assertEqual(event['reason'],'Camera/model frame became stale')
        self.assertIn('inferred',event['evidence'])

    def test_manual_override_does_not_count_as_disengagement(self):
        trace=DisengagementTrace()
        sample=dict(tick_ms=1000,flags=1|4|8|2048,speed=20.,vehicle=1,brake=0.)
        self.assertIsNone(trace.telemetry(sample))
        self.assertIsNone(trace.telemetry({**sample,'tick_ms':1010,'flags':sample['flags']|16}))
        self.assertIsNone(trace.telemetry({**sample,'tick_ms':1020,'flags':sample['flags']|1024}))

    def test_background_focus_is_not_reported_as_stop_reason(self):
        trace=DisengagementTrace()
        sample=dict(tick_ms=1000,flags=1|4|8|2048,speed=20.,vehicle=1,brake=0.)
        trace.telemetry(sample)
        trace.command(dict(vehicle=1,capture_tick_ms=900,mode=7),1100)
        event=trace.telemetry({**sample,'tick_ms':1300,'flags':1|4|1024})
        self.assertEqual(event['reason'],'Camera/model frame became stale')


if __name__=='__main__':
    unittest.main()
