# SkyrimTools — GitHub Copilot instructions

SkyrimTools is a **Skyrim SE modding toolkit for coding agents**: Markdown knowledge bases in `skills/`, three MCP
server launchers, and small Python/PowerShell scripts. There is nothing to build; the test suite is
`python scripts\agents\selftest.py` (CI runs it). The complete,
authoritative guide is **[`AGENTS.md`](../AGENTS.md)** — read it before changing anything here.

## The short version

- Windows-only; Skyrim SE 1.5.97-first (AE 1.6.x works except the reverse-engineering scripts).
- Heavy parts (`houseCARL`, Ghidra, JDK, Python venv) live outside the repo in `%LOCALAPPDATA%\SkyrimTools`.
  The repo holds no binaries, no mods, no game assets.
- Environment variables written by `setup.ps1`: `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`,
  `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR`. An unset one means that part is not installed — say so, do not guess a path.
- Check the machine with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1`
  (`-Json` for machine-readable output).
- MCP servers: `housecarl` (live MO2 load order, records, Papyrus, BSA/NIF, Nexus), `pyghidra-mcp` (headless Ghidra) and optional `skylink` (the running game, `setup.cmd -SkyLink`).
  Wiring for non-Claude clients: `docs/mcp-clients.md`. VS Code users in this workspace get `.vscode/mcp.json`.
- Skills: read `skills/<name>/SKILL.md` in full, then the `references/` file it names. Index: `skills/README.md`.
  In Claude Code they are `housecarl:<name>`; elsewhere the bare folder name. MCP tools are always `housecarl_<tool>`.

## Rules that outrank defaults

1. Never write into another author's mod folder — a patch/INI/OAR submod goes into a **new** MO2 mod folder, which does
   nothing until the user enables it (say so).
2. Never copy a shipped INI over a deployed one; merge keys with `scripts\misc\merge_ini.py`.
3. Never edit `ModOrganizer.ini` while MO2 runs; never hand-edit `plugins.txt` / `modlist.txt`.
4. No game assets or third-party files in git.
5. Never launch the game. Report "built, NOT tested in game" and what the user must do.
6. Verify addresses, REL::IDs and vtable slots with `scripts\re\addrlib.py` or Ghidra; never quote them unchecked.
7. Keep EOLs: `.cmd` is CRLF, `.ps1` CRLF, everything else LF. Keep file encodings.
8. When you add a script or a skill, update `AGENTS.md`, `README.md`, `skills/README.md` and `CONTRIBUTING.md`-style
   docs in the same change.
