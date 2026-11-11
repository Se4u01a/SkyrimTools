# Save files: format, scanning, bloat, bloat's causes

A save is a pair: `SaveN_....ess` and its `SaveN_....skse` co-save, same folder and same basename. **Treat them as one
object** — copying, moving or restoring one without the other produces a save that loads with half its state.

Three different questions get confused here: what a save *contains*, why a save *grew*, and whether a mod is safe to
*change* on it. The first two are this file; the third is [mod-change-safety.md](mod-change-safety.md).

## The `.ess` format, as far as raw reading goes

- SSE, AE and VR saves use the same `.ess` format with **LZ4** compression. The compressed block is preceded by a
  `(decompressedSize, compressedSize)` uint32 pair; typical decompressed sizes are 20-60 MB.
- Decompressed layout, top level:

| Region | Bytes | Contents |
|---|---|---|
| preamble | 0-5 | header bytes |
| plugin table | from byte 5 | regular plugin count (uint8) and length-prefixed UTF-8 plugin names |
| light plugin table | after the regular list | light plugin count (uint16) and length-prefixed names |
| change forms | ~100 KB - 22 MB | global data tables and binary change forms (mostly non-ASCII) |
| Papyrus data | ~22 MB + | script names, variable names, type annotations |
| reference tables | end | dense FormID arrays |

- A screenshot is stored near the header, which is why some byte ranges look like noise.
- The plugin lists are the save's own record of the load order at save time. That is what makes moving plugins possible
  at all (`skyrim-engine-knowledge`, save-safety).

## What raw scanning can and cannot do

`python scripts\save\ess_scan.py` is the raw reader. It is read-only and walks the header, the LZ4 body and the plugin
table:

```
python scripts\save\ess_scan.py list                       # .ess/.skse pairs in the saves folder found here
python scripts\save\ess_scan.py info SAVE                  # header fields, sizes, plugin counts, body structure
python scripts\save\ess_scan.py plugins SAVE               # the regular and light plugin table
python scripts\save\ess_scan.py search SAVE --string TEXT  # also --formid 0001ABCD, --hex DEADBEEF
python scripts\save\ess_scan.py strings SAVE --grep TEXT
python scripts\save\ess_scan.py forms SAVE --by-plugin
```

`SAVE` may be a `.ess` file or a folder (the newest `.ess` in it is used). The saves folder is discovered as
`SKYRIM_DOCUMENTS_DIR`, the Windows Documents folder with `My Games\Skyrim Special Edition` (then GOG, EPIC), then
`Skyrim VR`, then `%SKYRIM_MO2_DIR%\profiles\*\saves` — so on an MO2 install with profile-local saves, that is where it
looks. Exit 1 means the parse is **INCONCLUSIVE**: say what it could not walk instead of reporting the partial numbers
as complete.


It can:

- extract the regular and light plugin lists;
- find a FormID (as a little-endian uint32), a string, or a byte pattern, and count occurrences;
- show context around a match;
- compare decompressed sizes across saves.

It cannot:

- parse structured Papyrus instance data (variable values, active effect state);
- list orphaned *instances* — a script-name hit is a **lead**, not a count;
- establish that effects stack from a FormID byte count;
- write a valid save back.

Those are limits of **byte scanning**, not of save analysis: a structured parser (a ReSaver-class tool, an external
Java/C++ project that this repo does not ship) parses change forms, the Papyrus instance and string tables and a real
reference index, and can edit and write a new save. If the answer needs structured data, say that the raw scan cannot
give it, rather than inferring it from byte counts.

## Bloat triage, in order

1. **Measure, don't guess.** Record `decompressedSize` for several recent saves and the growth between them. A save that
   grows steadily across quiet play is a leak; one that grows once after a big cell is normal.
2. **Orphaned scripts**: search for the script names of a removed or lobotomized mod. A hit means the save still holds
   instances. That is expected after a removal (see the removal rule) and is what an orphan clean exists for.
3. **Duplication or accumulation**: search a spell's or a form list's FormID and count occurrences. **More than
   expected is a lead, not proof** — the same FormID appears in references, change forms and lists.
4. **Mod footprint**: search a mod's EditorID prefix to see whether it left anything behind. That is a footprint, not a
   semantic reference count.
5. **Ordering**: compare the plugin lists of the save and the current load order. A save naming a plugin that is no
   longer installed is the beginning of the whole orphan story; a save naming fewer plugins than the order is not a
   problem.
6. **If it needs structure** (which instance is orphaned, which variables hold what), go to a structured parser and say
   so.

## The co-save (`.skse`)

- SKSE gives each plugin a chunk in the co-save. `python scripts\save\cosave_info.py COSAVE.skse` prints a **read-only**
  JSON survey: the header fields and a per-opcode chunk inventory (count and total bytes). `--chunks` lists every chunk
  in file order, `--top 5` limits the inventory to the five largest opcodes. It never writes.


- The walk is `{u32 type, u32 version, u32 length}` per chunk; it resynchronises after a desync and **reports its
  coverage**. Exit 1 means coverage under 90 % (or no chunk found), so the totals are indicative only — say that rather
  than quoting them as complete. It does **not** decode the plugin-internal format inside a chunk; that is undocumented
  per plugin.
- Opcodes it names: `REGS`/`PLGN`/`REGE` are SKSE's own registrations, `JSTR` is JContainers, `STRV`/`STFV`/`STRL` are a
  StorageUtil-style API, `P3PE` is a Papyrus extender. Anything else is mod-specific and is reported raw, by size, for
  the load order's owner to identify.
- **`PLGN` is the load order at save time**: a u16 count, then per entry a u8 index (`0xFE` followed by a u16 light
  index for a light plugin), a u16 name length and the name. It is what resolves the FormIDs stored elsewhere.
- **Counts inside a chunk are not always 4 bytes.** MEASURED on one Papyrus-extender plugin's co-save (chunk version 8):
  counts are 8-byte `size_t` values, and a decoder reading 4-byte counts desynchronises silently after the first one.
  A "successful" decode that produces nonsense past chunk one is this bug.
- Use it to answer **which plugins stash state** (and therefore which DLL updates touch save data) before an update,
  not to read the state itself.

## Cleaning or repairing a save

- **Never overwrite the input save.** Work on a copy, write to a **new** file, and let the user load it. Keep the
  original pair untouched and named in the report.
- A structured cleaner's write path should be dry-run first, then applied to a new file, with a re-read comparison of
  what it wrote. If the tool reports a failed round trip, treat the output as broken and say so.
- Cleaning removes orphaned and unattached script instances; it does **not** undo a removed plugin's missing forms, and
  it cannot make a save whose masters are gone load.
- **The final validation is the user loading the save in game.** Say that, every time.
- After cleaning, the `Cannot open store` lines should not come back on the next load if the scripts are also gone from
  disk. If they do, the clean missed instances or the plugin is still installed.

## "My save will not load"

In order of likelihood, and each has a check:

1. **A master the save needs is gone or moved** — compare the save's plugin list with the current load order by name,
   not by index.
2. **A plugin changed slots** (full ↔ light) or was compacted — the save looks for IDs that no longer exist; the update
   rubric marks both `DON'T`/`RISKY` for a reason.
3. **A plugin was removed and its script instances now point at nothing** — the save may still load with orphan noise;
   if it does not, that is the removal rule, not a bug in the save.
4. **Heap corruption from a malformed light plugin** — the engine-knowledge ESL note records one such crash at save load
   whose cause was never established; test the plugin alone before blaming the save.
5. **A save written by a newer game build or a different runtime** — do not migrate across runtime versions by editing
   bytes.

## Reporting

State the pair (both file names), whether the save was modified at all, the sizes compared and over what period, the
counts found and what they do **not** prove, and what the user must do next (load the copy, keep the original). If a
structured parse was needed and none is available, say which question is still open instead of inferring an answer from
bytes.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
