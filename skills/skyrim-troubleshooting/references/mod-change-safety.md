# Mod changes on a live save: the procedure

This is the workflow for "can I update, add or remove this mod" and for working a list of mods. The rubric that prices
each kind of change — and the rule that plugin removal is unsupported — is in
`skyrim-engine-knowledge`'s [save-safety.md](../../skyrim-engine-knowledge/references/save-safety.md). Read it first: this
file only says how to establish the facts the rubric needs.

Every mod is judged **against this user's save, load order and install**, never in the abstract.

## Step 0 — the situation, before any proposal

Most updates happen mid-playthrough, and that is where they do damage — but not every user is mid-playthrough, and the
same user switches between a kept save, a test save and a rebuild. The protections that matter for a kept save are
wrong for a new game, so assume neither.

Ask only what cannot be established from the machine, and keep doing read-only work while waiting:

- Is there a save to keep playing, or is this a new/throwaway game?
- What is this session for: updates only, new mods too, or fixing one problem?
- Is anything off-limits: no removals, no load-order changes, particular mods?

Record the answers where the user can see them (their own notes, or the review file below, dated) and **apply** them. A
ruling stated mid-session is recorded in the same turn, so the next session starts with it. If a ruling blocks the move
that looks right, say so and propose the compliant one; never write down an exception, not "just this once" — a tool's
documentation and this file do not outrank the user.

**A mod the user mentions is not a mod to install.** "I downloaded X and Y" is context, not a request: stay inside what
the session is for, and ask which of the others they want evaluated.

## Source-of-truth order

**What is on disk** (`Data/`, the mod folders, the SKSE log, the load order) **> the Nexus page** > **the mod manager's
records.** A manager tracks what it installed, not what was copied in by hand or reverted later, so its version number
is never presented as fact.

## The two stages

| | Stage 1: desk review | Stage 2: file review |
|---|---|---|
| Input | mod page, changelog, file list, the install | the actual archive, compared with what is installed |
| Cost | about a minute per mod, no downloads | per mod, needs the archive |
| Runs on | every mod in the list | only the mods Stage 1 could not close |
| Ends with | a record with a verdict, OR one specific Stage-2 question | a final verdict and install steps |

## Stage 1 — desk review, per mod

1. **Known-bad list.** If the user keeps one, a hit closes the mod as `DON'T`. Ask for it once and keep it with the
   review file.
2. **Identify the mod.** `python scripts\misc\nexus_gql.py search "<name>"` (or `grep` on description text) lists
   candidates. Ports, backports and "NG" rewrites share names: pick by author and page, and say which one you picked.
3. **Read the page.** `python scripts\misc\nexus_gql.py mod|desc|files <modId>` gives the summary, the author-declared
   requirements, the description and the file list with each file's notes. Look for requirements, runtime support,
   "new game", "uninstall", light-flag notes and patches. A part that could not be fetched is **not** "none"; say which
   part failed.
4. **Find it on disk.**
   - DLLs: `python scripts\logs\skse_load_status.py <filter>` gives the version each DLL reports and its load result at
     the last launch.
   - Plugins: present in the load order? where? (`housecarl_load_order_status`, then `housecarl_check`).
   - Scripts: `Scripts\*.pex` in the mod folder.
   - Assets: `housecarl_asset_status` says which mod wins a path.
   Not on disk = a new mod.
5. **Runtime build** (anything with a DLL): does a build for this runtime exist — in this mod, a separate page, or a
   port? None = `NO-VR-BUILD` (or the SE/AE equivalent). A page *claiming* support is provisional: only the archive's
   DLL and then the SKSE log line prove it loads. Look for an **old-named sibling** DLL on disk: SKSE loads both.
6. **Map the changelog and file list onto rubric rows.** "The author says it is safe to update" is evidence, not a
   verdict.
7. **Fit with this install:** are the requirements present at the needed version? Does it overlap something installed
   (same system, same records)? `housecarl_check` for conflicts, or `housecarl_records` for the record itself.
8. **Write the record** (below).

### Stage 1 may close a mod only as

- `UP-TO-DATE`, `DON'T` (known-bad list, author warning, proven conflict), `NO-VR-BUILD`;
- `SAFE`, only when **every** changed file is a no-footprint rubric row, any DLL is proven loadable on this runtime, and
  no DLL-plus-`.pex` pairing or co-save format change is involved.

Everything else gets a provisional verdict **plus one specific Stage-2 question**. Plugin and `.pex` changes go to
Stage 2 by default, because changelogs leave things out.

## The record — one per mod, every field filled

```
### <Mod name> — Nexus <id> (<author>)  ·  <VERDICT>  ·  Stage 2: <not needed | NEEDED: the question>
- On disk:   <version + files: DLL load result / plugin active? position / scripts> | NOT INSTALLED
- Latest:    <version, date>  ·  runtime build: <exists? which file>  ·  known-bad list: <hit | none>
- Changes:   <rubric rows this update hits, from the changelog and file list>
- Fit:       <requirements met? overlaps or conflicts?>
- Why:       <one or two sentences tying the verdict to the rows above>
- Steps:     <exact steps, or "none">
```

- Update verdicts: `SAFE`, `SAFE-WITH-STEPS`, `RISKY` (one at a time, checkpoint save between), `DON'T`, `UNCLEAR`
  (not proven safe, never "probably fine"), `NO-VR-BUILD`, `UP-TO-DATE`.
- New-mod verdicts: `ADD-OK`, `ADD-WITH-STEPS`, `NEW-GAME-ONLY`, `NO-VR-BUILD`.
- A mod that cannot run on this runtime is `NO-VR-BUILD`/`NO-RUNTIME-BUILD`, not `DON'T` — look for a port before
  closing it. A replacement (a port, a rewrite) gets its own record, cross-referenced.
- For a list, keep every record in **one file the user can see**, with a summary table (mod · verdict · Stage 2?) at the
  top, so the review survives across sessions.

## Stage 2 — file review, only for the mods Stage 1 left open

1. **Get the archive** from the user. Ask where their downloads are before asking for a file.
2. **Compare it with the install**, file by file: what is new, what is the same, what changed. A changed file is either
   the update or the user's own edit — the listing cannot tell you which.
3. **Is the installed copy pristine?** Users fix conflicts by editing plugins, and an update silently overwrites those
   fixes. Hash the installed plugin against the **original archive of the same version** (not the manager's staging copy:
   a hardlinked staging file changes together with the installed one). If no original exists for that version, say so
   and treat the plugin as possibly edited.
4. **Diff what actually changed**, record by record:
   `python scripts\esp\espdiff.py diff OLD.esp NEW.esp` (installed vs archive, or previous release vs current) prints
   what was ADDED, REMOVED or CHANGED and in which subrecords; `... summary PLUGIN.esp` counts masters, new records and
   overrides per type.

   Two caveats before reading the output: records are matched by FormID in each plugin's **own master numbering**, so
   when the master lists differ an override can shift and appear as removed + added (read the masters lines first); and
   exit 1 means something differs **or** a plugin was read only partly (INCONCLUSIVE) — those are different answers.
   Then read the changed records against the rubric's rows: removed or renumbered FormIDs, a light flag, a new master, a
   changed running quest (stages, aliases, fragments), added or removed scripts.
5. **Scripts.** Decompile or disassemble both versions (`scripts\esp\pexdis.py`, or the shipped `.psc` when present) and
   diff properties, states and removed scripts. An **added** property is the unresolved rubric row; a **removed** one is
   a discarded value plus a warning.
6. **DLLs.** Runtime build, version, the SKSE log line after install, and — if the DLL declares natives — a diff of the
   `.psc` signatures against the callers in `Scripts\*.pex`.
7. **Stateful DLL?** `python scripts\save\cosave_info.py COSAVE.skse` on the co-save of the save being continued lists
   who writes co-save records, by opcode (see [saves.md](saves.md)).
8. **Final record:** verdict, install steps, and the after-install check.

## Rollout: in waves, with play between them

Never install a whole approved list at once. Small waves: DLL-only updates first, then single plugin updates, then
scripted or quest mods one at a time. Activating a plugin that is on disk but inactive **counts as adding it**. Between
waves the user plays and confirms the game is healthy, so a problem traces to one small wave.

Before each wave: the user backs up the save they continue (`.ess` **and** `.skse`) and the load order files. A new mod
goes into a **new mod folder the user enables**; never into another author's folder, never a bare copy into `Data/`.

## After installing, every wave

- The SKSE log line for each touched DLL (`skse_load_status.py`).
- The Papyrus log for `does not match existing signature`, `Cannot open store`, `not found`, and
  `Replacing native function` (a stale duplicate plugin): `papyrus_triage.py`.
- A game load by the user. RISKY items one at a time, with a checkpoint save between.

## Record what you learn

A mod or build that is broken on this runtime, or a coupling between mods, goes in the same review file, so the next
session's Stage 1 finds it. That file is the difference between a one-off answer and a review that survives.

## Mistakes this procedure exists to stop

| Mistake | Reality |
|---|---|
| "DLL-only, update whenever" | true for the save only; on VR it must be a VR build, and SKSE refuses another runtime's DLL silently |
| Trusting the mod manager's attribution | a manager can file a DLL under the wrong mod when files are dropped over each other; the bytes and the SKSE log decide |
| Updating a fork without removing the old DLL | SKSE loads both, and the older one can override the newer one's functions |
| "The author says it is safe" = `SAFE` | evidence only; map the changed files onto the rubric |
| A new Start-Game-Enabled quest "will just start" | not always on an existing save; confirm it is running before relying on it |
| Reading "could not check" as "no update" | nothing was compared; fix the query or the network and run it again |
| Judging a mod by its category | judge it by the files it ships: a texture mod with a plugin is a plugin update |

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
