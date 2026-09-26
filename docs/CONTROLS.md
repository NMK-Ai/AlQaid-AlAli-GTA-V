# GTA / FrogPilot controls

Use the **FrogPilot Driving Controls** window: every driving action below has a labeled button. It opens automatically with `Start-FrogPilot.cmd`; `Open-Driving-Controls.cmd` opens it separately. Buttons keep GTA focused and display live mode, speed, and engagement status. The real FrogPilot UI remains a separate window.

For keyboard use, click **GTA** first. Switching applications keeps automated driving enabled; physical game keys are read only while GTA is focused. Pausing, changing vehicles or losing fresh camera/control data releases driving controls. Closing the driving panel sends All Off. Reopening an already-running panel restores it without closing it.

**F6 enables the camera, not driving. F7 enables cruise master for always-on lateral. F8 engages cruise at your current speed.** Start at a sensible speed on a road; setting while stopped currently produces a 2 mph target.

| Key | Action |
| --- | --- |
| F12 / Spawn OpenPilot car | Spawn a stock Krieger in nearby clear road space, seat the player, and enable the camera. Stop and leave the pause menu first. Driving remains disengaged. The previous vehicle is preserved. Story Mode only. |
| F6 | Toggle the fixed forward camera. Re-enable after changing vehicles or restarting GTA. |
| F7 | Toggle cruise master. With Always On Lateral enabled, allow steering without speed control. |
| F8 | Set current speed and engage steering plus gas/brake. |
| Shift + F8 | Resume the saved cruise speed and engage. |
| F9 | Cancel speed control; always-on lateral remains available. |
| F10 | Turn off both cruise master and speed control. |
| + / - (including numpad) | Configured Cruise Interval on release; hold >0.5 seconds for Cruise Interval (Hold). Uses mph or km/h from FrogPilot's units setting. |
| Shift + + / - | Use the configured hold step with one tap (panel: Large step). |
| [ / ] | Toggle left/right indicators. Press the same key again to cancel. Selecting the opposite side switches indicators. |
| F5 | Toggle Experimental Mode; when Conditional Experimental Mode is selected, invoke its manual override. |
| F4 | Cycle driving personality / following distance. |
| B | Distance button, using the action selected in FrogPilot's Wheel Buttons settings. |
| Hold B > 0.5 seconds | Distance Button (Long Press). |
| Hold B > 2.5 seconds | Distance Button (Very Long Press). FrogPilot first runs the long action, then undoes it and runs the very-long action. |
| L | LKAS button, using its assigned Wheel Buttons action. |
| F1 | Toggle coast. |
| F2 | Toggle pause steering. |
| F3 | Toggle pause acceleration/braking. |
| F11 | Toggle Traffic Mode. |
| Insert | Cycle Normal / Eco / Sport virtual drive mode for Map Accel/Decel to Gears. |
| Numpad 4 / 6 | Supply a left/right steering nudge for manual lane-change confirmation. |
| W / Up or controller accelerator | Temporarily override gas/brake; release to resume cruise. Steering stays enabled. |
| S / Down or controller brake | Cancel speed control; Always On Lateral keeps steering. Resume requires the Resume button. |
| A / D, Left / Right, or controller steering | Temporarily override steering; release to resume. Cruise stays enabled. |
| Handbrake / Space | Turn off both automated axes. |

The installed protocol 4 adapter preserves the manual-override behavior introduced in protocol 3. Its compiled state-machine checks cover these transitions; live validation boundaries are listed in LIMITATIONS.md. FrogPilot's Disengage on Accelerator is set off and Pause AOL on Brake is set to zero by the simulator defaults.

The Wheel Buttons page is under **FrogPilot → Vehicle → Wheel Buttons** and requires **Advanced** or **Developer** tuning level. All six assignable actions have dedicated shortcuts as well. Current assignments: B tap = personality, B long = Experimental Mode, B very long = Traffic Mode, L = Experimental Mode. These remain configurable in the real UI.

Automatic lane changes use the real model's lane-change state machine. Turn on Lane Changes and Automatic Lane Changes in Steering settings, then use [ or ]. Its minimum speed, delay, lane-width check, and simulated blind-spot occupancy still apply. A blinker does not guarantee a lane change, and complete lane-change execution has not yet been validated.

Cruise Increase/Decrease also feed FrogPilot's normal button events: they accept/reject pending speed-limit changes and Increase can release a model-forced stop. No GTA speed-limit source is implemented yet. Custom cruise interval, hold interval, set-speed offset and reverse increase are now connected to the virtual cruise state. The real UI exposes these controls for the GTA profile.

UI actions already have mouse controls: Experimental icon, personality icon, flashing speed-limit acceptance, Record, and settings buttons. Presence of a UI button does not prove its backend works: the device-specific screen recorder and model switching still need PC adaptations. See [UI feature audit](UI_FEATURE_AUDIT.md).
