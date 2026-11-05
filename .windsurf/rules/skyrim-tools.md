---
trigger: always_on
description: SkyrimTools repository rules — Skyrim SE modding toolkit (skills, MCP servers, RE scripts)
---

# SkyrimTools

Full agent guide: [`AGENTS.md`](../../AGENTS.md) — read it first.

- Windows-only, Skyrim SE 1.5.97-first, nothing to build. Knowledge in `skills/`, tools in `scripts/`, installer
  `setup.cmd`.
- Heavy parts live in `%LOCALAPPDATA%\SkyrimTools`, found via `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`,
  `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR`. Unset variable = not installed: say so, don't guess a path.
- Install check: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1`.
- Load a skill by reading `skills/<name>/SKILL.md` in full plus the `references/` file it names; index in
  `skills/README.md`. MCP tool names are `housecarl_<tool>`; MCP wiring outside Claude Code: `docs/mcp-clients.md`.

## Non-negotiables

1. Patch, SPID/KID/SkyPatcher INI or OAR submod goes into a **new** MO2 mod folder, never into another author's mod;
   tell the user it does nothing until they enable it.
2. Never overwrite a deployed INI the user tuned in game — merge keys with `scripts\misc\merge_ini.py`.
3. Never edit `ModOrganizer.ini` while MO2 runs; never hand-edit `plugins.txt` / `modlist.txt`.
4. No game assets, mod files or binaries in git.
5. Never launch the game; report "built, NOT tested in game" and what the user must do.
6. Verify addresses, REL::IDs and vtable slots before quoting them (`scripts\re\addrlib.py`, Ghidra).
7. `.cmd`/`.ps1` CRLF, other files LF; keep encodings.
8. Adding a script or skill means updating `AGENTS.md`, `README.md` and `skills/README.md`.
