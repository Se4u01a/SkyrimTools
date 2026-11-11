# Skills

Twelve Agent Skills live here, one folder each: `skills/<name>/SKILL.md` plus a `references/` tree the skill points
into. This file is the index — an agent without skill auto-discovery can read the table, then the skill.

## Rules of use

- **Read the whole `SKILL.md`.** The frontmatter (`name`, `description`, `compatibility`) is for routing; the body is the
  knowledge, and it ends by naming the reference files to open for specific jobs.
- **Read the reference the skill names**, not all of them: they are long on purpose (`papyrus-reference` alone is ~2 MB).
- **`index.jsonl` is a lookup, not reading.** `papyrus-reference`, `mutagen-reference` and `spid-authoring` ship an index
  whose lines carry `file` and 1-indexed `line_start`/`line_end`. Grep for the exact quoted token — `"name":"GetActorLevel"`,
  `"sig":"ARMO"` — and open that shard at that line.
- **Missing thing ≠ invented thing.** Each reference skill says what to do when the corpus does not carry an entry: warn,
  offer the check, never fabricate a signature or a field.
- **Naming.** In Claude Code plugin installs a skill is `housecarl:<name>`; every other host and every raw checkout uses
  the bare folder name. MCP tool names are always bare `housecarl_<tool>`.

## Index

| Skill | Answers | Needs houseCARL | Reference highlights |
|---|---|---|---|
| [`skyrim-modding-practices`](skyrim-modding-practices/SKILL.md) | how to work in this environment: file editing, MO2 deploys, INI merges, Pandora, git, honest reporting | no | — (self-contained, ~60 lines, read first) |
| [`skyrim-local-toolbox`](skyrim-local-toolbox/SKILL.md) | which tool or path does a Skyrim job here, and what to use when `housecarl_*` tools are not loaded | no | substitutes table, RE/ESP/misc scripts |
| [`spid-authoring`](spid-authoring/SKILL.md) | SPID 7.3 `_DISTR.ini`: distributing spells, perks, items, keywords, outfits, factions to NPCs by filter | yes (validation) | `grammar-core.md`, `filters.md`, `form-types.md`, `value-tables.md` |
| [`kid-authoring`](kid-authoring/SKILL.md) | KID 3.5 `_KID.ini`: keywords onto item records by name/archetype/slot/stat filters | yes | `grammar-core.md`, `traits.md`, `filters.md`, `types.md` |
| [`skypatcher-authoring`](skypatcher-authoring/SKILL.md) | SkyPatcher 6.4.1: setting/adding/removing record fields, containers, leveled lists without an ESP | yes | `grammar-core.md`, `placement-and-conflicts.md`, per-record-type pages |
| [`open-animation-replacer`](open-animation-replacer/SKILL.md) | OAR 3.x `config.json`/`user.json`: conditions, submod priority, DAR conversion, why an animation is not playing | yes | `oar-config-reference.md` |
| [`papyrus-reference`](papyrus-reference/SKILL.md) | Papyrus/SKSE/plugin-API function, event and property signatures (offline) | for live script reads | `index.jsonl` → `skse/*.md`, `vanilla/*.md`, plugin pages (po3, PapyrusUtil, JContainers, MCMHelper, SkyUI…) |
| [`mutagen-reference`](mutagen-reference/SKILL.md) | record schema: fields, types, cardinality, writability, enum values, polymorphic arms (offline) | for record reads/writes | `index.jsonl` → `records.jsonl`, `structs.jsonl`, `arms.jsonl`, `enums.jsonl` |
| [`skse-plugin-authoring`](skse-plugin-authoring/SKILL.md) | writing/building/auditing a native SKSE DLL against CommonLibSSE-NG, SE+AE+VR, load failures | yes | `plugin-skeleton.md`, `hooking.md`, `event-sinks.md`, `multi-runtime.md`, `load-failures.md`, `toolchain-setup.md` |
| [`skyrim-reverse-engineering`](skyrim-reverse-engineering/SKILL.md) | crash logs, `SkyrimSE.exe+XXXX`, REL::IDs, thread snapshots, `.pdb` names, disassembly, Ghidra decompilation | no (Ghidra/RE workspace instead) | the `scripts/re/*.py` usage and Ghidra workflow |
| [`papyrus-compiler`](papyrus-compiler/SKILL.md) | compiling `.psc` to `.pex` here: which compiler, the MO2 import order, generated vanilla headers, what an error means | no (`housecarl_compile_script` is the MCP alternative) | `scripts/papyrus/papyrusc.py` |
| [`nexus-api-search`](nexus-api-search/SKILL.md) | Nexus Mods search, descriptions, requirements, files, update checks — anonymous GraphQL, no API key | no | `scripts/misc/nexus_gql.py` |

## Using these skills from another agent

Skills are plain folders, so an agent either reads them from this repo or gets a link in its own skills directory:

```powershell
# one junction per skill in ~\.codex\skills (default target for -Client codex)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client codex -LinkSkills
# Claude Code's user-level skills directory
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client claude -LinkSkills
# DeepSeek Harness: the same root its desktop app, CLI and ACP profile in Zed read
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client dsh -LinkSkills
# anywhere else
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client codex -LinkSkills -SkillsTarget D:\tools\my-agent\skills
```

Junctions mean an edit here is live in the other agent; `-Force` replaces an existing link, and a real directory is
never overwritten. If the target agent does not read skill folders at all, point its instruction file at this directory
and at [`AGENTS.md`](../AGENTS.md).

### DeepSeek Harness specifics

DSH's `dsh-skill-filesystem` provider scans, in rank order: `<projectRoot>/.dsh/skills`, `<projectRoot>/.agents/skills`,
`customSkillDirs`, `%USERPROFILE%\.dsh\skills`, `%USERPROFILE%\.agents\skills`. Its rules differ from Claude Code in
four ways worth knowing:

- discovery is **one level deep** — `<root>/<name>/SKILL.md` or `<root>/<name>.md`; a nested `**/SKILL.md` is ignored;
- `SKILL.md` frontmatter needs `name` (kebab-case, same as the folder) and `description`, the same two fields these
  skills already carry; `compatibility`, `license` and other extra keys are tolerated;
- optional `whenToUse`, `disable-model-invocation` and `user-invocable` control whether the skill reaches the model
  catalog and the human command surface; a malformed boolean drops the whole skill with a warning;
- the provider watches the roots, so a new junction appears in the session catalog without restarting DSH.

DSH also reads workspace instructions: user-global `%USERPROFILE%\.dsh\AGENTS.md` (then `%USERPROFILE%\.agents\AGENTS.md`),
then the `AGENTS.md`/`CLAUDE.md` chain from the project root down to the working directory. `%USERPROFILE%\.dsh\skills`
is therefore the exact analogue of `%USERPROFILE%\.claude\skills`.
