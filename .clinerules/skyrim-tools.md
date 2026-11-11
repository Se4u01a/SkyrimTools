# SkyrimTools

Authoritative agent guide: [`AGENTS.md`](../AGENTS.md). Read it before changing anything here.

## What this repo is

A Windows-only Skyrim SE modding toolkit for coding agents: 11 skills (`skills/<name>/SKILL.md` + `references/`), two MCP
server launchers (`housecarl`, `pyghidra-mcp`), Python/PowerShell scripts (`scripts/`), an installer (`setup.cmd`) and a
REL::ID name table (`data/`). Nothing to build; tests: `python scripts\agents\selftest.py`.

- Heavy parts (`houseCARL`, Ghidra, JDK, venv) live outside the repo in `%LOCALAPPDATA%\SkyrimTools`; environment
  variables `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`, `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR` point at them.
  An unset variable means that part is not installed — say so, do not guess a path.
- Install/health check: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1` (`-Json`, `-Fix`).
- MCP wiring for clients other than Claude Code: `docs/mcp-clients.md`; this workspace also ships `.vscode/mcp.json`.
- Read a skill as a whole: `SKILL.md` first, then the `references/` file it names. Index: `skills/README.md`.
  `index.jsonl` corpora are grepped for the quoted token to get shard + line. MCP tool names are `housecarl_<tool>`.

## Non-negotiables

1. A patch, SPID/KID/SkyPatcher INI or OAR submod goes into a **new** MO2 mod folder — never into another author's mod —
   and it does nothing until the user enables it; say so every time.
2. Never overwrite a deployed INI the user tuned in game; merge keys with `scripts\misc\merge_ini.py`.
3. Never edit `ModOrganizer.ini` while MO2 runs, and never hand-edit `plugins.txt` / `modlist.txt`.
4. No game assets, mod files or binaries in git.
5. Never launch the game. Finish with "built, NOT tested in game" and what the user must do.
6. Verify addresses, REL::IDs and vtable slots before quoting them (`scripts\re\addrlib.py`, Ghidra).
7. Keep EOLs: `.cmd`/`.ps1` CRLF, everything else LF; keep file encodings.
8. Adding a script or a skill means updating `AGENTS.md`, `README.md` and `skills/README.md` in the same change.
