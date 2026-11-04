# SkyrimTools

Claude Code plugin with everything gathered while modding Skyrim SE 1.5.97 on this machine (IssenFramework,
ReactiveDodgeFramework, DismemberingFramework): MCP servers, skills, scripts and working practices.

## Contents

| Path | What |
|---|---|
| `.claude-plugin/plugin.json` | plugin manifest (`skyrim-tools`) |
| `.claude-plugin/marketplace.json` | local marketplace `skyrim-tools` with this one plugin |
| `.mcp.json` | MCP servers: `housecarl` (load order, records, Papyrus, Nexus), `pyghidra-mcp` (Ghidra) |
| `skills/` | `skyrim-local-toolbox` (catalog of all tools), `skyrim-modding-practices`, `skyrim-reverse-engineering`, and from houseCARL: `spid-authoring`, `kid-authoring`, `skypatcher-authoring`, `open-animation-replacer`, `papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring` |
| `scripts/re/` | Address Library, thread snapshots, .pdb symbols, disassembly, vtable slots, Ghidra MCP launcher and CLI client |
| `scripts/esp/` | `espscan.py` (plugin records), `pexdis.py` (.pex disassembly) |
| `scripts/misc/` | `merge_ini.py` (merge new ini keys into a deployed ini), `font_has.py` (font glyph check) |
| `data/se_id_names.tsv` | REL::ID -> name table (`scripts/re/build_id_names.py`) |

Not in the repo (referenced by absolute path):
- RE workspace `D:\Games\Issen\re` (Ghidra 12.2, JDK 25, Python venv with pyghidra-mcp, Ghidra projects, binary
  copies). Override with the `SKYRIM_RE_DIR` environment variable.
- houseCARL server: `D:\Games\Issen\houseCARL\.claude\worktrees\relative-game-path\src\housecarl-mcp\bin\Release\net10.0\housecarl-mcp.exe`
  (build: `dotnet build -c Release` in that worktree), data `D:\Games\Issen\houseCARL-data`, MO2 instance STB.
- Skyrim-Animation-Studio (`D:\projects\Skyrim-Animation-Studio`): issen-clip, df-limb.
- Project tools in their own repos (RDF `tools\`, IssenFramework `tools\`), listed in `skyrim-local-toolbox`.

## Install / update

Registered in `C:\Users\Sequoia\.claude\settings.json` (all projects):

```json
"extraKnownMarketplaces": { "skyrim-tools": { "source": { "source": "directory", "path": "D:\\Games\\SkyrimTools" } } },
"enabledPlugins": { "skyrim-tools@skyrim-tools": true }
```

or by hand in Claude Code: `/plugin marketplace add D:\Games\SkyrimTools`, then `/plugin install skyrim-tools@skyrim-tools`.

Claude Code runs an installed plugin from its cache copy. After changing skills or `.mcp.json` here, run
`/plugin marketplace update skyrim-tools` (or reinstall) and restart the session. Scripts are called by their absolute
path in `D:\Games\SkyrimTools\scripts`, so script edits apply at once.

Project-specific skills stay in their project (e.g. `issen-strike-series` in `D:\Games\Issen\.claude\skills`).
