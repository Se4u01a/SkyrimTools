# Changelog

Versions follow `.claude-plugin/plugin.json`; each has a git tag `vX.Y.Z`. Upgrade: `git pull`, run `setup.cmd`
again, then in Claude Code `/plugin marketplace update skyrim-tools` and restart the session.

## 1.4.0 — 2026-11-11

### New
- **Papyrus compiler.** `scripts\papyrus\papyrusc.py compile|imports|headers|which` and the skill `papyrus-compiler`:
  `.psc` -> `.pex` with the open-source [papyrus-compiler](https://github.com/russo-2025/papyrus-compiler) (MIT) or the
  Creation Kit's `PapyrusCompiler.exe`. The import path is the live MO2 load order in priority order (first provider
  wins, like the VFS). The vanilla `.psc` that ship only with the Creation Kit are replaced by declaration headers
  generated from the game's own `.pex` in `Skyrim - Misc.bsa`, with parameter defaults from the `papyrus-reference`
  corpus. Output into an installed mod or the game's `Data` is refused.
- `setup.cmd` step 2b installs papyrus-compiler 2026.03.15 (SHA-256 pinned) into
  `%SKYRIM_TOOLS_HOME%\papyrus-compiler`; `-NoPapyrus` skips it. `doctor.ps1` reports the compiler.
- **Self-test and CI.** `python scripts\agents\selftest.py`: every script compiles and prints usage instead of a
  traceback (checked as on a clean English Windows), synthetic fixtures (plugin with a compressed record, INI, SWF,
  thread snapshot, a fake MO2 + BSA + stub compiler for papyrusc), PowerShell parse, EOL/BOM rules, manifests, skill
  frontmatter, every `index.jsonl` target, Markdown links. `--live` checks the real data and MCP launchers of this
  machine, `--ghidra` the pyghidra-mcp launcher, `--net` Nexus. GitHub Actions runs the static part on every push and
  turns a failed check into an annotation.

### Fixed
- `font_has.py --help` crashed on a cp1252 console (Cyrillic in the docstring).
- `addrlib.py --help` failed when the Address Library `.bin` was not installed.

## 1.3.0 — 2026-11-11

### New
- The heavy parts (`re\`, `houseCARL\`, `houseCARL-data\`, `tools\`) may sit in the gitignored repo root; the
  launchers and `doctor.ps1` fall back to them when the variables point at a folder that no longer exists.
- `run_ghidra_mcp.cmd` passes the Skyrim RE Toolkit GDT as `--gdt` when present; `scripts\run_sage_havok.cmd`
  launches SageHavokEditor. AGENTS.md 5.1 lists these optional, hand-installed tools.

### Fixed
- `pdbsym.py` resolved no names (wrong `SYMBOL_INFOW.SizeOfStruct`, deferred symbol loads).
- `thread_stacks.py` crashed on non-English Windows (tasklist prints in the OEM code page).
- `build_id_names.py` with a wrong argument overwrote `data/se_id_names.tsv` with an empty table.
- The Ghidra fallback path contained `..`, which Ghidra rejects as a project path.
- Every CLI script prints usage on `-h`/`--help` or missing arguments instead of a traceback.

## 1.2.0 and earlier

No changelog; see `git log`.
