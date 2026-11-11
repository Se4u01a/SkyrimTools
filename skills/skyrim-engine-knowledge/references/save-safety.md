# Save safety: what a change costs on an existing save

The two claims this file exists to get right: **removing a plugin from a live save is not supported**, and **the risk of
an update is decided by what it changes**, never by what the mod is called. The procedure that applies this rubric (with
the repo's tools) is the troubleshooting skill's *mod changes* reference.

## ESP removal and existing saves (CRITICAL)

**Never remove or disable a plugin from the load order of an existing save.** The rule stands; the reason usually given
for it is wrong (corrected 2026-10-05).

- ~~Removing a plugin shifts downstream load-order indices, which resets their quest and script state.~~ **Refuted.**
  The `.ess` carries a plugin-**name** table (`pluginInfo`, plus a separate `lightPluginInfo` list for light plugins)
  and a `formIDArray` of save-time FormIDs; on load the game remaps save-time IDs to the current order. SKSE's
  `ResolveFormId` documents exactly that contract for co-save data: it "takes a formID as it was when the save was made
  and writes the formID as it is when the save is loaded". READ: UESP *Skyrim Mod:Save File Format*, CommonLibSSE
  *Serialization*. "Remapped by plugin name" is INFERRED from that format rather than quoted from a page, but no source
  supports a reset, and inserting or reordering is routine on long saves.
- **The real dangers of removal:** every form from the removed plugin is dropped from the save, while its script
  instances stay baked in (`Cannot open store for class "X", missing file?` in the Papyrus log); references, aliases,
  inventory items and other mods' scripts that pointed at those forms dangle. The CK *Save File Notes (Papyrus)* says
  plainly that removing mods and continuing the same save is not supported by the game. That is why the technique below
  exists.

**Lobotomize instead.** Keep the plugin in the load order so its forms stay resolvable, and strip its functionality:

1. remove the compiled scripts (`.pex` files from `Data/Scripts/`);
2. disable the SKSE plugins (`.dll` → `.dll.disabled`);
3. disable distribution files (SPID/KID/SkyPatcher `.ini` → `.ini.disabled`) if applicable;
4. clean the save to remove the orphaned script instances (with the `.pex` gone they cannot re-create).

The plugin stays as a hollow shell. Removing it outright is only on the table when the user is starting a new game.

**In this repo's rules** steps 1-3 act on another author's mod folder, which is out of bounds unless the user explicitly
asks: name exactly which files must go and let the user do it in their mod manager (disable the mod, or hide the files).
Only suggest removing a plugin at all when the user is starting a new game.

Source: direct experience in the source project — the lobotomy approach is confirmed working.

## Updating or adding mods on an existing save: the safety rubric

**Classify every update by what it CHANGES, never by what the mod "is".** A "DLL mod" that also ships `.pex` files is a
script update; a "texture mod" that ships a plugin is a plugin update. Open the archive, sort its files into the rows
below, and the riskiest row present sets the verdict.

**Verdicts:** `SAFE` · `SAFE-WITH-STEPS` · `RISKY` (one at a time, checkpoint save between) · `DON'T` ·
**`UNCLEAR`, which means "not proven safe", never "probably fine"**. `UNCLEAR` needs the archive, a diff, or a live test
on a save copy before it can move. For a mod not yet installed: `ADD-OK` · `ADD-WITH-STEPS` · `NEW-GAME-ONLY`.

### 1. What the update changes, from no save footprint to deep

| Changes | Save footprint | Default verdict | Why / what to check |
|---|---|---|---|
| Textures, meshes, sounds, voice, strings, INI/JSON/TOML config | none | SAFE | Nothing is stored in the save. VR caveats still apply: PreWEAPON/PreSHIELD skeleton nodes crash, and a flat-screen `.swf` can replace a VR one. |
| Animations / behaviour (`.hkx`, OAR configs) | none | SAFE-WITH-STEPS | No save data, but behaviour output may need regenerating (Nemesis/Pandora). An OAR config change needs no regen. |
| SKSE DLL that writes **no co-save records** and registers no Papyrus natives | none | SAFE *if loadable on this runtime* | See §2. Revert = put the old DLL back, even on the same save. |
| SKSE DLL **that writes co-save records** | `.skse` co-save | SAFE-WITH-STEPS | SKSE hands each plugin its record `version` and leaves the format to the author. A DLL that ignores its own version field after a format change is UNSOURCED territory: read the changelog for "save format" or "reset". Back up the `.skse` together with the `.ess`. |
| SKSE DLL **+ its `.pex`/`.psc` native declarations** | depends | SAFE-WITH-STEPS | The pair must move together. A mismatch logs `does not match existing signature` and the native goes unbound. |
| Plugin record **field edits, FormIDs unchanged** | partial | SAFE-WITH-STEPS | Base-record edits apply on load, except for fields the save already changed (change forms). Visited cells, opened containers and met NPCs keep their baked state until a reset, so the "fix" may be inert on an existing save. That is lost value, not damage. |
| Plugin: **records removed** that the save may reference | dangling refs | RISKY | Same as removal: dropped forms and orphaned instances. Needs a diff. |
| Plugin: **FormIDs renumbered / compacted** | broken refs | **DON'T** | The save looks for the old IDs. Compacting is also unsupported for a mod with generated facegendata, scripts or `.seq` files. |
| Plugin: **light (ESL) flag added**, IDs already within `0x800`-`0xFFF` | slot move | RISKY | The plugin moves from a full slot to the FE light list. The remap should cover it (INFERRED), but community advice is new games only. |
| Plugin: **light flag removed** | slot move | RISKY | UNSOURCED. Treat like the row above. |
| Plugin: **master added** | none, if the master is present | SAFE-WITH-STEPS | The new master must already be installed and load earlier. Once in a save, masters cannot be dropped. |
| Plugin: **running quest** changed (stages, aliases, fragments) | baked | RISKY | QUST is a change form, so alias fills and stage state persist. Changes land only when the quest restarts (INFERRED). |
| `.pex`: **function bodies only** | none | SAFE | "Adding functions: no issues occur." A frame already on the stack finishes on the OLD code; later calls use the new code. |
| `.pex`: **variable/property removed or renamed** | warning | SAFE-WITH-STEPS | The saved value is discarded with a log warning, and the warning stops after the next save. A rename counts as delete + add. |
| `.pex`: **property ADDED** | unresolved | RISKY / UNCLEAR | **Sources conflict:** the CK page says a new auto property takes the plugin's value, while a Skyrim LE report says instances already in the save stay `None`. Non-auto properties stay blank after load (see [papyrus-runtime.md](papyrus-runtime.md)). Settle it with a live test on a save copy before trusting an update that depends on it. |
| `.pex`: **existing property's VALUE changed** in the plugin | baked | inert on an existing save | "Changing the value will not overwrite the value it has in the save game" (unless the property is `const`). The update's fix may never reach the save. |
| `.pex`: **script, state or quest removed** | orphans | RISKY | `Cannot open store for class`. An orphan clean can remove unattached instances afterwards. |
| Long-running loop or registration in a changed script | persistent | RISKY | `RegisterForUpdate` and event registrations persist until unregistered. A loop on the stack keeps running old code until it exits. |

**Things that LOWER script risk:** the mod has a version-migration path — a SkyUI MCM `OnVersionUpdate`, a maintenance
quest on `OnPlayerLoadGame`, or an "update/reset" button. Confirm it exists in the decompiled source; do not trust the
description.

### 2. SKSE DLLs: the runtime gate comes before save safety

"DLL-only = update whenever" is true for save safety only. A DLL can still be wrong for the runtime:

- **It must be a build for this runtime**, or a CommonLibSSE-NG / CommonLibVR multi-runtime build that declares it. An
  SE/AE-only DLL on VR is at best refused by SKSE, which disables the feature silently, and at worst crashes; NG itself
  warns of "fundamental ABI incompatibilities between SE/AE and VR".
- **A newer Address Library can be a hard prerequisite even when the mod's stated minimum is met.** MEASURED on one VR
  install: a DLL whose stated minimum Address Library was 0.235.0 stopped the game before SKSE finished starting,
  missing ID 40291, with 0.276.1 installed; with 0.279.0 it loaded. Update the Address Library first when a DLL update
  fails early, and treat a stated minimum as a claim to check against the log.
- **Forks and renames leave the old DLL behind, and SKSE loads BOTH.** A renamed fork's old DLL beside the new one is
  the classic case; the older one can replace the newer one's native functions. After any update, look for an
  old-named sibling.
- **The proof is the SKSE log, not the install:** every DLL gets one result line in the SKSE log —
  `loaded correctly`, `reported as incompatible during query|load`, or `does not appear to be an SKSE plugin`. Diff that
  file before and after each update (the troubleshooting skill's *SKSE DLLs* reference has the verdicts).
- **Find stateful DLLs from the save itself:** the co-save lists its records by opcode
  (`python scripts\save\cosave_info.py COSAVE.skse`). JContainers (`JSTR`), PapyrusUtil (`STFV`/`STRL`/…), Papyrus
  Extender (`P3PE`), SPID and DbSKSEFunctions are common writers; many opcodes will be unnamed because the format inside
  a chunk belongs to its plugin.
 
- **A VR mod's MAIN file on Nexus can be the SE/AE build.** MEASURED on one mod whose MAIN download was SE/AE-only while
  the VR DLL came from the author's GitHub release. An `openvr` string inside a DLL is **not** proof of VR support: the
  SE/AE DLL contained one too. Judge by the declared runtime support and runtime guards, or by the SKSE log after a
  test start, never by a string search.

### 3. Adding a mod that is not installed yet

- **Appending, or inserting mid-order, does not corrupt other mods' saved state** (see the correction above). It CAN
  change which plugin wins records other mods depend on: check what the new plugin newly WINS before activating
  (`housecarl_check`, or see the troubleshooting skill's *conflicts* reference).
- **Adding a scripted mod is a one-way door.** Removal is unsupported, so the only exit is a lobotomy. Weigh that before
  adding, not after.
- **Start-Game-Enabled quests.** Community sources say SGE quests still start on an existing save, but their dialogue,
  scenes and some fragments need a matching `Data/SEQ/<plugin>.seq` plus a save and reload. **One measurement
  disagrees**: a single SGE quest did not auto-start across several loads and needed `Quest.Start()` plus a save
  (MEASURED once, 2026-07-09; one quest, one load order, not a general rule). So: check that the SEQ file ships, then
  confirm `Quest.IsRunning` after the first load. Do not assume it started.
- **Plugin slots:** count the full and light slots from the load order at decision time (and whether a light-plugin
  support plugin is loaded); do not carry a number over from an earlier session.
- **The author's "requires a new game" is an author ruling, not an engine rule.** Respect it unless a diff proves
  otherwise.
- **Distribution mods (SPID/KID/SkyPatcher)** apply at runtime on every load, so they can be added without a save
  footprint — except for what they hand out (spells, perks, items), which actors then carry.

### 4. The routine for every update session

1. **Baseline before touching anything:** copy the current `.ess` **and its `.skse`**, the load order files, snapshot
   the SKSE log, and run the Papyrus and crash triage so "after" has a "before".
2. **One RISKY change at a time,** with a checkpoint save between, so a break can be bisected. SAFE items can be
   batched.
3. **Install through the mod manager** (or a recorded, backup-taking manual install), so every file stays attributable.
4. **Verify from the outside after each batch:** the SKSE log result line for every touched DLL, a game load by the
   user, and a Papyrus log diff for new `Cannot open store`, `does not match existing signature` or `not found` lines.
5. **If something breaks:** asset or DLL → restore the backup, on the same save. Plugin or script → roll back to the
   pre-change save. Never "fix forward" a save that loaded a bad script state.

**Sources:** UESP *Skyrim Mod:Save File Format* and *Skyrim:Form ID*; CommonLibSSE *Serialization*; CommonLibSSE-NG
*Runtime Targeting*; CK *Save File Notes (Papyrus)* and *Persistence (Papyrus)* (read through a mirror of the Fallout
wiki, because the Skyrim pages reject bots; VM rules are shared but were not re-confirmed on the Skyrim page); Nexus
forum threads on new properties being `None` on existing saves and on orphan log lines; a mod page on safe ESL
conversion; a SEQ-generation mod's README; a Nexus article on mods, stability and saves. Rows marked INFERRED or
UNSOURCED are claims to test, not facts.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
