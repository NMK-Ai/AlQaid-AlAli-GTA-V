# Troubleshooting

**Setup stops:** fix the reported prerequisite, then rerun the failed stage. Do not run setup while this clone is driving. `Check-Setup.cmd` checks local artifacts. A clean checkout intentionally has no token, model files or WSL disk yet.

**WSL name already exists:** select a different `wslDistribution` in `config/local.json`. The installer will not repurpose someone else's distribution. WSL installation, virtualization and NVIDIA driver problems must be resolved before model compilation.

**Hook/version error:** confirm you have GTA Enhanced and a matching official Script Hook V runtime/Enhanced loader. Wait for an upstream hook update if the game just updated. Do not remove game executables or anti-cheat files to bypass version checks. Use Story Mode only.

**Game opens but no telemetry:** load Story Mode and spawn the Krieger. Check `OpenPilotGTA-bridge.log` in the game folder and `reports/windows-host-error.log`. Missing `xinput1_4.dll` from the compatible Enhanced loader was a failure during initial development. A different mod may also own a loader or port.

**Dashcam or unavailable:** inspect `reports/bridge-status.json` and `reports/frogpilot-manager-cuda.log`. The profile must identify as GTA. Give the camera and model time to start. Missing or stale telemetry, radar or model output must be fixed rather than silencing communication alerts.

**Controls window missing:** run `Open-Driving-Controls.cmd`. The launcher verifies a full visible window and can restore one without starting a second copy. Check `reports/control-panel.log` and `control-panel-faults.log`. If the game is elevated, configure `elevateControls` as described in SETUP.md.

**No moving camera:** enable the forward camera with the panel. Keep GTA unminimized, at a 1928x1208 client size. Capture deliberately rejects a different size. Disable Pause Game On Focus Loss to continue while switching windows. Logs: `windows-host-error.log`, `capture-status.json`, `linux-bridge.log`.

**Invisible UI / WARN:COPY MODE:** WSLg graphics sharing failed. Stop the project and save work in other WSL distributions first. Run `wsl --shutdown`, then launch again. This affects all WSL distributions, so the launcher does not do it automatically. For misplaced mouse clicks, drag the real UI with its title bar; avoid external utilities that resize only the Windows RDP proxy.

**Experimental holds a stop:** this remains a known behavior. Check the cruise target, whether the model requests `shouldStop`, and whether radar sees a lead. Switch Experimental off for ordinary ACC. Do not assume a model swap fixes shared pedal or timing issues.

**Lag / disengagement:** reduce GTA graphics load and review model execution and camera timing in `bridge-status.json`. Leave GPU headroom; compilation tests run without GTA are insufficient. Manual brake cancels speed control, handbrake cancels both axes, and freshness failures release commands intentionally.

Streaming software can also saturate the CPU. The capture process requests AboveNormal Windows scheduling priority to keep frames moving; it does not use realtime priority or disable freshness checks. If streaming causes repeated `camera_stale` entries in the native log, reduce stream resolution/frame rate and check whether the streaming application is using hardware encoding. A GPU that is not fully utilized does not rule out CPU contention.

**Report a problem:** include Windows version, GPU/driver, game/hook versions, repository commit, active model and relevant short log excerpts. Remove personal paths or account details. Never upload bridge-token, saves, your WSL disk or downloaded third-party binaries.
