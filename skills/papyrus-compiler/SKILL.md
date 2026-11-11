---
name: papyrus-compiler
description: >-
  Compiles Papyrus .psc to .pex on this machine with scripts/papyrus/papyrusc.py: picks a compiler (the open-source
  russo-2025 papyrus-compiler that setup.cmd installs, or the Creation Kit's PapyrusCompiler.exe), builds the import
  path from the live MO2 load order in priority order, fills the missing vanilla sources with headers generated from
  the game's own .pex, writes the .pex into a NEW mod folder and reads the diagnostics. Use whenever a .psc must be
  compiled or checked, a compile error must be explained ("unknown type", "is not a function"), or a script edit must
  be turned into a .pex. Not for API signatures (that is papyrus-reference), not for .pex disassembly (pexdis.py),
  and never a claim that the script works in game.
compatibility: >-
  Windows. A compiler from setup.cmd (papyrus-compiler) or the Creation Kit; SKYRIM_MO2_DIR and SKYRIM_GAME_DIR for
  the imports and the vanilla headers. houseCARL is optional (housecarl_compile_script is the MCP lane for the CK).
---

# Papyrus compiler

`%SKYRIM_TOOLS_REPO%\scripts\papyrus\papyrusc.py` (stdlib Python) drives a Papyrus compiler with the imports the
user's MO2 load order actually provides. Before writing any call into the script, check its signature with
`papyrus-reference` — the compiler only tells you after the fact.

## Which lane

| Situation | Use |
|---|---|
| compile or syntax-check a `.psc` from a shell, any agent | `python scripts\papyrus\papyrusc.py compile ... -o <new mod>\Scripts` |
| houseCARL is loaded and the CK compiler is configured in it | `housecarl_compile_script` (same MO2 import discovery, lands the `.pex` in a houseCARL patch mod) |
| houseCARL is loaded but says the compiler is missing | `housecarl_set_tool_path` `papyrus_compiler` = `%SKYRIM_TOOLS_HOME%\papyrus-compiler\papyrus-compiler\Original Compiler\PapyrusCompiler.exe` (the CK compiler shipped in the papyrus-compiler archive) — it still needs the vanilla `.psc`, see below |
| only want to know what the imports are | `python scripts\papyrus\papyrusc.py imports` |
| which compilers exist here | `python scripts\papyrus\papyrusc.py which` (exit 3 = none: `setup.cmd` installs one) |

## Commands

```
python scripts\papyrus\papyrusc.py compile <file.psc|folder>... -o <out dir> [-i <dir>]... [--compiler auto|open|ck]
                                    [--profile NAME] [--no-mo2] [--no-vanilla-headers] [--check] [--into-existing-mod]
python scripts\papyrus\papyrusc.py imports [--profile NAME] [-i <dir>]...
python scripts\papyrus\papyrusc.py headers [--rebuild]
python scripts\papyrus\papyrusc.py which
```

- `--check` compiles to a temp folder: syntax and types only, no output. Use it for "does this compile?".
- `--compiler auto` takes the open compiler when installed, else the CK one. Pass `--compiler ck` to reproduce what
  the Creation Kit would say (it is stricter about some things, see differences below).
- Exit codes: 0 every input compiled, 1 some failed (diagnostics printed), 2 usage / refused output, 3 no compiler.
- Success is decided by a `.pex` this run wrote with the Papyrus magic `FA57C0DE`, not by the compiler's exit code
  (the CK returns 0 on usage errors) and not by "no output" (a warning is not a failure).

## The import path (why a script resolves or not)

Order, highest precedence first; a script name resolves to its FIRST provider, exactly like the MO2 VFS:

1. the folders of the inputs, 2. every `-i`, 3. MO2 `overwrite\`, 4. the enabled mods of the profile from the top of
   `modlist.txt` (top line = highest priority; disabled mods and separators are skipped), 5. the game's `Data`,
6. the generated vanilla headers, LAST (both compilers accept them; `--no-vanilla-headers` drops them).

A folder counts when it is `<root>\Source\Scripts` (SE/CK layout) or `<root>\Scripts\Source` (LE layout) and holds a
`.psc`. The profile is `selected_profile` of `ModOrganizer.ini` unless `--profile`. For the open compiler the winners
are staged into one temp folder (`-h`), so precedence is decided by the script, not by the compiler; inputs are kept
out of the headers.

`papyrusc.py imports` prints the list with the number of `.psc` per folder. Read it before blaming the code.

## Vanilla sources and the generated headers

The vanilla `.psc` (`Debug`, `ReferenceAlias`, `GlobalVariable`, `Message`, `Door`, ...) ship only in the Creation
Kit's `Scripts.zip`; most load orders have SKSE's 62 base classes and USSEP's patched scripts, not the rest.
`papyrusc.py headers` (run automatically by `compile`) generates declaration-only headers from the game's own `.pex` in
`Skyrim - Misc.bsa` (+ `Update.bsa` and the DLC BSAs when present): hierarchy (`extends`), properties, events and
function signatures, with parameter defaults taken from the `papyrus-reference` corpus (`.pex` has no defaults).
Cached in `%SKYRIM_TOOLS_HOME%\papyrus-headers\<hash>` and rebuilt when the BSAs or the corpus change.

Limits, say them when they matter:
- a default the corpus does not carry is missing, so a call that omits that argument fails: write it out;
- every function is declared `native` and bodyless — the headers are for the compiler only, never ship or compile
  them, and never put them in a mod;
- real sources always win: when the user has the Creation Kit's `Scripts.zip` extracted (game `Data\Source\Scripts`
  or a mod with `Source\Scripts`), those are used and the headers only fill what is still missing.

Verified on the author's machine (no Creation Kit, STB load order): a script calling `Debug.Notification` (vanilla,
header), `Game.GetModCount` (SKSE) and `EquipItem` with omitted defaults compiles with both compilers to the same
bytecode (`pexdis`), and fails with "undefined identifier Debug" when `--no-vanilla-headers` is passed. Whole mod
folders on the same load order: MCM Helper, Wheeler, RaceMenu and STB Skip dialogues build clean with the open
compiler; every failure seen was in the sources the load order provides, not in the lane — a modpack's decompiled
`SKI_ConfigBase.psc` without defaults (Open Cities, QuickLoot IE, Better Fast Travel), a quest fragment calling a
function its own mod no longer has (Alternate Start), and, with `--compiler ck` only, USSEP's `CWSiegeScript`
calling a vanilla non-native function whose defaults no header carries.

## Output rules

- The `.pex` goes into `<NEW mod folder>\Scripts`. `papyrusc.py` refuses a folder of an installed mod (one with
  `meta.ini`) and the game's `Data` unless `--into-existing-mod` — pass it only for the user's own mod, never for
  another author's (skill `skyrim-modding-practices`).
- A new mod does nothing until the user enables it in MO2. A recompiled script that replaces another mod's `.pex`
  must have HIGHER priority than that mod (lower in MO2's left pane; a new mod lands last, which is highest). Name the
  mod it overrides.
- Keep the `.psc` next to it as `<mod>\Source\Scripts\<Name>.psc` so the next compile and the next agent find it.
- Report "compiled, NOT tested in game". The game reads scripts on load: a changed script on an existing save keeps
  the old properties and running states, so the user may need a new game or a clean reload to see the change.

## Reading the errors

| Message (open / CK wording) | Usually means | Do |
|---|---|---|
| `unknown type X`, `X is not a known user-defined script type` | the script that defines `X` is not in the imports | `imports`; enable the mod that ships `X.psc` (SKSE, SkyUI SDK, PapyrusUtil, MCM Helper...) or `-i` its folder |
| `X is not a function or does not exist`, `unknown function` | wrong name, or a newer API than the installed `.psc` | check `papyrus-reference`; compare with the `.psc` that `imports` resolved |
| `type mismatch`, `cannot cast` | argument or return type | `papyrus-reference` signature; Papyrus casts with `as` |
| `function takes 3 parameters not 1` (open), `too few arguments` (CK) | the winning `.psc` declares no default for a parameter the call omits: a generated header without that default, or a DECOMPILED `.psc` shipped by a modpack (decompilers drop defaults; lowercase `function`, no comments) | `imports` shows which mod's `.psc` wins; put the original source (e.g. the SkyUI SDK's `SKI_ConfigBase.psc`) in with `-i`, or write the arguments out |
| `script X extends Y ... Y not found` | parent script missing from the imports | as for unknown type |

`papyrusc.py` prints a hint when two thirds of the errors are unknown names: usually a missing import, unless the
name is a typo. The open compiler writes NO `.pex` at all when any input of the run has an error: compile a folder,
fix the reported files (or compile the others by name), then compile again. The CK compiler is run once per file, so
the good ones still get their `.pex`.

## Differences between the two compilers

From the papyrus-compiler README (russo-2025, MIT): a line break inside a string literal is accepted by the open
compiler and rejected by the CK; the CK can change the case of string literals to a name it has seen before, the open
compiler keeps the source case. Anything that compares strings case-sensitively may behave differently. For a release
build of someone else's mod, prefer the compiler its author used; when unsure, compile with both (`--compiler ck`
too) and report any disagreement.

## Verifying the output

`python scripts\esp\pexdis.py <out>\<Name>.pex` disassembles what was built (script name, parent, properties,
functions): check that the properties the plugin fills are there with the right types. That is all that can be
checked outside the game.

Related: `papyrus-reference` (signatures), `skyrim-local-toolbox` (MO2 instance, where tools are),
`skyrim-modding-practices` (new mod folder, honest reporting).
