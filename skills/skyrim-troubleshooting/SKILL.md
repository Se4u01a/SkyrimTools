---
name: skyrim-troubleshooting
description: >-
  Work a Skyrim problem from evidence to a verdict: a crash, a freeze or hang, a Papyrus error storm, an SKSE DLL that
  will not load, save bloat or orphaned scripts, a mod that might be unsafe to update or remove on the current save,
  which plugin wins a record, and which install a log actually came from. Load it when the game misbehaves and a log,
  a dump, a save or a load order has to be read with this repo's tools (scripts\logs, scripts\save, scripts\esp,
  scripts\re, the houseCARL MCP server). Not for engine behaviour in the abstract (skyrim-engine-knowledge), not for
  function signatures (papyrus-reference), not for writing an SKSE plugin (skse-plugin-authoring).
compatibility: >-
  The Python scripts need Python 3 and are stdlib-only. Live record, conflict and asset reads need the houseCARL MCP
  server and a configured Mod Organizer 2 instance; without it the substitutes are named here and the answer is
  narrower. Nexus lookups use scripts\misc\nexus_gql.py (anonymous, no key).
---

# Skyrim troubleshooting

A symptom is not a diagnosis. This skill turns a misbehaving game into a named cause, using the toolkit's own tools, and
says plainly what was read and what is still a guess.

The engine facts behind each symptom live in `skyrim-engine-knowledge`; this skill is the workflow, the tool calls and
the verdict. Crash addresses, REL::IDs, thread snapshots and decompilation are `skyrim-reverse-engineering`.

## Rules that apply before any tool

- **Mirror the logs first.** The game and its plugins overwrite their logs every launch, so triage an earlier launch
  from a copy: `python scripts\logs\mirror_logs.py`. It never deletes or overwrites a mirrored file, and it writes into
  the toolkit folder (`%SKYRIM_TOOLS_HOME%\log-mirror` by default) — never into this repo.
- **Name the folder you read, and its age.** A machine can carry `My Games\Skyrim`, `...\Skyrim Special Edition` and
  `...\Skyrim VR` at once, and the wrong one **reads perfectly** — a complete report about an install you are not
  modding. So can a stale `plugins.txt`. If a tool prints the rivals it ignored, read that line and say which folder the
  answer came from.
- **Newest by modification time, and say which file.** Every log rotates; "the log" means the newest `Papyrus.<n>.log`
  or `skse*.log`, named.
- **Count before you rank.** Every triage tool here reports a denominator and prints rows that sum to it, including a
  row that is zero. If a count looks too tidy, the parser dropped a shape (see the Papyrus entry-versus-line trap).
- **One change at a time.** A verdict of "fixed" needs one variable moved, a checkpoint save, and a before/after
  comparison of the same log lines.
- **Never edit another author's mod folder, and never overwrite a save.** The user's mod manager enables a new mod
  folder; the user loads a repaired save. Say so every time.
- **Only the user tests in game.** Finish with what was read, what was run, and what they must do.

## The tools, by question

| Question | Tool | Reference |
|---|---|---|
| What crashed, is this crash new, has it been ruled on? | `python scripts\logs\crash_triage.py [LOG]` | [references/crash.md](references/crash.md) |
| Why is the game hung, and which thread is guilty? | `python scripts\logs\crash_triage.py` for the dump, then `scripts\re\thread_stacks.py --busy --ids` | [references/freeze.md](references/freeze.md) |
| What did the engine complain about, and how much of it is noise? | `python scripts\logs\papyrus_triage.py [LOG]` | [references/papyrus-errors.md](references/papyrus-errors.md) |
| Which SKSE DLLs loaded, and which were refused? | `python scripts\logs\skse_load_status.py [FILTER]` | [references/skse-dlls.md](references/skse-dlls.md) |
| Keep the logs a relaunch would overwrite | `python scripts\logs\mirror_logs.py` | [references/papyrus-errors.md](references/papyrus-errors.md) |
| What is in this save, is it growing, are scripts orphaned? | `python scripts\save\ess_scan.py info\|plugins\|search\|strings\|forms SAVE` | [references/saves.md](references/saves.md) |
| Which plugin writes co-save data, so which stateful DLL is installed? | `python scripts\save\cosave_info.py COSAVE.skse` | [references/saves.md](references/saves.md) |
| What do two plugin versions actually change? | `python scripts\esp\espdiff.py diff OLD.esp NEW.esp` | [references/mod-change-safety.md](references/mod-change-safety.md) |
| Which plugin wins this record, and what does this asset resolve to? | `housecarl_check`, `housecarl_records`, `housecarl_asset_status` (or `scripts\esp\espscan.py` for raw subrecords) | [references/conflicts-and-paths.md](references/conflicts-and-paths.md) |
| Which instance did the record layer even resolve? | `housecarl_load_order_status` | [references/conflicts-and-paths.md](references/conflicts-and-paths.md) |
| Is this mod's page, changelog or requirement set what it claims? | `python scripts\misc\nexus_gql.py search\|grep\|mod\|desc\|files ...` | [references/mod-change-safety.md](references/mod-change-safety.md) |
| An address in a crash log, a hung thread, a decompile | `scripts\re\*` — see `skyrim-reverse-engineering` | [references/crash.md](references/crash.md), [references/freeze.md](references/freeze.md) |
| Is it safe to publish this release? | read-only review | [references/release-review.md](references/release-review.md) |

The new triage scripts in `scripts\logs`, `scripts\save` and `scripts\esp\espdiff.py` are part of the toolkit; run any of
them with `-h` for its exact arguments before depending on a shape you remember from a document.


## Route by symptom

| Symptom | Start with | Why |
|---|---|---|
| Crash to desktop, a crash log exists | [references/crash.md](references/crash.md) | the dump names a module and offset before it names a cause |
| Crash on load, or on entering one cell | [references/crash.md](references/crash.md), then [references/conflicts-and-paths.md](references/conflicts-and-paths.md) | a removed plugin, a light-plugin slot, or a cell-specific asset |
| Freeze, hang, endless loading screen, "not responding" | [references/freeze.md](references/freeze.md) | a hung main thread and a paused game look identical from outside |
| Papyrus log filling with errors | [references/papyrus-errors.md](references/papyrus-errors.md) | most of it is four known-benign shapes; the rest is version skew |
| A mod's feature does nothing | [references/skse-dlls.md](references/skse-dlls.md), then [references/papyrus-errors.md](references/papyrus-errors.md) | a refused DLL and an unbound native both look like "no error" |
| CTD that only one mod could cause | [references/crash.md](references/crash.md), then [references/conflicts-and-paths.md](references/conflicts-and-paths.md) | confirm the mod is the one loaded, not a namesake |
| Save grew, save is slow, save will not load | [references/saves.md](references/saves.md) | footprint and orphans are measurable; guesses are not |
| "Can I update / remove this mod mid-playthrough?" | [references/mod-change-safety.md](references/mod-change-safety.md) | the rubric prices the change; the disk says what is installed |
| "Why is this record not the one I edited?" | [references/conflicts-and-paths.md](references/conflicts-and-paths.md) | winner, VFS and the wrong-install trap |
| "I changed a script and the game still runs the old one" | [references/papyrus-errors.md](references/papyrus-errors.md) | a `.pex` is read at startup |
| "Before I publish this" | [references/release-review.md](references/release-review.md) | a review gate with an author in the loop |

## First response, in order

1. **Say what is on screen and what the user did**, in one line, and ask for the log the game wrote if you do not
   have it. Do not open with a theory.
2. **Mirror the logs** (`scripts\logs\mirror_logs.py`) so the next launch cannot destroy the evidence.
3. **Read the newest log of the right kind**, with the right tool above, and quote the lines that matter.
4. **Establish the install and the load order** before drawing conclusions: which game folder, which profile, which
   plugin actually wins. `housecarl_load_order_status` or the file itself, named.
5. **Only then** a cause, and mark it: what is proven by a log line, what is inferred, and the cheapest check that would
   settle it.

## What to hand back

- The files read, with their folders and how old they are.
- The counts: how many dumps, entries, DLLs, plugins — and against what denominator.
- Which findings are benign and why (a count is not a finding).
- One recommended next action, and what would falsify it.
- If a step needed the record API and only `espscan.py` was available, say the result is raw subrecords, not a resolved
  record.
- If a change is proposed, "built, NOT tested in game", plus what the user must do.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
