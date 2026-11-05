# Contributing to SkyrimTools

This repo is knowledge plus small tools, so "it works" means "an agent that has never seen this machine can follow it".
That is the bar for a change. The agent-facing guide is [AGENTS.md](AGENTS.md); human docs are [README.md](README.md),
[FEATURES.md](FEATURES.md) and [INSTALL.md](INSTALL.md) (the latter two in Russian).

## House rules

- **No absolute paths, no usernames, no machine-specific values** in anything that ships. Paths come from
  `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`, `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR`, or from an argument.
  The `D:\...` paths in `skyrim-local-toolbox` / `skyrim-modding-practices` are explicitly labelled as the author's
  machine — keep that label if you touch them.
- **No binaries, no game assets, no third-party mod files.** Scripts and Markdown only; `data/se_id_names.tsv` is text.
- **EOLs and BOM:** the repo stores LF and `core.autocrlf=true` checks it out as CRLF on this machine; `.cmd` and `.ps1`
  are CRLF either way (`.gitattributes`), so keep a file's existing EOL instead of normalising it. `setup.ps1` is UTF-8
  **with BOM**: Windows PowerShell 5.1 reads a BOM-less script as ANSI, so its Russian strings turn into mojibake or a
  parse error. Convert a file with `[IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding $true))`, and keep the
  encoding of files that already have one (FLICK translations: UTF-16LE with BOM).
- **Python:** standard library only, unless the script's docstring says it needs the RE venv (`capstone`, `pefile`,
  `mcp` — pinned in `requirements-re.txt`). Print UTF-8, take paths as arguments, start the file with a docstring that
  shows real usage lines.
- **PowerShell:** plain cmdlets and `[Environment]`/`[System.IO]` calls, no modules to install, `-NoProfile` friendly.
  A script that other agents run must print something useful and exit non-zero on failure.
- **Markdown:** one fact per line, real paths and real command examples, no marketing. Tables for enumerations, prose for
  reasoning. Agents read the whole file — length is fine if every line carries a fact.

## Adding a skill

1. `skills/<name>/SKILL.md`, frontmatter `name` **identical to the folder name** (`scripts\agents\doctor.ps1` checks
   this), a `description` that says when to load it and what it is *not* for, and `compatibility` when it needs the
   houseCARL server or a toolchain.
2. Body: what the skill answers, the routing table to `references/`, the traps, and what to do when the corpus does not
   carry an answer. End with explicit "read this reference for that job" pointers.
3. Put the long material in `references/`, one topic per file. If it is a lookup, ship `index.jsonl` with `name`,
   `file`, `line_start`, `line_end` per line and say to grep the exact quoted token.
4. Add a row to `skills/README.md` and to the skills table in `AGENTS.md` (and to `llms.txt` if it is a top-level skill).
5. Never ship a skill that invents an API, a record field or a framework token: warn and point at the check instead.

## Adding a script

1. Put it in the right folder: `scripts/esp/` (plugin/pex readers), `scripts/misc/` (INI, fonts, Nexus), `scripts/re/`
   (Address Library, memory, disassembly, Ghidra). Anything about installing or wiring the toolkit goes to
   `scripts/agents/`.
2. Docstring with runnable usage lines, same as the neighbours; ASCII only.
3. Add a row to the scripts table in `AGENTS.md`, to the appropriate section of `README.md`, and to the skills that
   mention the tools (`skyrim-local-toolbox`, and `skyrim-reverse-engineering` for `scripts/re/`).
4. Run it once against real input and paste the real output in the pull request. "Should work" is not a test.

## Changing the installer

`setup.ps1` is idempotent and destructive only when asked: keep it that way. A new step needs (a) a line in the plan it
prints before asking, (b) a guard that skips it when already done, (c) a line in INSTALL.md and in the tables of
`README.md`/`AGENTS.md`, (d) an entry in `-Uninstall` if it writes outside the repo. Keep the SHA-256 pins in `$Pins`
current, and bump `requirements-re.txt` only with a matching change to the `set_pdb` patch of `ghidrecomp`.

## Commits

One finished change per commit, in the imperative mood, with what was verified and what was not. Do not commit
`__pycache__` (already ignored), and never commit deployed MO2 files. Experiments the user rejected belong on a
`wip/<topic>` branch rather than in the trash.
