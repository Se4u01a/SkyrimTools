# SkyrimTools

Skyrim modding toolkit for coding agents on Windows x64. Supports Mod Organizer 2 (MO2) on Skyrim SE 1.5.97 and AE, with reverse-engineering workflows geared to 1.5.97.

## What it does

| Component | Function |
|---|---|
| houseCARL | Inspect the MO2 load order, resolve record and asset conflicts, and build patches. |
| CLI scripts | Inspect and diff plugins, read saves and logs, compile and disassemble Papyrus, and query Nexus Mods. |
| Agent skills | Look up Papyrus and Mutagen APIs, author SPID, KID, SkyPatcher and OAR configs, and troubleshoot SKSE mods. |
| Ghidra (`-Ghidra`) | Analyze Skyrim and SKSE binaries through pyghidra-mcp. |
| SkyLink AI (`-SkyLink`) | Inspect the running game through SKSE with the `SkyLink AI` mod enabled in MO2. |

## Install or update

Run `setup.cmd` from the repository and select the folder containing `ModOrganizer.ini`. The default install location is `%LOCALAPPDATA%\SkyrimTools`.

```powershell
.\setup.cmd -Yes -Mo2Dir "<folder containing ModOrganizer.ini>"
```

Use `-Ghidra` and `-SkyLink` to include the optional components. To update, pull the repository and rerun setup with the options you use. See [the installation guide (Russian)](INSTALL.md).

Setup installs the prebuilt Windows x64 [MCP gateway](gateway/README.md) for Claude Code and verifies its SHA-256. After updating the plugin, run `/plugin marketplace update skyrim-tools` and restart the session. For Codex, VS Code and other clients, see [MCP setup](docs/mcp-clients.md).

## Check the installation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1 -Fix
python scripts\agents\selftest.py
```

Use `--live` to check local Skyrim and MO2 data and installed tools. See [AGENTS.md](AGENTS.md) for script usage, the [skill index](skills/README.md) for authoring references, and [FEATURES.md](FEATURES.md) for examples in Russian.
