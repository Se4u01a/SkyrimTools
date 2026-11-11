# Crash triage

A crash dump names **where** the game died, not **why**. This file is how to read a folder of them without chasing the
same crash four times, and which crash shapes the engine knowledge already explains.

## Where the dumps are, and the `.LOG` trap

- A crash logger writes into the game's `SKSE` folder (`Documents\My Games\<game>\SKSE\`), sometimes in its own
  subfolder such as `SKSE\Crashlogs`. It usually opens the newest dump in Notepad.
- **The extension changed.** Recent versions write **`.LOG`**; older ones wrote `.txt`, and both can sit in the same
  folder.
- **The dangerous case is not finding nothing — it is finding some.** A `crash-*.txt` search does not fail on a folder
  of `.LOG` files; it returns a confident, complete-looking total from whichever half it matched. MEASURED on one
  install: **8 `.txt` (all from June 2025) beside 20 `.log` (2026)**, and the first version of the triage tool reported
  "8 log(s)" — a year out of date, with an accounting check that balanced perfectly, because a denominator can only
  account for what it was given.
- Match `crash-*` **case-insensitively** on both extensions, and keep the `crash-` prefix: the logger's own
  `CrashLogger.log`/`CrashLoggerSSE.log` is not a crash.
- A logger version that added `__fastfail` dumps (a crash class older loggers never wrote) means the parser may meet a
  shape it does not know. MEASURED: the triage tool's **unparsed counter** is the check — it should stay 0 when a real
  `__fastfail` dump is added. If it is not 0, add the shape to the parser rather than ignoring the dump.

`python scripts\logs\crash_triage.py` walks every dump in the folder; `python scripts\logs\crash_triage.py [dir-or-file]`
reads one dump or one folder. `--frames N` sets how many frames print under an unknown signature (default 4), `--all`
prints every signature instead of the top 15, and `--known FILE` supplies the rulings ledger.



It reads `crash-*.txt`, `crash-*.log` and a `Crashlogs/*.log` subfolder (a logger that writes timestamp-named dumps into
`Crashlogs`); a file that looks like a dump but matches no shape is reported as a near miss rather than dropped. Exit 0
is "triaged", 1 is "see RESULT" (accounting, a degraded parser, an incomplete input set), 2 is bad usage or no dumps.

## How to read one dump

- A dump is ~5,500 lines, ~4,600 of which are the raw `STACK` block. **The identifying part is the exception line plus
  the top of `PROBABLE CALL STACK`.**
- Group dumps by **module + offset** of the top frames, so ten crashes of one bug are one finding. Key the ruling by
  **module AND offset** (module in lower case, offset in upper case) — an offset is only meaningful inside its module.
- Keep a **rulings ledger**, and feed it to the tool with `--known FILE`: one `MODULE+OFFSET STATUS note` per line,
  `#` or `;` starting a comment, STATUS `ACCEPTED` or `KNOWN`, and the note printed under that signature. **Without a
  ledger file every signature prints as unknown**, so a crash settled last week is investigated again — the file is
  yours to create and to keep, and it is the whole difference between a triage history and a triage snapshot.
- Rows must sum to the dumps parsed, and a mismatch must be loud. A triage report that silently drops a dump is worse
  than no report: it invents a history in which the bug never happened.
- The newest dump is the one to read first, and the folder's modification times should be quoted: after a CTD, sort by
  modified time, not by name.

## What the exception line tells you

| Shape | Likely class | Next step |
|---|---|---|
| `EXCEPTION_ACCESS_VIOLATION` in a script-memory page policy frame (`SkyrimScript::HandlePolicy::Func4`, through `BSScript`/`NativeFunctionBase::Call`, often with a script-tweak plugin) | VM page-policy fault | [freeze.md](freeze.md) memory section — do **not** shrink page sizes |
| `EXCEPTION_ACCESS_VIOLATION` in the physics path (`hkpConstraintInstance`, `hkpRigidBody`, `hkpSimulationIsland`) while a creature touches world geometry, independent of combat | orphaned extended creature skeleton | restore the vanilla `skeleton.nif` — see [nif-and-audio.md](../../skyrim-engine-knowledge/references/nif-and-audio.md) |
| CTD when a physics op hits a freshly spawned actor | null physics body | guard behind an `Is3DLoaded()` wait — see [papyrus-runtime.md](../../skyrim-engine-knowledge/references/papyrus-runtime.md) |
| CTD on placing a mesh that reads back fine in its authoring tool | malformed controller or header strings | the validation gates in [nif-and-audio.md](../../skyrim-engine-knowledge/references/nif-and-audio.md) |
| Crash at save load after a plugin change | removed plugin, light-plugin slot move, compacted FormIDs | [saves.md](saves.md), then the save-safety rubric in `skyrim-engine-knowledge` |
| Crash on a script's first tick after an install | unbound native (DLL/`.pex` mismatch) | [skse-dlls.md](skse-dlls.md) |

These are shapes to recognise, not proof. The stack is the evidence; the class is the hypothesis.

## Workflow

1. **Mirror the dumps** (`scripts\logs\mirror_logs.py`) before the next launch overwrites them.
2. **Run the folder through the triage tool** and read the grouping, not just the newest dump.
3. **If the signature is in the rulings ledger**, stop: report it as already settled and why.
4. **Read the exception line and the top of `PROBABLE CALL STACK`.** Anything past the first few frames is usually
   runtime scaffolding.
5. **Map the addresses.** `SkyrimSE.exe+X` is an RVA; `addrlib.py off <X> SkyrimSE.exe+<X>` gives the REL::ID and the
   name when one exists, and `pdbsym.py` names a DLL's frames from its `.pdb`. Full procedure:
   `skyrim-reverse-engineering`.
6. **Ask what changed** since the last good run: a new plugin, a rebuilt `.pex`, a DLL update, a mesh, a light-plugin
   flag. One change at a time, and a checkpoint save between changes.
7. **Confirm the mod you suspect is the mod that loaded** — a namesake plugin, a stale copy in `Data/`, or an old-named
   DLL sibling will produce the crash and look innocent. See [conflicts-and-paths.md](conflicts-and-paths.md).
8. **Record the ruling** in the ledger with the module, offset and one line of cause.

## What a crash log cannot answer

- **Why the game hung**: a hang usually leaves no dump. Use [freeze.md](freeze.md) and thread snapshots.
- **Which mod is at fault** when the top frame is the engine: the engine frame is where it died, not what misused it.
  The stack above it, and the load order, are the evidence.
- **Whether a mod is safe on your save**: that is a different question entirely — `skyrim-engine-knowledge`'s
  save-safety reference.

## Reporting a crash

State the dump file and folder, the exception line, the grouped signature, whether it is new or already ruled on, and
the addresses you mapped (with the ID/name each one produced). If the addresses were not mapped, say the frames are
unresolved rather than naming a mod from the module name alone.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
