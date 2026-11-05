# GEMINI.md

The agent-facing guide for this repository is [`AGENTS.md`](AGENTS.md); it applies here unchanged.

@AGENTS.md

## Gemini CLI specifics

- MCP servers go into `~/.gemini/settings.json` under `"mcpServers"`. Gemini CLI launches `command` directly (no shell),
  so `%SKYRIM_TOOLS_REPO%` will not expand: use `cmd.exe` with the absolute launcher path, as printed by
  `scripts\agents\connect.ps1 -Client gemini`. See `docs/mcp-clients.md`.
- Skills are read as files, not discovered: `skills/<name>/SKILL.md`, names are the bare folder names
  (`papyrus-reference`, `spid-authoring`, ...). The index is `skills/README.md`.
- `tools/*.py` are stdlib-only Python 3 unless their docstring says *RE venv* or *Ghidra* (see `AGENTS.md` §5).
- Everything is Windows-only; run PowerShell with `-NoProfile -ExecutionPolicy Bypass -File` for the repo's `.ps1` files.
