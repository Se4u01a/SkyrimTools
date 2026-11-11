# Records and plugins

How a plugin file is put together and which record fields do not behave the way they read. Schemas (fields, types,
cardinality, enum values) are `mutagen-reference`; authoring a plugin through YAML is
[esp-yaml-and-spriggit.md](esp-yaml-and-spriggit.md); live record/conflict reads are the troubleshooting skill.

## VMAD (Virtual Machine Adapter)

- The VMAD subrecord attaches scripts and their properties to a record. **It must be read sequentially** — no lengths
  or offsets are provided, so selective editing without corrupting adjacent data is not possible.
- Building one from scratch is fragile: known bugs with complex property structures, and tools cannot parse VMADs with
  illegal struct definitions (structs within structs, arrays in structs).
- Adding a **new script** to a VMAD is harder than removing a property; script fragments need a correct
  `fragmentCount` or quest aliases corrupt.
- For 25+ properties the reliable route is a template record created in the Creation Kit, then copying the VMAD
  subrecord. Simple cases (1-3 properties) can be written programmatically.
- The cheapest alternative is not having properties at all: `Game.GetFormFromFile` on your **own** plugin's forms (see
  [papyrus-runtime.md](papyrus-runtime.md)).

READ: UESP *VMAD Field*, the TES5Edit VMAD issues.

## Record and plugin structure traps

- **ONAM**: any ESM-flagged module that overrides temporary CELL children must list every overridden record in ONAM
  subrecords. Missing entries are silently ignored by the engine. An ESM cleaned with Quick Auto Clean must be resaved
  to fix incorrect ONAM.
- **Every reference in an ESP is treated as permanent** regardless of its Temporary flag; only ESL-flagged plugins
  really support temporary references.
- Record flags do not always survive a drag-and-drop between plugins.
- The **Partial Form flag** removes every subrecord except the EditorID.
- **A dict keyed by FormKey can hide a duplicate.** MEASURED on one plugin: two records shared object ID `0x860` (a
  weapon and an unused explosion), one collapsed the other, the count disagreed with the edit tool, and the edit tool's
  error check reported nothing. Assert key uniqueness and keep record type + EditorID beside each entry.
- **Reused vanilla records can carry gating Conditions.** If a reused magic effect or spell fires on some targets and
  not others ("hit or miss"), suspect Conditions on the MGEF before anything else: vanilla effects are often built for
  a quest context and carry `HasKeyword`, `GetRestrained` and similar checks that quietly gate the reuse, with no error
  anywhere. Checklist: own the record first and strip the Conditions on your copy (so no other mod's override can
  reintroduce the gate), check delivery (a Constant-Effect/Self ability applied by `AddSpell` lands instantly; an Aimed
  projectile can whiff), and check **Resist Value** — a separate axis from Conditions; set it to `None` for
  unresistable. Serializing the copy is the fastest way to see inherited fields you never set.

## Plugin types

| Type | Load position | FormID range | Limit | Notes |
|---|---|---|---|---|
| ESM | top of the order | full range | 254 ESM+ESP total | supports temporary references properly |
| ESP | after the ESMs | full range | 254 ESM+ESP total | treats **all** references as permanent |
| ESL (light) | shares the FE slot | `xx000800`-`xx000FFF` at header 1.70 | 4096 FormIDs (2048 usable at 1.70) | |

ESL rules:

- **Recommended: new records at object IDs `xx000800`-`xx000FFF` with a header-1.70 plugin.** That range is what every
  ESL-capable runtime accepts, and IDs above `0xFFF` do not fit a light plugin at all.
- **Below `0x800` is runtime-dependent, not a rule either way.** Header 1.71 lets SE 1.6.1130 and later use object IDs
  from `0x001`, and modern SE tools generate light plugins that way. Skyrim VR has no native ESL support, so there it
  depends on the ESL-support plugin in use. MEASURED on one VR install, not generalised: a header-1.71 light plugin
  with most records at `0x002`-`0x7FF` loaded and played normally (the ESL-support plugin's log said it emulated the
  old header version), while a different header-1.71 plugin with every record below `0x800` was followed by a
  heap-corruption crash at save load whose cause was never established. Neither "always crashes" nor "safe" is proven:
  before enabling such a plugin, check its new-record ID range, install it alone, and verify it on that runtime.
- Tools disagree on where compaction starts (`FE000xxx` vs `FE001xxx`). ESP→ESL conversion requires compacting FormIDs
  **and** setting the ESL flag.
- Compacting is unsafe for a mod that ships generated facegendata, scripts or `.seq` files.

## Load order and override resolution

- The **last-loaded** plugin that touches a record wins; it overrides every lower plugin. A conflict view that hides
  non-winning overrides prevents false positives, and removing a plugin does not shift the meaning of the others (see
  [save-safety.md](save-safety.md)).
- "Copy as override" resolves against the highest override visible to the target file, which follows that file's
  masters.
- A plugin's own records use a mod index equal to **its master count** (`0x05` with 5 masters), which is what
  `GetFormFromFile` prefixes must match.

## Archiving (BSA/BA2)

Priority, highest first:

1. **Loose files in `Data/`** — they always win.
2. Plugin-associated archives, in plugin load order.
3. Vanilla/engine archives named by the INI.

- SSE/VR support two archives per plugin: `MyMod.bsa` and `MyMod - Textures.bsa`.
- Archives override each other by position in the archive load order; later wins.
- On an MO2 install the loose-file winner is a virtual one — see the troubleshooting skill's mod-manager reference
  before concluding that a file is where it appears to be.

READ: the modding wiki's asset load order page.

## Field semantics that do not match the field name

### Spell effect Area is in FEET

- Effect `Area` is measured in **feet**, not game units. 1 foot ≈ 21.3 game units ≈ 30.5 cm.
- `Area=60` is a ~18 m **radius** (36 m across), not 60 units (~85 cm). `Area=200` ≈ 61 m radius; `Area=3` ≈ 0.9 m;
  `Area=1` ≈ 0.3 m.
- A sword-width effect is `Area=2-3`; a stagger aura or splash is `Area=10-15` (~3-5 m).
- This applies to every spell effect: damage, healing, cloak, area denial.

### Explosion knockback needs a Knock Down flag, not more Force

- An `EXPL` record's `DATA\Force` **only moves actors when a Knock Down flag is set** in `DATA\Flags`. Without
  `Knock Down - Always` or `Knock Down - By Formula`, force 3, 50 or 1000 produces zero knockback. The parameter looks
  like the knob and is not.
- `Knock Down - Always` ragdolls every affected actor regardless of mass; `By Formula` is mass-weighted and gentler.
- Force pushes **radially away from the centre**, so a self-centred explosion flings distant actors outward; a
  directional fling needs an offset centre.
- For simple visible knockback, engine-native `PushActorAway(target, 1-5)` is usually better than an explosion.

### MGEF archetype is spelled `Archtype`

The MGEF archetype field is literally misspelled **`Archtype`** in the record; a scan for `Archetype` silently matches
nothing. READ: the record, through any path-based tool.

### WEAP: `BasicStats` and `Data` are different sections

Swapping them yields an **invisible weapon** — the record exists, has no mesh and no icon. Confirmed against working
records:

- `BasicStats` = `Value`, `Weight`, `Damage` (the stat-card numbers).
- `Data` = `AnimationType`, `Speed`, `Reach`, `Flags`, `NumProjectiles`, `AnimationAttackMult`, `Skill`, `Stagger`,
  plus the always-present `Unused`, `Unknown2`, `Unknown3` fields.
- Fields that matter for a visible weapon: a model path, `Model.Data: 0x020000000000000000000000` (the MODT subrecord,
  present in every working record), `ImpactDataSet: 013CAC:Skyrim.esm` (without it, no hit sounds or effects), a
  `Critical` section even when minimal, `DetectionSoundLevel`, and an `ObjectBounds` default of
  `First: -32768,-32768,-32768` / `Second: 32767,32767,32767`.
- Vanilla `EquipmentType` FormIDs in `Skyrim.esm`, MEASURED by reading the EQUP group: `013F42` RightHand, `013F43`
  LeftHand, `013F44` EitherHand, `013F45` BothHands, `0141E8` Shield, `025BEE` Voice, `035698` Potion. MEASURED over
  every WEAP: one-handed swords, daggers, axes and maces use RightHand (1,213 of 1,258; 42 EitherHand, 3 BothHands);
  greatswords, battleaxes and bows use BothHands (1,137 of 1,137). Copy the EquipmentType of a vanilla weapon of the
  same kind.
- `Weapon.SetReach(float)` is respected independently of the mesh, but **only from a game restart** — during gameplay
  the value changes and hit detection does not. There is no documented upper cap. Vanilla reach is
  `141 (fCombatDistance) × NPCScale × WeaponReach`: 10.0 ≈ 1410 units ≈ 21 m, 30.0 ≈ 4230 units ≈ 63 m,
  50.0 ≈ 7050 units ≈ 106 m.
- `Weapon.SetModelPath()` does not update an equipped weapon's visual; even unequip → set → re-equip shows the same
  mesh. `Weapon.SetEquippedModel()` is native SKSE and was **DESTRUCTIVE in VR** — no visual change, then the weapon
  disappears from the hand and is only recoverable by unequipping and re-equipping. Do not use it. (Both MEASURED in VR
  by the source's author; treat as "don't" on any runtime.)
- `AnimationType: Staff` **is required for hold-to-fire**. With `OneHandSword` plus a staff keyword and staff
  enchantment, the engine never triggers hold-attack-to-cast.
- `AnimationType: Staff` on a sword mesh renders the blade **inverted**: the staff skeleton orients the weapon bone
  differently. The fix is a 180° rotation around **Y** on the child geometry nodes (Z or X only spins the blade about
  its own axis). Grip offset comes from the skeleton bones: `WeaponSword` ≈ (-11.89, +1.92, +6.67) and `WeaponStaff`
  ≈ (0.00, -10.08, +2.47), which is why a staff grip feels further back and more centred. A root translation to
  compensate has little effect in VR — the IK grip system owns hand-to-weapon placement.
- `WNAM` (first-person model) changes what is rendered **in the hand** when IK attaches the third-person model:
  pointing `WNAM` at a STAT that wraps a different NIF redirects the in-hand mesh to that NIF, and it wins over editing
  the third-person model when both are set. The inventory icon viewport also follows `WNAM` — with `WNAM` null the icon
  renders blank, and the icon is the STAT's NIF. MEASURED in VR by the source's author.
- The engine does **not** derive `1stperson<name>.nif` for custom directories; that convention only works inside
  recognised vanilla paths.
- A staff whose mesh physically contacts an enemy in melee **auto-fires the concentration enchantment** without the
  trigger being pressed. Script-side fix has a one-frame flash (check the trigger in `OnEffectStart`, dispel if not
  pressed); the engine-level fix is to strip the enchantment from the weapon form on release and restore it on press.
  Both confirmed working in VR by the source's author.

## Navmesh, cleaning, strings, masters

- Navmesh **creation** is Creation Kit only; edit tools can delete a navmesh but not recreate it. Navmesh data is
  zlib-compressed and some older plugins lose data when processing it. Adding too many objects to a cell with
  ESP-stored navmesh causes crash-on-exit (ESM navmesh is fine). Never "fix" deleted navmeshes inside official masters —
  they are intentional.
- **Not all ITMs are errors** — keyword injections and compatibility patches contain intentional ones. **Deleted
  references (UDR)** are a primary crash cause and should be undeleted and disabled — unless the mod's whole purpose is
  deleting that thing, in which case cleaning breaks it. Always review before saving after a clean.
- Strings: **STRINGS** = item, actor, race, location names and quest objectives; **ILSTRINGS** = dialogue subtitles and
  voice lines; **DLSTRINGS** = book body text and quest descriptions. A missing string file is blank text in game, and
  edit tools neither validate nor generate them.
- Removing a master that is still used leaves broken FormIDs with no recovery. "Clean Masters" only removes masters
  nothing references; removing one by hand means updating every referencing FormID and is extremely error-prone.

## Creation Kit bugs worth knowing

- The CK does **not** set the 0x8 ESM flag when converting a file to master type; correct it by hand.
- The CK can appear to save successfully while the plugin disappears or is corrupted.
- On load the CK removes null records, which can silently corrupt data.
- The CK rejects ESP files as masters (other tools allow it) and deletes the ESP master references, leaving orphaned
  records.
- LE→SSE porting loses data across form version 43→44 (critical-hit data on weapons among it).

## Papyrus fragments

- Fragments live inline in VMAD subrecords and are fragile to corruption.
- Fragment code must carry all its own function and event declarations; declaring properties inside a fragment can
  cause compiler errors that block every further edit.
- Workaround for a stubborn fragment: add an empty fragment, close the quest window, reopen, edit the code, then assign
  properties through the Properties button.
- The CK validates fragments on save; an edit tool does not, so fragments edited outside the CK must be resaved in it.

## Reading plugins without the record API

When the `housecarl_*` record tools are not loaded, `scripts\esp\espscan.py` prints **raw subrecords**: strings and
FormIDs a plugin contains, and the subrecords of one record. That is enough to answer "is this EditorID here", "which
plugin mentions this FormID", "what does this subrecord hold" — and not enough to answer "what does this record resolve
to" in a load order, which needs the override chain (troubleshooting skill). A `.pex` can be disassembled with
`scripts\esp\pexdis.py` instead of being decompiled.

- **A record viewer that shows only EditorID and record type is telling you about itself, not about the record.** Some
  viewers return an empty property list for MGEF and SNDR records. The fields are there; read them with a raw subrecord
  reader, a text round trip, or the record API — and do not report "the record has no properties".

## External tools: facts about xelib / xEdit-style libraries

Nothing in this repo installs or requires them; these are the traps a script hits when one is used.

- Game mode for both Skyrim SE and Skyrim VR is `GM_SSE` (4). The library reads the registry from the
  **Skyrim Special Edition** key, not a VR key.
- **`setFormID` and the master-count high byte.** The "local" FormID a record the plugin *owns* reports is
  **master-count-prefixed**, not the bare lower three bytes: a plugin with 4 masters owns records that look like
  `0x040008XX`. Passing a bare `0x8B3` sets the high byte to `0x00`, which the engine reads as an **override of
  `Skyrim.esm` form `0x0008B3`** — a silently corrupt record, and two plugins doing it collide. `GetFormFromFile`
  matches the lower three bytes, so it can appear to half-work.

```js
const n = xelib.getMasterNames(file).length;      // e.g. 4
const localFid = (n << 24) | 0x0008B3;            // 0x040008B3
const copy = xelib.copyElement(srcRecord, file, true);
xelib.setFormID(copy, localFid, true, false);     // local = true, fixRefs = false
```

- **Nested element paths fail confusingly.** `getValue(record, 'PARENT\\Child')` errors when the target does not exist
  at the first level ("Expected 2 arguments, got 1" from the FFI layer). Navigate in two steps: get the outer element,
  get the inner element, then call the path functions on the element handle with an empty path (`''`).
- **`setGamePath` wants a trailing separator, and the error appears one call later.** Give it a path without a
  separator and `setGamePath` returns success; the next call, `setGameMode`, fails with `SetGameMode failed` — naming
  the wrong function. It only bites when the path is set *before* the mode, which is why the same bad path looks
  harmless in one script and fatal in another. Deriving the path makes this easy to get wrong, because resolving a path
  never returns a trailing separator; check both separator styles before appending one.
- The same class of trap applies to any tool that finds the game through the registry instead of an explicit path: on a
  managed install it sees the wrong `Data/` and returns a plausible wrong answer (troubleshooting skill,
  *conflicts and paths*).

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
