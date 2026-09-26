# Third-party components

- [FrogPilot](https://github.com/FrogAi/FrogPilot), derived from [openpilot](https://github.com/commaai/openpilot): fetched at the revision in config/project.json. Upstream MIT notice is retained in LICENSE because patch fragments derive from upstream source. Their bundled dependencies retain their respective upstream licenses.
- [tinygrad](https://github.com/tinygrad/tinygrad), opendbc, cereal, msgq and other upstream components are obtained with the pinned FrogPilot tree; this repository does not replace their license files.
- Macrostiff model and metadata are fetched from [FrogPilot Resources](https://github.com/FrogAi/FrogPilot-Resources/tree/7f2e85df05f7442efeddbe670f210daf61c432c3). Files and compiled artifacts are not redistributed in Git. Their provenance and hashes are in config/macrostiff-manifest.json; upstream terms apply.
- [Script Hook V](https://www.dev-c.com/gtav/scripthookv/) SDK, runtime and Enhanced loader are separate user-provided downloads. No SDK, loader, trainer or third-party DLL is included in Git.
- GTA V Enhanced and Rockstar/Steam components are separately installed commercial software. No game archives, decryption keys, executables, saves or account data are included.
- Ubuntu/WSL and Python packages are downloaded from their publishers and package indexes. Their licenses apply independently.

The small Krieger configuration contains only numeric values needed by the integration, not the extracted handling file or archive-reading tools.
