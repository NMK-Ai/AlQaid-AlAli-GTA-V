# Validation scope

Release preparation on September 18, 2026:

- Four portable-source checks passed: Python syntax, original-machine path exclusion, portable default configuration/model hashes, and private directory exclusions.
- The patch set applied to pristine files from the exact pinned FrogPilot commit. Applying it again produced identical files. This test used a temporary directory containing spaces and did not modify the running FrogPilot checkout.
- Bridge unit suite: 28 passed, one platform-dependent case skipped on Windows.
- The Windows x64 ASI compiled with Visual Studio 2022 and the separately installed Script Hook V SDK.
- All five native contract tests passed with MSVC and with Linux g++. Assertions remain enabled in Release builds. These exercise override/watchdog state, angle response, braking/reverse handling, radar and road context logic.
- The PowerShell installer was exercised with fake game files in directories containing spaces: configuration, persistent random token, native argument quoting, preview, initial/repeated install, upgrade, conflicting loader refusal, changed-file refusal and ownership-aware uninstall passed.
- PowerShell parser checks and Bash syntax checks passed. A fresh clone from GitHub passed the portable-source checks; installer fixtures and WSL argument handling were also exercised from paths containing spaces.
- Hosted GitHub Actions did not start; no hosted-test pass is claimed. The local results above are the available verification.

The source comes from a working GTA/FrogPilot installation; a new PC has **not** completed the whole installer and driving acceptance test yet. The release copy has not replaced that installation. A fresh Linux build plus per-GPU inference checks are still performed by Setup on each destination. Do not interpret unit tests, a compiled ASI, or CI status as an end-to-end GTA test.

During preparation the original game was kept running at the user's request. GPU compilation/benchmarks were not repeated concurrently with their drive. CPU contention during Discord streaming was diagnosed from native `camera_stale` messages; assigning AboveNormal priority to the capture process restored roughly 20 Hz delivery in later observations. This mitigation is included, but does not guarantee timing under every streaming workload.
