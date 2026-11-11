# Which install, which path, which plugin wins

Most wrong answers in Skyrim triage are not wrong analysis — they are analysis of the wrong install. This file is how
to establish *which* folders, load order and file the answer came from, before anything is concluded.

## More than one `plugins.txt`, more than one `My Games` folder

A machine that has ever had more than one Skyrim installed carries several copies of the same per-game state, and
**nothing errors when the wrong one is read**:

- `%LOCALAPPDATA%\Skyrim VR\plugins.txt`, `...\Skyrim Special Edition\plugins.txt`, `...\Skyrim\plugins.txt` — the active
  load order.
- `Documents\My Games\Skyrim VR\`, `...\Skyrim Special Edition\`, `...\Skyrim\` — INIs, `Logs\Script\Papyrus.*.log`, and
  the `SKSE\` folder with the SKSE log and the crash dumps.
- Under MO2 the load order lives in the instance instead: `profiles\<profile>\plugins.txt` and `loadorder.txt`.

MEASURED on one VR-only install: the **SSE** `plugins.txt` exists, holds 659 plugins, and was **18 days stale**. It
disagrees with the VR file about what is active, and it is a perfectly valid file. A stale-but-valid load order produces
a complete, plausible, **wrong** answer, and every conflict answer computed from it is confidently wrong.

- The older claim that "the SSE `plugins.txt` does not exist on a VR install" is contradicted by that measurement. Do
  not assume its absence.
- **Pick deliberately, report the rivals, offer an override.** The bundled log tools probe `Skyrim VR` →
  `Skyrim Special Edition` (including its GOG and Epic folders) → `Skyrim`, use the first that exists, and name every
  rival they ignored on **stderr** together with the variable that overrides the choice:
  `SKYRIM_DOCUMENTS_DIR` (the game folder under Documents), `SKSE_LOG_DIR`, `SKSE_CRASH_DIR`, `PAPYRUS_LOG_DIR`.
  So a wrong pick is corrected without editing the tool, and the stderr block is part of the answer.
- `housecarl_load_order_status` names the instance the record layer resolved; `housecarl_set_mo2_instance` changes it.
  Ask it first whenever a record answer looks surprising.



When a tool prints more than one candidate folder, that line is part of the answer, not log noise. Quote it.

## MO2's virtual file system

**Mod Organizer 2 has no real merged `Data/`.** It builds a *virtual* one when it launches a program through itself, by
overlaying in priority order: the stock game's `Data/`, then each enabled mod's own folder, then `overwrite/` (highest).
That view exists **only while MO2 runs that program**.

| Thing | Stock / Vortex | MO2 |
|---|---|---|
| A mod's actual files | `Data/...` | `<instance>\mods\<mod name>\...` |
| INIs | `Documents\My Games\<game>\` | `<instance>\profiles\<profile>\` (when profile-specific INIs are on) |
| `plugins.txt` / `loadorder.txt` | `%LOCALAPPDATA%\<game>\` | `<instance>\profiles\<profile>\` |
| Files a tool writes into `Data/` at run time | land in `Data/` | land in `<instance>\overwrite\` |

- **Finding the instance:** global instances live in `%LOCALAPPDATA%\ModOrganizer\<InstanceName>\`; a portable instance
  keeps everything in its own install folder. Either way the settings are in `ModOrganizer.ini`: `[General]` holds
  `gamePath`, `gameName`, `selected_profile`; `[Settings]` holds the optional `base_directory`, `mod_directory`,
  `profiles_directory`, `overwrite_directory` overrides, which may contain the literal token `%BASE_DIR%`. Values are
  QSettings-escaped, so backslashes are doubled.
- Match an instance to a game folder by comparing its `gamePath`. Two instances can point at one game; one game can be
  visible to two tools.
- **Never edit `ModOrganizer.ini` while MO2 is running** — MO2 rewrites it from memory on exit, and the edit disappears.
  The user changes executables and profiles in the GUI.

## The silent-wrong-answer trap: load-order tooling outside MO2

A record library that finds the game path from the registry sees only the plugins physically present in the stock
`Data/` — which on an MO2 setup is the base game and very little else. It does not error. It returns a **wrong but
entirely plausible** answer for anything involving the override chain, conflict resolution or the full load order.

- **Needs the VFS** (run it through MO2's executable list): override-chain resolution, "what wins this conflict",
  anything reading the full load order, load-order-dependent edits.
- **Works fine outside MO2:** reading or editing a **single plugin by path**, because that never consults the load order.
  This is the main reason a text round trip of one plugin is the safe route on an MO2 install.
- The same logic applies to every tool that resolves the game path from the registry rather than from an explicit file
  path — including the game-folder scanners of log tools, which is why they print their candidates.

## Never bare-copy a mod into `Data/` on a managed install

- **Vortex** tracks deployed files; a hand-placed file is untracked, and a later deploy or purge can clobber or orphan it.
- **MO2** builds `Data/` virtually; a file written to the real `Data/` is not part of any mod, does not appear in the
  conflict view, and will not behave like the rest of the load order.
- Either way it is invisible to the user's own record of what is installed, which is exactly the state that makes a
  broken install impossible to debug later.

So: **a new mod folder, enabled by the user**, or the user's mod manager. "It's just one DLL" is how an install becomes
unreproducible. This repo's own rule is the same one: never write into another author's mod folder, and a new folder does
nothing until it is enabled.

### When the user installs by hand anyway

A recorded manual install (dry run first, showing every destination; anything outside `Data/` flagged and brought to the
user; a backup of what is replaced plus a hash manifest) is the minimum. Read the destinations before applying, and check
the result after: the written files hash-match, and the game loads. Under MO2, the correct outcome is a new folder in the
instance's `mods\`, not a write into `Data/`.

## Vortex: a purge puts `.vortex_backup` files back

MEASURED on one install (2026-10-05 and 2026-10-13):

- When Vortex deploys a mod over files that already exist unmanaged, it renames them `*.vortex_backup`. When that mod is
  disabled or purged, Vortex renames the backups back, so **an old manual copy returns**. "Disabled in Vortex" does not
  mean "gone from `Data/`". Before installing a replacement for a framework, inventory its folders by date and by Vortex
  ownership (`vortex.deployment.json`).
- It can also leave a `*.vortex_backup` with no original beside it. After one mod that had overwritten meshes was
  disabled, two NIFs existed only as `.nif.vortex_backup` and the item was invisible in game. A whole-`Data/` scan found
  748 backups, 30 of them without an original. **After any purge, scan for orphans.**

## Which plugin wins a record, and which file wins a path

- **The last-loaded plugin that touches the record wins.** A record question is answered against the **whole** load
  order; a who-wins answer computed against a hand-picked subset is only as complete as the guess — a plugin outside the
  list can win and never be seen. Worse, a short list can silently load nothing and still resolve, producing a confident
  answer from an empty tree.
- With the houseCARL server: `housecarl_load_order_status` (which instance), `housecarl_check` (conflicts),
  `housecarl_records` (the record), `housecarl_asset_status` (which mod or archive wins a path). Load-order answers are
  cheap enough to recompute per question; do not cache a winner across a session.
- **Without houseCARL:** `scripts\esp\espscan.py` reads **raw subrecords** from one plugin, and a file search under
  `mods\` ordered by `modlist.txt` finds a candidate asset winner. Say that the answer is raw subrecords or a file
  search, not a resolved record or a conflict verdict. Do not improvise record writes.
- **Loose files always beat archives**, and archives beat each other by archive load order. On MO2 the "loose file" is a
  virtual one, so a search of the real `Data/` can miss the winner entirely.
- A file that two mods both ship has a winner determined by mod priority, not by install date or file time.

## Listing traps

- **A listing with a default limit looks complete.** MEASURED: an archive lister defaulted to 100 entries, and a
  1,571-file archive read as holding 100 files, which produced a confident and completely wrong conclusion about 709
  missing textures. The listing carried its own `showing` and `total` fields. Compare them before concluding anything is
  missing; a filtered listing legitimately shows fewer than the total.
- **An archive tool that can list may still need an external helper to extract or repack**, and that helper may refuse
  an output folder that does not exist yet. Create the folder first.
- **Compare process identities from one source only**: two Windows APIs can give the same process start time with a
  different last fractional digit, so a mismatch between sources proves nothing.

## Reporting

Name the folder you read and its age, the instance and profile, whether the answer came from the virtual file system or
from a physical folder, and whether the conflict answer is a resolved verdict or a raw-subrecord reading. If a tool
ignored candidates, quote them.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
