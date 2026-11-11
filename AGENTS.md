# SkyrimTools — agent guide

This repository is a **Skyrim SE modding toolkit for coding agents**, not an application: there is nothing to build;
`python scripts\agents\selftest.py` is the test suite (CI runs it on every push). It holds Markdown knowledge bases (the `skills/`), three MCP server launchers, and small
Python/PowerShell scripts that read plugins, Papyrus, fonts, INIs, Address Library and memory. The heavy parts
(houseCARL, Ghidra, JDK, a Python venv, a copy of `SkyrimSE.exe`) live **outside** the repo in
`%LOCALAPPDATA%\SkyrimTools`; the repo carries no binaries, no mods, no game assets.

It is packaged as a Claude Code plugin (`.claude-plugin/`, `.mcp.json`), but nothing here depends on Claude Code:
any agent that can read files, run a shell command and speak MCP can use it. This file is the entry point for all of
them. Human-facing docs: [README.md](README.md) (English), [INSTALL.md](INSTALL.md) and [FEATURES.md](FEATURES.md)
(Russian).

All of it is Windows-only (MO2, .NET launchers, `ctypes` into dbghelp/psapi) and 1.5.97-first: on AE 1.6.x everything
except the reverse-engineering scripts still works.

## 0. Fast path

1. **Is it installed?** Run the checker; it prints what is present, what is missing and what to run next:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1
   ```
   `-Json` gives machine-readable output, `-Fix` lists the exact commands that repair each gap.
2. **Not installed / half installed:** `setup.cmd -Yes -Mo2Dir "<folder with ModOrganizer.ini>"` (add `-Ghidra` only
   if the task needs decompilation). It needs no agent: it prints a plan, downloads, checks SHA-256, writes the
   `SKYRIM_*` user environment variables and registers the Claude Code plugin. Re-running it is the upgrade path.
3. **Before any mod work**, read [skills/skyrim-modding-practices/SKILL.md](skills/skyrim-modding-practices/SKILL.md):
   those rules were each paid for with a debugging round and they override your defaults.
4. **Find the right skill** in [skills/README.md](skills/README.md). A skill is not a filename to skim: read its
   `SKILL.md` in full, then the `references/` file it tells you to open.
5. **Wire the MCP servers** with [docs/mcp-clients.md](docs/mcp-clients.md): `scripts\agents\connect.ps1 -Client <name>`
   prints a ready-to-paste config with absolute paths resolved for this machine.

## 1. Repository layout

| Path | What |
|---|---|
| `AGENTS.md` | this file — the single source of truth for agents |
| `README.md`, `FEATURES.md`, `INSTALL.md` | install, capabilities, Russian user docs |
| `skills/` | 15 agent skills, each `<name>/SKILL.md` + `<name>/references/`; index in `skills/README.md` |
| `.mcp.json` | MCP servers for Claude Code (`${CLAUDE_PLUGIN_ROOT}` is Claude-only) |
| `.claude-plugin/` | Claude Code plugin + local marketplace manifests |
| `scripts/agents/` | `doctor.ps1`, `connect.ps1`, `selftest.py` — install check, MCP/skill wiring for any agent, self-test |
| `scripts/run_skylink.cmd` | launcher for the optional `skylink` MCP server (SkyLink AI, the running game) |
| `.github/workflows/selftest.yml` | CI: the static self-test on `windows-latest` for every push and pull request |
| `scripts/esp/` | `espscan.py` (raw plugin records), `pexdis.py` (`.pex` disassembler), `espdiff.py` (record-level diff of two plugins) |
| `scripts/logs/` | `crash_triage.py`, `papyrus_triage.py`, `skse_load_status.py`, `mirror_logs.py` — crash, Papyrus and SKSE log triage; `_paths.py` finds the `Documents\My Games` folder |
| `scripts/save/` | `ess_scan.py` (read a `.ess`: header, plugins, strings, FormIDs), `cosave_info.py` (SKSE co-save chunk inventory) |
| `scripts/misc/` | `merge_ini.py`, `font_has.py`, `nexus_gql.py` |
| `scripts/papyrus/` | `papyrusc.py` — compile `.psc` with the MO2 load order's imports (open-source compiler or the CK's) |
| `scripts/re/` | Address Library, thread snapshots, `.pdb` symbols, disassembly, vtables, Ghidra launchers |
| `data/se_id_names.tsv` | REL::ID → name table used by the RE scripts and skills |
| `setup.cmd` / `setup.ps1` | installer / upgrader (environment, houseCARL, optional RE workspace) |
| `requirements-re.txt` | pinned Python packages of the RE venv |
| `CONTRIBUTING.md` | house rules for changing this repo (EOLs, paths, adding a skill or script) |
| `CHANGELOG.md` | what changed in each tagged version (`plugin.json` carries the number) |

Everything the repo writes to the user's machine is either a user environment variable or a **new MO2 mod folder**.
Never edit an existing mod, `plugins.txt` or `ModOrganizer.ini` unless the user explicitly asked for it.

## 2. Environment variables (written by `setup.ps1`, read by launchers, scripts and skills)

| Variable | Meaning | Default |
|---|---|---|
| `SKYRIM_TOOLS_REPO` | this repo (scripts, `data/`) | — set by setup |
| `SKYRIM_TOOLS_HOME` | root of the heavy parts | `%LOCALAPPDATA%\SkyrimTools` |
| `HOUSECARL_EXE` | houseCARL server exe | `%SKYRIM_TOOLS_HOME%\housecarl\server\housecarl-mcp.exe` (set by hand to use a source build) |
| `HOUSECARL_DATA_DIR` | houseCARL settings | `%SKYRIM_TOOLS_HOME%\housecarl-data` |
| `SKYRIM_MO2_DIR` | MO2 instance folder (contains `ModOrganizer.ini`) | — unset until setup/user sets it |
| `SKYRIM_GAME_DIR` | game folder (`SkyrimSE.exe`) | — unset unless detected |
| `SKYRIM_RE_DIR` | RE workspace (Ghidra, JDK, venv, `projects\`, `bins\`) | `%SKYRIM_TOOLS_HOME%\re`, only with `-Ghidra` |
| `SKYRIM_ADDRLIB_BIN` | Address Library `.bin` override (optional) | found under MO2 mods or game `Data` |
| `PAPYRUS_COMPILER_DIR` | papyrus-compiler folder override (optional) | `%SKYRIM_TOOLS_HOME%\papyrus-compiler` (setup.cmd) |
| `SKYRIM_DOCUMENTS_DIR` | the game folder under `Documents\My Games` (e.g. `...\Skyrim Special Edition`) for the log and save scripts (optional) | found per game folder, SE first |
| `SKYLINK_EXE` | SkyLink AI server exe override (optional) | `%SKYRIM_TOOLS_HOME%\skylink\server\SkyrimMCP.exe` |

Syntax by shell: cmd `%VAR%`, PowerShell `$env:VAR`, Git Bash `$VAR`. **An unset variable means that part is not
installed** — say so and ask for the path; do not guess a `D:\...` path from an example in the docs.

## 3. MCP servers

Three stdio servers, all launched by `.cmd` wrappers that read the variables above, so they need no arguments:

| Server | Launcher | Ready when | Gives you |
|---|---|---|---|
| `housecarl` | `scripts\run_housecarl.cmd` | `%HOUSECARL_EXE%` exists (needs .NET Runtime 10 x64) | the live MO2 load order: record reads/writes, conflicts, patches, Papyrus (de)compile, BSA, NIF, SKSE layer, Nexus |
| `pyghidra-mcp` | `scripts\re\run_ghidra_mcp.cmd` | `%SKYRIM_RE_DIR%\venv`, `jdk-*`, `ghidra_*_PUBLIC` exist | headless Ghidra: decompile, disassemble, xrefs (auto-attaches CommonLibSSE GDT archives) |
| `skylink` | `scripts\run_skylink.cmd` | optional: `%SKYLINK_EXE%` exists (`setup.cmd -SkyLink`); it starts without the game, but its tools answer only while Skyrim runs through SKSE with the `SkyLink AI` mod enabled | the running game: player, inventory, quests, NPCs, Papyrus calls, console; read freely, change only on the user's explicit request |

houseCARL tool names are `housecarl_<tool>` on every host — `housecarl_records`, `housecarl_asset_status`,
`housecarl_apply`, `housecarl_create`, `housecarl_forward`, `housecarl_check`, `housecarl_compile_script`,
`housecarl_decompile_script`, `housecarl_bsa_extract`, `housecarl_skse`, `housecarl_load_order_status`,
`housecarl_skypatcher_layer`, `housecarl_set_mo2_instance`. Start from `housecarl_load_order_status` to see which
instance houseCARL resolved; the full argument surface is in the server's own `tools/list` and in the skills.
`pyghidra-mcp` starts a JVM: allow 20–60 s for the first connection, and the first analysis of `SkyrimSE.exe` takes
tens of minutes (it is cached in the Ghidra project afterwards).

**If `skylink` is not available or the game is not running**, say so and stop: there is no substitute for a live read,
and never take over the user's desktop (screenshots, keystrokes, window focus) or launch the game yourself.

**If `housecarl` is not available**, do not improvise record writes. Use the substitutes and say what cannot be done
exactly — the table is in [skills/skyrim-local-toolbox/SKILL.md](skills/skyrim-local-toolbox/SKILL.md): `espscan.py`
for record reads, `pexdis.py` for `.pex`, plain file search under `mods\` for asset winners, and no writes at all.
**If `pyghidra-mcp` is not available**, `scripts/re/*.py` still cover offsets, stacks and disassembly from the exe on
disk; see [skills/skyrim-reverse-engineering/SKILL.md](skills/skyrim-reverse-engineering/SKILL.md).

## 4. Skills (the knowledge in this repo)

`skills/<name>/SKILL.md` is an Agent Skill: YAML frontmatter with `name`, `description` and usually `compatibility`,
then the full instructions, then pointers into `references/`. To use one, read the whole `SKILL.md` and open the
reference it names — the frontmatter is for routing, not the content. In Claude Code a plugin skill is called
`housecarl:<name>`; on every other host it is the bare folder name (`papyrus-reference`). The skills already say this.

| Skill | Load it for |
|---|---|
| `skyrim-modding-practices` | the working rules: file editing, MO2 deploys, INI merges, git, honest reporting — read first |
| `skyrim-local-toolbox` | which tool/path does the job on this machine, and the fallback when houseCARL is missing |
| `spid-authoring` | SPID 7.3 `_DISTR.ini` — distributing spells/perks/items/keywords/outfits to NPCs |
| `kid-authoring` | KID 3.5 `_KID.ini` — keywords onto item records |
| `skypatcher-authoring` | SkyPatcher 6.4.1 — editing record fields, containers, leveled lists without an ESP |
| `open-animation-replacer` | OAR 3.x `config.json` conditions, priorities, DAR `_conditions.txt` conversion |
| `papyrus-reference` | offline Papyrus/SKSE/plugin-API signature corpus (`references/index.jsonl` → shard + line) |
| `mutagen-reference` | offline record schema: fields, types, cardinality, writability, enum values |
| `skse-plugin-authoring` | native SKSE DLLs (C++, CommonLibSSE-NG): skeleton, hooks, event sinks, SE/AE/VR, load failures |
| `skyrim-reverse-engineering` | crash/offset/hang analysis: REL::IDs, thread snapshots, `.pdb`, Ghidra |
| `skyrim-engine-knowledge` | how the engine actually behaves: Papyrus runtime, records and plugins, save safety, NIF/audio, VR differences, porting to VR |
| `skyrim-troubleshooting` | crash, freeze, Papyrus error storm, an SKSE DLL that did not load, a save problem, whether a mod change is safe — evidence to a verdict with `scripts/logs`, `scripts/save`, `scripts/esp` |
| `skyrim-live-game` | the RUNNING game through SkyLink AI (`skylink`) or DevBench: read freely, change only on the user's explicit request |
| `nexus-api-search` | Nexus Mods lookups through the anonymous GraphQL API (no key, no browser) |
| `papyrus-compiler` | compiling `.psc` -> `.pex` here: compiler choice, MO2 import order, generated vanilla headers, errors |

The three `index.jsonl` corpora (`papyrus-reference`, `mutagen-reference`, `spid-authoring`) are lookups, not reading:
grep for the exact quoted token, e.g. `"name":"GetActorValue"`, and it returns the shard file and the 1-indexed line.
Two skills (`papyrus-reference`, `mutagen-reference`) answer offline; only the parts that read a live load order need
houseCARL.

Other agents can point at this repo's skills instead of copying them:
`scripts\agents\connect.ps1 -Client codex -LinkSkills` creates one directory junction per skill in the agent's skills
folder — `-Client codex` for `~\.codex\skills`, `-Client claude` for `~\.claude\skills`, `-Client dsh` for
`~\.dsh\skills` (DeepSeek Harness: desktop app, CLI and the ACP profile Zed spawns all read it), or
`-SkillsTarget <dir>`. DeepSeek Harness also scans `<project>\.dsh\skills`, `<project>\.agents\skills` and
`~\.agents\skills`, one level deep (`<root>\<name>\SKILL.md`), and reads user-global instructions from
`~\.dsh\AGENTS.md`. Without junctions, tell the agent in its own instructions where `skills/` lives.

## 5. Scripts

Python scripts are stdlib-only unless noted; they take paths as arguments and print UTF-8. Run them with any Python 3
(`python` on PATH); the ones marked *RE venv* need `%SKYRIM_RE_DIR%\venv\Scripts\python`, and the *Ghidra* ones need a
running `pyghidra-mcp` on streamable HTTP.

| Script | Use |
|---|---|
| `scripts\agents\selftest.py [--live] [--ghidra] [--net] [-k TEXT] [-v]` | self-test: static checks + synthetic fixtures (CI); `--live` adds real data and the MCP launchers on this machine |
| `scripts\esp\espscan.py PLUGIN.esp text\|ref\|dump ...` | records containing a string / FormID; subrecords of one record — record reads without houseCARL |
| `scripts\esp\pexdis.py FILE.pex` | disassemble a Papyrus `.pex` |
| `scripts\misc\merge_ini.py DIST DEPLOYED` | add new keys of a shipped INI to the deployed one, keeping every tuned value and line |
| `scripts\misc\font_has.py FONT [codepoints]` | does a TTF/OTF map the glyphs (default: Cyrillic) |
| `scripts\misc\nexus_gql.py search\|grep\|mod\|desc\|files\|raw ...` | Nexus Mods through the public GraphQL API |
| `scripts\papyrus\papyrusc.py compile\|imports\|headers\|which ...` | compile Papyrus `.psc` to `.pex` with the imports of the live MO2 load order; skill `papyrus-compiler` |
| `scripts\logs\crash_triage.py [dir-or-file] [--frames N] [--all] [--known FILE]` | CrashLogger/trainwreck dumps (`SKSE`, `SKSE\Crashlogs`) -> ranked signatures, the denominator first |
| `scripts\logs\papyrus_triage.py [logfile] [--top N] [--all]` | `Papyrus.N.log` -> error shapes bucketed by form, attributed to scripts |
| `scripts\logs\skse_load_status.py [filter] [--log PATH]` | what SKSE did with each DLL on the last launch (`skse64.log` + loader log) |
| `scripts\logs\mirror_logs.py [--dest DIR]` | append-only copy of SKSE, crash and Papyrus logs into `%SKYRIM_TOOLS_HOME%\log-mirror`, before the next launch rotates them |
| `scripts\logs\_paths.py` | module, not a CLI: finds `Documents\My Games` SE-first; `SKYRIM_DOCUMENTS_DIR` overrides |
| `scripts\save\ess_scan.py list\|info\|plugins\|search\|strings\|forms ...` | read a `.ess` (SE/AE, its own LZ4), never writes; a partial parse reports INCONCLUSIVE |
| `scripts\save\cosave_info.py COSAVE.skse [--chunks] [--top N]` | SKSE co-save structure to JSON: header, chunk inventory, coverage |
| `scripts\esp\espdiff.py diff OLD NEW \| summary PLUGIN... [--list-overrides]` | what was added, removed or changed between two plugins; masters, new records, overrides |
| `scripts\run_sage_havok.cmd` | launch SageHavokEditor GUI (`tools\SageHavokEditor\SageHavokEditor.exe`) |
| `scripts\re\addrlib.py id\|off\|dump ...` | REL::ID ↔ RVA of `SkyrimSE.exe` (needs the Address Library `.bin`) |
| `scripts\re\build_id_names.py [SRC_DIR...]` | rebuild `data/se_id_names.tsv` (maintainer only) |
| `scripts\re\thread_stacks.py [pid] --busy --ids` | snapshot every thread of the running/hung game |
| `scripts\re\pdbsym.py DLL.dll RVA...` | name functions of a DLL from its `.pdb` |
| `scripts\re\disasm_at.py EXE RVA...` | disassemble around return addresses — *RE venv* |
| `scripts\re\calls_in.py START END` | calls a code range makes, targets named by REL::ID — *RE venv* |
| `scripts\re\find_vcall.py OFFSET DEPTH ROOT...` | where a virtual call with this vtable offset happens — *RE venv* |
| `scripts\re\vtable_slot.py ID SLOT` | read a vtable slot and disassemble its target — *RE venv* |
| `scripts\re\swf_as2.py FILE.swf [--names]` | skim ActionScript 2 of a Scaleform `.swf` |
| `scripts\re\decomp.py BINARY NAME\|0xADDR...` | decompile through the MCP server — *Ghidra* |
| `scripts\re\mcp_call.py [--url URL] tools\|<tool> '{json}'` | call any `pyghidra-mcp` tool from the CLI — *Ghidra* |

`scripts\run_housecarl.cmd`, `scripts\run_skylink.cmd` and `scripts\re\run_ghidra_mcp.cmd` are the MCP launchers; the Ghidra one also accepts extra
arguments (`-t streamable-http -p 8765`) so the Ghidra tools can be driven from a shell without an MCP client.

## 5.1 Optional third-party tools (not installed by `setup.ps1`)

Used when present; `doctor.ps1` reports them, nothing breaks without them. Put them in place by hand.

| Tool | Where it is looked for | Used by |
|---|---|---|
| [Skyrim RE Toolkit](https://github.com/ByteBard97/skyrim-re-toolkit) GDT archives | `%SKYRIM_RE_DIR%\gdt\CommonLibSSE_SE_b93280e.gdt` | `run_ghidra_mcp.cmd` passes it as `--gdt`, so decompiled code shows CommonLibSSE types (`Actor`, `TESObjectREFR`) |
| [BethesdaGhidraScripts](https://github.com/doodlum/BethesdaGhidraScripts) | `%SKYRIM_RE_DIR%\BethesdaGhidraScripts\` | by hand: imports CommonLib/Address Library symbols, vtables and signatures into a Ghidra project |
| [SageHavokEditor](https://github.com/TheSageLenny/Sage-Havok-Editor) | `%SKYRIM_TOOLS_REPO%\tools\SageHavokEditor\SageHavokEditor.exe` (gitignored) | `scripts\run_sage_havok.cmd`: behavior graph (`.hkx`) editor GUI |

The heavy parts may also sit in the repo root instead of `%SKYRIM_TOOLS_HOME%`: `re\`, `houseCARL\`, `houseCARL-data\`
and `tools\` are gitignored, and the launchers fall back to `re\` and a `houseCARL\` build there when the variables point
at a folder that no longer exists.

## 6. Rules that outrank your defaults

Condensed from `skyrim-modding-practices`; the skill has the reasoning and the full list.

- **Never write into another author's mod folder.** A patch, a SPID/KID/SkyPatcher INI or an OAR submod goes into a
  **new** MO2 mod folder, and a new folder does nothing until the user enables it — say so every time.
- **Never copy a shipped INI over a deployed one.** The user tunes values in the game menu; `merge_ini.py` keeps every
  existing value and adds only new keys.
- **Never edit `ModOrganizer.ini` while MO2 runs** — MO2 rewrites it on exit. Editing `plugins.txt`/`modlist.txt` by hand
  is also out of bounds; the user does that in the GUI.
- **No game assets in git.** Clips, meshes, textures and other mods' files stay in MO2 mod folders (licences forbid
  re-uploads). Commit recipes, listings and scripts that rebuild them.
- **The user is the only one who tests in game.** Never run the game or claim a change works in it. Finish with
  "built, NOT tested in game" plus what the user must do (enable the mod, rerun Pandora, restart).
- **Reading the running game is allowed; changing it is not, unless asked.** Read live state when the user has the game
  open; any change (items, quests, console, save/load) needs an explicit request from the user in this conversation.
- **Verify engine facts, never quote them.** An address, REL::ID, vtable slot or "IDA says" comment is checked with
  `addrlib.py`, Ghidra or the real code before it is used or written into a comment.
- **Keep EOLs and encodings.** The repo stores LF and `core.autocrlf=true` checks it out as CRLF here, so keep a file's
  existing EOL rather than normalising it; `.cmd` and `.ps1` stay CRLF. FLICK translations are UTF-16LE with BOM, and
  `setup.ps1` is UTF-8 **with** BOM (Windows PowerShell 5.1 reads a BOM-less script as ANSI, which turns its Russian
  strings into garbage). An exact-match edit that mysteriously fails is usually EOL or tabs.
- **Editing files beats shell heredocs.** Bash heredocs here halve backslashes and drop tabs; write the file or use a
  targeted edit.
- **Commit each finished change** (clear message, attribution) so the user can roll back after testing; rejected
  experiments go on a `wip/...` branch.
- **Untrusted downloads** go to their own empty folder and are read with `python -I`; check Nexus permissions before
  redistributing anything.

## 7. Reporting back

State what was read and what was run, not what was assumed. If a step needed houseCARL but only `espscan.py` was
available, say that the result is raw subrecords and not the resolved record. If an environment variable was unset,
name it. Anything that ended in a game-visible change is unverified until the user says otherwise.

## 8. Changing this repo

[CONTRIBUTING.md](CONTRIBUTING.md) has the conventions; the short version: keep the Markdown knowledge and the script
docstrings in sync, no absolute paths, no binaries, `.cmd`/`.ps1` CRLF and everything else as it is (LF in the repo,
CRLF in the working copy), and when you add a script or a skill, update `AGENTS.md`, `README.md`, `skills/README.md`
and the file of the agent whose instructions you touched. Before committing, run `python scripts\agents\selftest.py`
(and `--live` when you touched a script or a launcher); a new script also gets a row in its `SCRIPTS` table and,
when it can be fed a synthetic input, a fixture check.
