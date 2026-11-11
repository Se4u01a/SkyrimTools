# SkyrimTools

Everything gathered while modding Skyrim SE 1.5.97 (IssenFramework, ReactiveDodgeFramework, DismemberingFramework):
MCP servers, skills, scripts and working practices. Installable on any Windows machine with `setup.cmd`.

It works with **any** coding agent — Claude Code, Codex, VS Code/Copilot, Cursor, Windsurf, Cline, Gemini CLI,
opencode. Claude Code is just the packaging it ships first: open **[AGENTS.md](AGENTS.md)** for the agent-facing guide
(repo map, environment variables, MCP wiring, script reference, the rules that matter), and
[docs/mcp-clients.md](docs/mcp-clients.md) for connecting the two MCP servers to a client that is not Claude Code.

**По-русски:** что умеет набор — [FEATURES.md](FEATURES.md), как установить — [INSTALL.md](INSTALL.md).

## Contents

| Path | What |
|---|---|
| `AGENTS.md` | agent guide — the single source of truth for any agent; `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules`, `.windsurf/rules`, `.clinerules`, `llms.txt` are thin adapters to it |
| `docs/mcp-clients.md` | MCP server config for Claude Code, Codex, VS Code, Cursor, Windsurf, Cline, Gemini CLI, opencode |
| `skills/README.md` | index of the 12 skills — what each answers, and whether it needs houseCARL |
| `scripts/agents/` | `doctor.ps1` (is this machine installed and usable?), `connect.ps1` (MCP config + skill junctions for any agent), `selftest.py` (self-test; CI runs it, `--live` checks this machine) |
| `CONTRIBUTING.md` | house rules for changing the repo (EOLs, no absolute paths, adding skills/scripts) |
| `FEATURES.md`, `INSTALL.md` | what the toolkit does, how to install it (Russian, for users) |
| `.claude-plugin/plugin.json` | plugin manifest (`skyrim-tools`) |
| `.claude-plugin/marketplace.json` | local marketplace `skyrim-tools` with this one plugin |
| `.mcp.json` | MCP servers: `housecarl` (load order, records, Papyrus, Nexus), `pyghidra-mcp` (Ghidra) |
| `skills/` | `skyrim-local-toolbox` (catalog of all tools), `nexus-api-search` (preferred Nexus lookups via GraphQL), `skyrim-modding-practices`, `skyrim-reverse-engineering`, `papyrus-compiler`, and from houseCARL: `spid-authoring`, `kid-authoring`, `skypatcher-authoring`, `open-animation-replacer`, `papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring` |
| `scripts/re/` | Address Library, thread snapshots, .pdb symbols, disassembly, vtable slots, Ghidra MCP launcher and CLI client |
| `scripts/papyrus/` | `papyrusc.py`: compile `.psc` -> `.pex` with the MO2 load order's imports (open-source papyrus-compiler from setup, or the CK's) |
| `scripts/esp/` | `espscan.py` (plugin records), `pexdis.py` (.pex disassembly) |
| `scripts/misc/` | `merge_ini.py` (merge new ini keys into a deployed ini), `font_has.py` (font glyph check), `nexus_gql.py` (Nexus search / description / files via the anonymous GraphQL API) |
| `scripts/run_sage_havok.cmd` | launcher for `SageHavokEditor` GUI |
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

## Any other agent

The plugin is the Claude Code path; everything below is host-neutral. Details in [AGENTS.md](AGENTS.md).

| Step | Command |
|---|---|
| is the machine installed and usable? | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1 -Fix` |
| do the tools actually work here? | `python scripts\agents\selftest.py --live` (`--ghidra` also starts pyghidra-mcp) |
| install / repair | `setup.cmd -Yes -Mo2Dir "<folder with ModOrganizer.ini>"` — the same `setup.ps1`, no agent needed |
| find the right knowledge | [skills/README.md](skills/README.md) (index of all 12 skills), then read the whole `SKILL.md` |
| connect the MCP servers | [docs/mcp-clients.md](docs/mcp-clients.md), or `scripts\agents\connect.ps1 -Client <codex\|vscode\|cursor\|windsurf\|cline\|gemini\|opencode\|json>` prints the block for this machine |
| reuse the skills | `scripts\agents\connect.ps1 -Client codex -LinkSkills` junctions every skill into `~\.codex\skills` (`-Client claude` for `~\.claude\skills`, `-Client dsh` for `~\.dsh\skills`, `-SkillsTarget <dir>` for anything else) |

Repos that read a fixed instruction file get one: `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`,
`.cursor/rules/skyrim-tools.mdc`, `.windsurf/rules/skyrim-tools.md`, `.clinerules/skyrim-tools.md`, `llms.txt` — each is a
short adapter, and `AGENTS.md` stays the source of truth. VS Code users opening this repo get both MCP servers from
`.vscode/mcp.json` without configuring anything.

On the author's machine the variables point at the existing installs: `HOUSECARL_EXE` = the build from
`D:\Games\SkyrimTools\houseCARL\.claude\worktrees\relative-game-path` (relative `gamePath` fix, not in a release yet),
`HOUSECARL_DATA_DIR` = `%LOCALAPPDATA%\SkyrimTools\housecarl-data`, `SKYRIM_RE_DIR` = `D:\Games\SkyrimTools\re` (Ghidra 12.2).
Skyrim-Animation-Studio and the project tools (RDF, IssenFramework) stay in their own repos and are listed in `skyrim-local-toolbox`.

Project-specific skills stay in their project (e.g. `issen-strike-series` in `D:\Games\Issen\.claude\skills`).
