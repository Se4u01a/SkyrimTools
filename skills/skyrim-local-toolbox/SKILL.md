---
name: skyrim-local-toolbox
description: >-
  Catalog of every Skyrim modding tool on this machine and where it lives: the SkyrimTools plugin's MCP servers
  (houseCARL, pyghidra-mcp) and scripts (espscan, pexdis, addrlib, thread_stacks, merge_ini, font_has), the
  project tools in RDF / IssenFramework (hkxcheck, Pandora staging, clip sets, DF packs), Skyrim-Animation-Studio's
  issen-clip / df-limb, and the MO2 instances. Load when you need a tool for a Skyrim task and do not know which one,
  when a housecarl_* tool is not loaded and a local substitute is needed, or when you need to find which mod provides a
  file, read an .esp record or a .pex, or locate the MO2 instances.
---

# Local Skyrim toolbox

SkyrimTools (`D:\Games\SkyrimTools`, git) is a Claude Code plugin: the skills, the two MCP servers and the small
scripts below. Heavy installs stay where they were and are referenced by path. The plugin's `README.md` lists how it
is installed and updated. Working rules learned along the way: skill `skyrim-modding-practices`.

## Instances
- STB (the game being played): `D:\Games\stb\[STB] Mod Organizer` — `mods\`, `profiles\SBORKA\modlist.txt`
  (`+` enabled, `-` disabled, top line = highest priority), `overwrite\`. Game `D:\Games\stb`, 1.5.97.
- SDS: `D:\Games\stb\[SDS] - Mod organizer` — source of MCO/Orshdan clips, not played.
- Logs: `C:\Users\Sequoia\Documents\My Games\Skyrim Special Edition\SKSE\` (`<Plugin>.log`, crash logs).

## MCP servers (SkyrimTools `.mcp.json`)
| Server | What | Installed |
|---|---|---|
| `housecarl` | load order, records read/write, conflicts, Papyrus (de)compile, BSA, NIF, Nexus, SKSE layer | exe built from `D:\Games\Issen\houseCARL\.claude\worktrees\relative-game-path` (branch `claude/relative-game-path`, relative `gamePath=..\` fix, not merged); data `D:\Games\Issen\houseCARL-data`; instance = STB |
| `pyghidra-mcp` | Ghidra decompile / disassemble / xrefs | `scripts\re\run_ghidra_mcp.cmd` + workspace `D:\Games\Issen\re` — see `skyrim-reverse-engineering` |

The authoring skills (`spid-authoring`, `kid-authoring`, `skypatcher-authoring`, `open-animation-replacer`,
`papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring`) come from houseCARL (commit a4dc3ebe) and call
`housecarl_*` tools. Prefer those tools when loaded (ToolSearch "housecarl"); if not, use the substitutes below and
say so when a step cannot be done exactly.

## Substitutes when the housecarl_* tools are not loaded
| houseCARL tool | Here |
|---|---|
| `asset_status` (which mod wins a path) | search `mods\*\<path>` (Glob), order by `modlist.txt`; BSAs: check `mods\<mod>\*.bsa` |
| `records` read / FormID lookup | `python D:\Games\SkyrimTools\scripts\esp\espscan.py plugin.esp text|ref|dump ...` (raw subrecords; `import espscan` gives `records()`, `subrecords()`, `edid()`) |
| `decompile_script` | `python D:\Games\SkyrimTools\scripts\esp\pexdis.py file.pex` (disassembly) or the mod's `scripts\source\*.psc` |
| `compile_script` | none outside houseCARL; check signatures with `papyrus-reference` |
| `skse` layer | read `mods\*\SKSE\Plugins\*.ini|*.json` and the SKSE logs |
| `nif_inspect` | Skyrim-Animation-Studio's crates read NIFs (`df-limb`); else ask the user to open NifSkope |
| writes (`apply`, `create`, ...) | never hand-write plugins; use SPID/KID/SkyPatcher INIs in a new MO2 mod folder |

## SkyrimTools scripts (`D:\Games\SkyrimTools\scripts`)
- `esp\espscan.py`, `esp\pexdis.py` — above.
- `re\*.py` — addrlib, thread_stacks, pdbsym, disasm_at, vtable_slot, calls_in, find_vcall, swf_as2, decomp,
  mcp_call, build_id_names: see `skyrim-reverse-engineering`.
- `misc\merge_ini.py DIST DEPLOYED` — add the keys of a shipped ini missing from the deployed one, every existing value
  and line kept (the user tunes values in game; see `skyrim-modding-practices`).
- `misc\font_has.py FONT [hex codepoints]` — does a TTF/OTF have the glyphs (default: Cyrillic) — for FLICK/SkyUI fonts.

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
- `hkxcheck.py FILE.xml [--summary NAME|#ID] [--list-sm]` — stdlib checker/inspector of behavior XML (serde-hkx `hkxc`
  or `hkxcmd` output).
- `stage_pandora.py` — runs Pandora outside MO2 into `_work/` (never into the real output mod); `pandora_log.py` —
  FAILED/SKIPPED edits of Engine.log by mod; `dump_pandora_out.py` — Pandora output to XML; `validate_rdf.py` — compare two
  staged runs.
- `gen_rdf_patch.py` / `gen_rdf_nemesis.py` — Pandora patch as single source, Nemesis version generated from it.
- `clip_analyze.py`, `annotate_clips.py`, `build_clip_set.py` — clip root-motion analysis, annotation writing, OAR clip
  sets; `gen_menu_translations.py` — FLICK translations (UTF-16LE BOM, CRLF); `build_fomod.py` — FOMOD archive.

## IssenFramework `tools\`
`import_strike_clips.py` (strike sets -> OAR submods), `render_strike_previews.py` (FLICK preview sheets),
`build_df_pack.py` + `df_packs\` (DF packs for creatures without one).

## Projects (D:\Games\Issen)
IssenFramework (own plugin, git), ReactiveDodgeFramework, SkyrimSE_DismemberingFramework, CommonLibSSE-NG (shared by
xmake builds as `../CommonLibSSE-NG`), houseCARL (MCP server source), `re\` (RE workspace), `_scratch\` for throwaway
files, `_downloads\` for archives (untrusted), `_backups\`.
