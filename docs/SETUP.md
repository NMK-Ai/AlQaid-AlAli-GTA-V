# Setup details

The repository contains the adapter and integration code. Setup obtains the pinned FrogPilot source and model separately. You supply GTA and the official Script Hook V SDK/runtime.

`config/project.json` holds portable defaults. Setup writes machine-specific values to ignored `config/local.json`. You can create that file from `config/local.example.json` before setup. Supported overrides include `gameDirectory`, `steamExecutable`, `wslDistribution`, `buildJobs`, `uiScale`, and `elevateControls`.

Run `Setup.cmd -Plan` to inspect the target and stages. Individual resumable stages:

| Command | Work |
| --- | --- |
| `Setup.cmd -Stage Configure` | Detect game/Steam, save local settings, generate a unique random bridge token and default runtime preferences |
| `Setup.cmd -Stage Windows` | Configure and install Python capture/control-panel dependencies in `.venv` |
| `Setup.cmd -Stage Native` | Configure and build the ASI and run native logic tests |
| `Setup.cmd -Stage Linux` | Import the checked Ubuntu image if absent; install packages; fetch pinned source; patch/build UI; download, compile and numerically check Macrostiff |
| `Setup.cmd` | All stages in order |

For a Python installation without `py.exe`, use `Setup.cmd -PythonExe "C:\path\python.exe"` with Python 3.13 x64 and Tk. `buildJobs` defaults to 4; reduce it on memory-constrained systems.

Linux uses its own upstream-locked Python 3.12 environment, independent of Windows Python. The build uses CPU OpenCL for camera transforms and CUDA/PTX for model inference. NVIDIA's Windows driver provides WSL's CUDA driver library. GPU artifacts are rebuilt locally and must pass an independent numerical comparison and an unloaded p95 pair-inference check below 40 ms. This check leaves room for other work but is not proof of adequate performance alongside GTA; monitor live frame rate too.

The Ubuntu image URL and SHA-256 are pinned in `config/project.json`, sourced from Microsoft's WSL distribution catalog. `-RootfsPath` accepts a previously downloaded image with exactly that checksum. Downloads are cached locally. Never import someone else's configured WSL image to obtain this setup.

An ownership marker inside the distribution ties it to this clone. Setup and launch refuse an existing distribution owned by another project. To keep two clones, assign a different distribution name before setup. Only one GTA bridge may run on a PC at once because native UDP ports and control-panel identity are shared. Do not move the installed clone; use a fresh clone with a new distribution name if relocation is needed after setup.

The native install has a full preflight, checksum manifest and rollback for file-copy errors. Existing identical loader files may be used but are marked as not owned. Existing differing files stop installation. Modified project-installed files stop updates/uninstall for review. Normal users who have a protected game directory may need to run only the game install/uninstall step as administrator.

The controls normally run without elevation. If Steam/GTA is intentionally running as administrator and panel buttons do not reach the game, set `elevateControls` to `true`; opening the panel then uses the normal Windows UAC prompt.

Default model selection is Macrostiff. The retained big-model support code is experimental development code; this installer does not download or install big models, and the device model-download UI is not a PC GPU model installer.
