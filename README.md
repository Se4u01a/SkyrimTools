# SkyrimTools

Claude Code plugin with everything gathered while modding Skyrim SE 1.5.97 (IssenFramework, ReactiveDodgeFramework,
DismemberingFramework): MCP servers, skills, scripts and working practices. Installable on any Windows machine with `setup.cmd`.

**По-русски:** что умеет набор — [FEATURES.md](FEATURES.md), как установить — [INSTALL.md](INSTALL.md).

## Contents

| Path | What |
|---|---|
| `FEATURES.md`, `INSTALL.md` | what the toolkit does, how to install it (Russian, for users) |
| `.claude-plugin/plugin.json` | plugin manifest (`skyrim-tools`) |
| `.claude-plugin/marketplace.json` | local marketplace `skyrim-tools` with this one plugin |
| `.mcp.json` | MCP servers: `housecarl` (load order, records, Papyrus, Nexus), `pyghidra-mcp` (Ghidra) |
| `skills/` | `skyrim-local-toolbox` (catalog of all tools), `nexus-api-search` (preferred Nexus lookups via GraphQL), `skyrim-modding-practices`, `skyrim-reverse-engineering`, and from houseCARL: `spid-authoring`, `kid-authoring`, `skypatcher-authoring`, `open-animation-replacer`, `papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring` |
| `scripts/re/` | Address Library, thread snapshots, .pdb symbols, disassembly, vtable slots, Ghidra MCP launcher and CLI client |
| `scripts/esp/` | `espscan.py` (plugin records), `pexdis.py` (.pex disassembly) |
| `scripts/misc/` | `merge_ini.py` (merge new ini keys into a deployed ini), `font_has.py` (font glyph check), `nexus_gql.py` (Nexus search / description / files via the anonymous GraphQL API) |
| `data/se_id_names.tsv` | REL::ID -> name table (`scripts/re/build_id_names.py`) |
| `setup.cmd` / `setup.ps1` | installer: .NET 10, houseCARL release, optional Ghidra workspace, env vars, plugin registration |
| `scripts/run_housecarl.cmd` | houseCARL launcher used by `.mcp.json` |
| `requirements-re.txt` | Python packages of the RE venv |

## Install / update

**For anyone: see [INSTALL.md](INSTALL.md)** (in Russian). Short version: clone, close Claude Code, run `setup.cmd`,
reopen Claude Code. No Docker: houseCARL is a Windows exe that reads the live MO2 instance, and Ghidra reads the game exe.

`setup.ps1` puts the heavy parts outside the repo, in `%LOCALAPPDATA%\SkyrimTools` (`-InstallDir` to change):
`housecarl\server` (release zip, SHA-256 checked; built from the tag's source with the relative-`gamePath` fix when
the MO2 instance uses a relative `gamePath`, or with `-HousecarlFromSource`), `housecarl-data`, and with `-Ghidra` `re\` (JDK 25, Ghidra 12.2,
venv from `requirements-re.txt` with the ghidrecomp `set_pdb` patch, `projects\`, `bins\skyrim\SkyrimSE.exe`). It writes
user environment variables that the launchers, scripts and skills read, and registers the plugin in
`~/.claude/settings.json`:

| Variable | Used by |
|---|---|
| `SKYRIM_TOOLS_REPO` | skills (script paths) |
| `SKYRIM_TOOLS_HOME` | launchers: default root for the next three |
| `HOUSECARL_EXE`, `HOUSECARL_DATA_DIR` | `run_housecarl.cmd`; not written by setup, set them to use a houseCARL built from source |
| `SKYRIM_MO2_DIR` | houseCARL's default instance, `addrlib.py` (Address Library .bin) |
| `SKYRIM_GAME_DIR` | `addrlib.py` fallback, setup's SkyrimSE.exe copy |
| `SKYRIM_RE_DIR` | `run_ghidra_mcp.cmd`, `skyrim_paths.py`, RE skill |

`.mcp.json` starts both servers through `${CLAUDE_PLUGIN_ROOT}/scripts/...cmd`, so the plugin has no absolute paths.
Claude Code runs an installed plugin from its cache copy: after changing skills or `.mcp.json` here, run
`/plugin marketplace update skyrim-tools` and restart the session. Scripts are called through `%SKYRIM_TOOLS_REPO%`,
so script edits apply at once.

On the author's machine the variables point at the existing installs: `HOUSECARL_EXE` = the build from
`D:\Games\Issen\houseCARL\.claude\worktrees\relative-game-path` (relative `gamePath` fix, not in a release yet),
`HOUSECARL_DATA_DIR` = `D:\Games\Issen\houseCARL-data`, `SKYRIM_RE_DIR` = `D:\Games\Issen\re`. Skyrim-Animation-Studio and
the project tools (RDF, IssenFramework) stay in their own repos and are listed in `skyrim-local-toolbox`.

Project-specific skills stay in their project (e.g. `issen-strike-series` in `D:\Games\Issen\.claude\skills`).
