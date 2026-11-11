# Papyrus log triage

Most of a Papyrus log is not a bug. The work is to separate the four known-benign shapes and the one or two real
version-skew findings from a wall of repeats, and to say how many of each there are.

## Read the right file, and keep it

- The log is `Documents\My Games\<game>\Logs\Script\Papyrus.<n>.log` (on VR: `...\Skyrim VR\Logs\Script\`). `.0` is the
  current session; the numbered files are older sessions.
- The game rotates it every launch, so triage an earlier launch from a copy: `python scripts\logs\mirror_logs.py`.
- A mod's **own** log in the `SKSE` folder is often more specific than the Papyrus log (it prints settings, versions and
  its own errors). When a script behaves as if a setting were unchanged, that file is the one that shows it.
- Name the file you read and how old it is. More than one game install means more than one `Logs\Script` folder, and the
  wrong one reads perfectly (see [conflicts-and-paths.md](conflicts-and-paths.md)).

## Count entries, not lines

`python scripts\logs\papyrus_triage.py` reads the newest log; `... [logfile]` reads a named one. `--top N` sets how many
shapes print per severity (default 15), `--all` prints every shape. Exit 1 means an accounting check failed — read the
RESULT line and fix the reading, not the total. `SKYRIM_DOCUMENTS_DIR` or `PAPYRUS_LOG_DIR` overrides the folder it
discovers.


- **The unit of accounting is the ENTRY, not the line.** A Papyrus entry is multi-line: MEASURED on one install,
  `Papyrus.1.log` had **8,426 lines but only 5,292 timestamped entries**, the rest being `stack:` continuations. A
  line-based sum is ~37 % wrong.
- **Severity is spelled two ways in the same file.** MEASURED: `warning:` 99 times and `WARNING:` 662 times; a
  case-sensitive grep silently loses 87 % of them.
- Rows must sum to the input, and the "not shown" row must print even when it is zero. A triage tool that drops a shape
  reports a smaller, more comfortable world.

## The known-benign shapes

| Line | What it is | Do |
|---|---|---|
| `VM is freezing...` / `VM is frozen` | printed on every normal exit and save | ignore completely |
| `Cannot open store for class "X", missing file?` | an orphaned script instance baked into a save, from a removed or lobotomized mod | harmless; suppress with `bDisableMissingScriptError = true`, and clean the orphans if it is many |
| `Unable to call X - no native object bound` | a phantom ActiveMagicEffect instance whose `Self` has no native binding | no in-script guard works (a `== None` test returns garbage, not None); fix the broadcast source, detach the script at record level, or filter natively |
| `... does not have a property named ...` / missing-property warnings | version skew between a script in the save and the script on disk | cosmetic after the next save; the value is discarded |

- A removed mod also leaves its `RegisterForUpdate` handlers registered, so periodic errors continue; that is orphan
  noise plus a reason not to remove plugins from a live save (`skyrim-engine-knowledge`, save-safety).
- Orphan instances can be removed by a save-cleaning tool; that is the only way to make the lines stop for good.

## The findings that are worth the time

| Line | Meaning | Next step |
|---|---|---|
| `Replacing native function ...` | **two SKSE plugins register the same script's natives**, so a stale duplicate DLL is installed and may be overriding the newer one's functions | find the old-named sibling or the leftover port and retire it — [skse-dlls.md](skse-dlls.md) |
| `... does not match existing signature` | the `.psc` compiled against one DLL version is calling an older/newer one; the native goes unbound | the DLL and its `.pex` declarations move together; identify which build is installed ([skse-dlls.md](skse-dlls.md)) |
| an unbound native for a function the mod relies on | the DLL is missing, refused by SKSE, or too old | [skse-dlls.md](skse-dlls.md) |
| `... not found` for a plugin/form | a missing master or a record that a soft dependency used to provide | [conflicts-and-paths.md](conflicts-and-paths.md) |
| thousands of one-line errors per second | an error storm, which can degrade the VM into a freeze | find the script and the failing call (`skyrim-engine-knowledge`, papyrus-runtime: NaN and `IsBlocking` are the two classics) |
| a script stack dump | 5 s of continuous overload somewhere | [freeze.md](freeze.md) |

**`Cannot open store for class "X"` is not proof that mod X is running or installed.** It is proof that a *save* still
holds an instance of it. The distinction decides whether you are looking at an install problem or a save problem.

## "I changed the script and the game runs the old one"

- **A `.pex` is read when the game launches.** A mid-session save/load never re-reads it from disk — not even loading a
  save that has never seen the mod. Skyrim bakes the script instance into the save and restores that instance on load.
- The only reliable refresh: quit to desktop, relaunch, and load a **pre-activation** save (one made before the effect
  was ever active). A post-activation save restores its baked instance even after a full restart.
- **Verify which build is live rather than assuming:** plant a distinctive log line in each build and look for it in the
  on-disk log. Separately, grep a newly added string into the `.pex` on disk — that distinguishes "it did not compile"
  from "it did not load". `scripts\esp\pexdis.py` disassembles a `.pex` without a full decompiler.
- **Design implication — this is the real fix.** Make anything you intend to iterate a runtime parameter (a
  GlobalVariable the script reads each run) instead of a constant. Then tuning never changes the code: one load to get
  the parameter-driven build in, and zero reloads for the whole sweep, flipping values live. Put the *mechanism* behind
  a parameter too, so an approach can be swapped without recompiling.

## Reducing the noise (config, not code)

Keys worth knowing in a script-tweak plugin's INI (names differ per plugin; this is what they do):

- `bDisableMissingScriptError` — suppress `Cannot open store` lines at log level.
- `bDisableNoPropertyOnScriptErrorLogs` — suppress cosmetic property-skew warnings.
- `iStackDumpTimeoutMS` — **lower** it so a dump fires before a freeze times out.
- `iMaxOpsPerFrame` — raise it on a heavy modlist.
- `bSpeedUpNativeCalls` — decouple native calls from framerate.
- `bIgnoreMemoryLimit` — memory ceiling back on, so the VM dumps instead of faulting.

Do not change the Papyrus memory page sizes on a heavy modlist; read the page-policy note first
(`skyrim-engine-knowledge`, papyrus-runtime).

## Reporting

Give the file and its age, the totals (entries, not lines, and the line count beside it), the counts per known shape, the
counts per real finding, and which of them are new since the last good launch. "No errors" is not a finding; "0 entries
matching `does not match existing signature`, 3 orphan stores, 1 stale duplicate native" is.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
