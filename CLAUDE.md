# CLAUDE.md

SkyrimTools is documented once, for every agent, in [`AGENTS.md`](AGENTS.md). It applies to Claude Code unchanged and
is imported here so it is always in context:

@AGENTS.md

## Claude Code specifics

- This repo **is** a plugin: manifest `.claude-plugin/plugin.json`, local marketplace `.claude-plugin/marketplace.json`,
  MCP servers `.mcp.json`. It is also usable without the plugin (see `docs/mcp-clients.md`).
- `${CLAUDE_PLUGIN_ROOT}` in `.mcp.json` is expanded by Claude Code only. Other clients use `%SKYRIM_TOOLS_REPO%` or the
  absolute paths printed by `scripts\agents\connect.ps1`.
- Claude Code runs an installed plugin from its **cache copy**: after editing `skills/`, `.mcp.json` or
  `.claude-plugin/`, run `/plugin marketplace update skyrim-tools` and restart the session. Scripts are called through
  `%SKYRIM_TOOLS_REPO%`, so edits to `scripts/` apply at once.
- Plugin skills are namespaced `housecarl:<name>` (e.g. `housecarl:papyrus-reference`); in a bare checkout they are the
  plain folder names. MCP tool names are always bare — `housecarl_records`, `housecarl_apply`.
- `setup.cmd` registers the plugin in `%USERPROFILE%\.claude\settings.json` (backup:
  `settings.json.skyrimtools.bak`). Health checks in session: `/plugin` shows `skyrim-tools` enabled, `/mcp` shows
  `housecarl` (and `pyghidra-mcp` if Ghidra was installed, `skylink` if `setup.cmd -SkyLink` was run) as connected.
- Do not install the skills a second time through houseCARL's own `houseCARL-Setup.exe --claude`: the skills and the
  server would be duplicated. `scripts\agents\doctor.ps1` warns about this.
