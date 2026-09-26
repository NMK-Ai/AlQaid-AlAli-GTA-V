# Preview limitations

- Steering calibration is specific to a stock Krieger. At speed or in sustained turns the car can leave the drawn path; lane keeping is not accepted as complete.
- Experimental Mode can request stops on clear GTA roads. Longitudinal calibration and excessive stopping gaps remain under investigation. This preview includes the tested proportional brake mapping and low-speed hold correction, but those corrections do not prove that all unwanted model stops are resolved.
- GTA's visual domain differs from real roads. Correct model execution does not guarantee appropriate decisions in the game.
- The original RTX 4090 installation demonstrated approximately 20 Hz camera/model operation. Other GPU/driver combinations and simultaneous GTA load need measurement. Lag, stale camera frames or missing processes can release controls.
- Main/wide model views are derived from one calibrated GTA forward render. The narrow view is a digital crop, not an independent high-resolution camera. Arbitrary FOV, aspect-ratio or client-size changes invalidate the current setup.
- Radar tracks use game vehicle geometry and occlusion checks. Road-node, junction and GPS-route diagnostics are passive; NPC driving does not replace or steer the model.
- Full FrogPilot UI means the real UI is displayed, not that all device-specific features work on Windows. Cloud pairing, device updates, hardware accessories, screen recording, maps and arbitrary model downloads are not provided by this integration. See the source [UI feature inventory](UI_FEATURE_AUDIT.md).
- Driver attention is simulated. Actual GTA motion supplies pose instead of locationd's estimated motion. The GTA profile has simulation-only actuation exceptions; do not deploy it to a real car or comma device.
- Steam Enhanced Story Mode is the initial target. GTA Legacy, Rockstar/Epic launchers, non-NVIDIA GPUs and Apple Silicon are not supported by the release installer.
- The overlay is a display thumbnail. Settings clicks belong in the genuine full UI window.

Contributions should include reproducible conditions and measured camera/model/control timing. A successful build or short test is not evidence that every UI feature or driving scenario works.
