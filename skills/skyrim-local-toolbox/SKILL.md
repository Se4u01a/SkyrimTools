---
name: skyrim-local-toolbox
description: >-
  Catalog of every Skyrim modding tool on this machine and where it lives: the SkyrimTools plugin's MCP servers
  (houseCARL, pyghidra-mcp) and scripts (espscan, pexdis, addrlib, thread_stacks, merge_ini, font_has), the
  project tools in RDF / IssenFramework (hkxcheck, Pandora staging, clip sets, DF packs), Skyrim-Animation-Studio's
  issen-clip / df-limb, SageHavokEditor, Skyrim RE Toolkit, BethesdaGhidraScripts, and the MO2 instances. Load when you
  need a tool for a Skyrim task and do not know which one, when a housecarl_* tool is not loaded and a local substitute
  is needed, or when you need to find which mod provides a file, read an .esp record or a .pex, or locate the MO2 instances.
---

# Local Skyrim toolbox

SkyrimTools (git) is a modding toolkit for coding agents: a Claude Code plugin, and without any change the same skills,
two MCP servers and small scripts for every other agent (`AGENTS.md` in the repo root is the guide; `skills/README.md`
lists the skills). `setup.cmd` in its folder installs the heavy parts and writes user environment variables; every path
below goes through them (cmd `%VAR%`, Git Bash `$VAR`, PowerShell `$env:VAR`). The repo's `README.md` / `INSTALL.md` say
how it is installed and updated, `scripts\agents\doctor.ps1 -Fix` says what is missing on this machine. Working rules
learned along the way: skill `skyrim-modding-practices`.

## Paths (environment variables written by setup.ps1)
| Variable | What |
|---|---|
| `SKYRIM_TOOLS_REPO` | the SkyrimTools repo (scripts, `data\`, and on this machine `houseCARL\`, `re\`, `tools\`) |
| `SKYRIM_TOOLS_HOME` | install root of the heavy parts, default `%LOCALAPPDATA%\SkyrimTools` (`housecarl\server`, `housecarl-data`, `re\`) |
| `SKYRIM_MO2_DIR` | the MO2 instance, the folder with `ModOrganizer.ini` |
| `SKYRIM_GAME_DIR` | the game folder (`SkyrimSE.exe`) |
| `SKYRIM_RE_DIR` | RE workspace (Ghidra, JDK, venv), on this machine in repo root `%SKYRIM_TOOLS_REPO%\re` (`setup.cmd -Ghidra` on clean installs) |
A variable that is unset means that part is not installed or was skipped: say so, and ask the user for the path
rather than guessing. MO2 layout: `mods\`, `profiles\<profile>\modlist.txt` (`+` enabled, `-` disabled, top line =
highest priority), `overwrite\`. SKSE logs: `%USERPROFILE%\Documents\My Games\Skyrim Special Edition\SKSE\`
(`<Plugin>.log`, crash logs).

## The author's machine (Sequoia)
Everything from here on that names `D:\...` (instances, Skyrim-Animation-Studio, RDF / IssenFramework tools, the
projects) exists only on the author's machine. On another machine check that the path exists before using it.
- STB (the game being played): `D:\Games\stb\[STB] Mod Organizer`, profile `SBORKA`. Game `D:\Games\stb`, 1.5.97.
- SDS: `D:\Games\stb\[SDS] - Mod organizer` — source of MCO/Orshdan clips, not played.
- RE2CE TEST: `D:\Games\stb\[RE2CE TEST] Mod Organizer`, profile `RE2CE` — clean animation test bed (same game
  folder, vanilla masters only): SKSE (+ Address Library bins), Open Animation Replacer (IED addon removed; animation
  log ON, written to the SKSE OAR log), SKSE Menu Framework, and the mod under test. Local saves/INIs. Test clips here,
  not in STB, so other OAR/DAR mods cannot win the frames. Copy a rebuilt mod over its folder in `mods\`.

## MCP servers (SkyrimTools `.mcp.json`)
| Server | What | Installed |
|---|---|---|
| `housecarl` | load order, records read/write, conflicts, Papyrus (de)compile, BSA, NIF, Nexus, SKSE layer | `scripts\run_housecarl.cmd` -> `%HOUSECARL_EXE%`, else repo build in `houseCARL\` or release in `%SKYRIM_TOOLS_HOME%\housecarl\server`; settings in `%HOUSECARL_DATA_DIR%` (default `%SKYRIM_TOOLS_HOME%\housecarl-data`); instance = `%SKYRIM_MO2_DIR%` or the one saved with `housecarl_set_mo2_instance`. Author's machine: exe built from `%SKYRIM_TOOLS_REPO%\houseCARL\.claude\worktrees\relative-game-path\src\housecarl-mcp\bin\Release\net10.0\housecarl-mcp.exe` (relative `gamePath=..\` fix, not merged) |
| `pyghidra-mcp` | Ghidra decompile / disassemble / xrefs | `scripts\re\run_ghidra_mcp.cmd` + workspace `%SKYRIM_RE_DIR%` (`%SKYRIM_TOOLS_REPO%\re`, contains Ghidra 12.2 in `ghidra_12.2_PUBLIC` + CommonLibSSE GDT type archives) — see `skyrim-reverse-engineering` |

The authoring skills (`spid-authoring`, `kid-authoring`, `skypatcher-authoring`, `open-animation-replacer`,
`papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring`) come from houseCARL (commit a4dc3ebe) and call
`housecarl_*` tools. Prefer those tools when loaded (ToolSearch "housecarl"); if not, use the substitutes below and
say so when a step cannot be done exactly.

## Substitutes when the housecarl_* tools are not loaded
| houseCARL tool | Here |
|---|---|
| `asset_status` (which mod wins a path) | search `mods\*\<path>` (Glob), order by `modlist.txt`; BSAs: check `mods\<mod>\*.bsa` |
| `records` read / FormID lookup | `python %SKYRIM_TOOLS_REPO%\scripts\esp\espscan.py plugin.esp text|ref|dump ...` (raw subrecords; `import espscan` gives `records()`, `subrecords()`, `edid()`) |
| `decompile_script` | `python %SKYRIM_TOOLS_REPO%\scripts\esp\pexdis.py file.pex` (disassembly) or the mod's `scripts\source\*.psc` |
| `compile_script` | none outside houseCARL; check signatures with `papyrus-reference` |
| `skse` layer | read `mods\*\SKSE\Plugins\*.ini|*.json` and the SKSE logs |
| `nif_inspect` | Skyrim-Animation-Studio's crates read NIFs (`df-limb`); else ask the user to open NifSkope |
| `writes` (`apply`, `create`, ...) | never hand-write plugins; use SPID/KID/SkyPatcher INIs in a new MO2 mod folder |

## SkyrimTools scripts (`%SKYRIM_TOOLS_REPO%\scripts`)
- `esp\espscan.py`, `esp\pexdis.py` — above.
- `re\*.py` — addrlib, thread_stacks, pdbsym, disasm_at, vtable_slot, calls_in, find_vcall, swf_as2, decomp,
  mcp_call, build_id_names: see `skyrim-reverse-engineering`.
- `misc\merge_ini.py DIST DEPLOYED` — add the keys of a shipped ini missing from the deployed one, every existing value
  and line kept (the user tunes values in game; see `skyrim-modding-practices`).
- `misc\nexus_gql.py search|grep|mod|desc|files` — Nexus Mods lookups through the anonymous GraphQL API; see skill
  `nexus-api-search` (use it before WebFetch on nexusmods.com).
- `misc\font_has.py FONT [hex codepoints]` — does a TTF/OTF have the glyphs (default: Cyrillic) — for FLICK/SkyUI fonts.
- `run_sage_havok.cmd` — launcher for `SageHavokEditor` GUI.

## Animation tools
- Skyrim-Animation-Studio, `D:\projects\Skyrim-Animation-Studio` (Rust, branch `issen-sequence`,
  `cargo build --release -p <crate>`), `target\release\`:
  - `issen-clip.exe` — `dump`, `annotate`, `rewrite`, `sequence` (.seq.json series), `--sheet-list` sprite sheets.
    Needs Windows paths (`D:/...`). Usage: skill `issen-strike-series` (IssenFramework project).
  - `df-limb.exe` — cuts Dismembering Framework limb meshes out of creature bodies (driven by
    IssenFramework `tools\build_df_pack.py`).
  - `sds-anim-studio.exe` — the GUI studio (clip playback on NPCs, annotations, Precision/PIE/SCAR previews, OAR export).
  - Bone tracks of a clip: a throwaway `crates/hkx/examples/<name>.rs` using `sds_hkx::anim::read_animation`.
- OAR is 3.2 (V3 conditions API) in STB. Payload Interpreter configs: `SKSE\PayloadInterpreter\Config\*.ini` map
  `PIE.$Name` annotations to `@CAST|form|plugin...`. Only annotations named after a graph event reach plugins (PIE is one).

## Behavior graphs (ReactiveDodgeFramework `tools\`, `D:\Games\Issen\ReactiveDodgeFramework`)
- `SageHavokEditor` (`scripts\run_sage_havok.cmd` -> `%SKYRIM_TOOLS_REPO%\tools\SageHavokEditor\SageHavokEditor.exe`,
  upstream [TheSageLenny/Sage-Havok-Editor](https://github.com/TheSageLenny/Sage-Havok-Editor)) — visual editor and
  graph inspector for Skyrim Havok behavior trees (`.hkx`), state machines, animation annotations, and Pandora/Nemesis patches.
- `hkxcheck.py FILE.xml [--summary NAME|#ID] [--list-sm]` — stdlib checker/inspector of behavior XML (serde-hkx `hkxc`
  or `hkxcmd` output).
- `stage_pandora.py` — runs Pandora outside MO2 into `_work/` (never into the real output mod); `pandora_log.py` —
  FAILED/SKIPPED edits of Engine.log by mod; `dump_pandora_out.py` — Pandora output to XML; `validate_rdf.py` — compare two
  staged runs.
- `gen_rdf_patch.py` / `gen_rdf_nemesis.py` — Pandora patch as single source, Nemesis version generated from it.
- `clip_analyze.py`, `annotate_clips.py`, `build_clip_set.py` — clip root-motion analysis, annotation writing, OAR clip
  sets; `gen_menu_translations.py` — FLICK translations (UTF-16LE BOM, CRLF); `build_fomod.py` — FOMOD archive.

## Reverse engineering toolkits (optional, placed by hand; `setup.ps1` does not install them)
- **Skyrim RE Toolkit** ([ByteBard97/skyrim-re-toolkit](https://github.com/ByteBard97/skyrim-re-toolkit)):
  - Precompiled Data Type Archives (`.gdt`) in `%SKYRIM_RE_DIR%\gdt\` (`CommonLibSSE_SE_b93280e.gdt`, AE, VR).
    `run_ghidra_mcp.cmd` automatically passes `--gdt` to `pyghidra-mcp` so decompiled code resolves raw pointers into
    typed engine structs (`TESObjectREFR`, `Actor`, etc.).
  - Sources and runtime inspection harness in `%SKYRIM_RE_DIR%\skyrim-re-toolkit\`.
- **BethesdaGhidraScripts** ([doodlum/BethesdaGhidraScripts](https://github.com/doodlum/BethesdaGhidraScripts),
  `%SKYRIM_RE_DIR%\BethesdaGhidraScripts\`):
  - Automates Clang-based generation of Ghidra import scripts from CommonLib headers and Address Library.
  - Automatically imports vtables, function signatures, and symbols into Ghidra projects across SE and AE binaries.
- **Ghidra 12.2** (`%SKYRIM_RE_DIR%\ghidra_12.2_PUBLIC\`, official NSA build):
  - Driven headless over MCP by `pyghidra-mcp` (`scripts\re\run_ghidra_mcp.cmd`).

## IssenFramework `tools\`
`import_strike_clips.py` (strike sets -> OAR submods), `render_strike_previews.py` (FLICK preview sheets),
`build_df_pack.py` + `df_packs\` (DF packs for creatures without one).

## Projects (D:\Games\Issen)
IssenFramework (own plugin, git), ReactiveDodgeFramework, SkyrimSE_DismemberingFramework, CommonLibSSE-NG (shared by
xmake builds as `../CommonLibSSE-NG`), `_scratch\` for throwaway files, `_downloads\` for archives (untrusted), `_backups\`.
On the author's machine `houseCARL\` (MCP server source) and `re\` (RE workspace) live in the SkyrimTools repo root
(`%SKYRIM_TOOLS_REPO%\houseCARL`, `%SKYRIM_TOOLS_REPO%\re`, both gitignored), no longer under `D:\Games\Issen`.
