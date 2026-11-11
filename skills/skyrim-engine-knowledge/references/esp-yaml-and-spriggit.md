# Authoring a plugin as text (YAML round-trips)

Some plugins can be serialized to one YAML file per record, edited as text, and deserialized back. The tool that does
it (Spriggit) is an **external tool that SkyrimTools does not install or ship**; everything here is what the format and
the round trip do, so a diff can be read and a failure recognised. Record field meanings are
[records-and-plugins.md](records-and-plugins.md); schema is `mutagen-reference`.

## Why round-trip at all

- It is the readable form of a plugin: a reviewable diff instead of binary bytes.
- It works **outside a mod manager**, because serializing a single plugin by path never consults the load order. On an
  MO2 install that is the main reason to prefer it for single-plugin work (the load-order trap is in the troubleshooting
  skill, *conflicts and paths*).
- It is the strongest verification of a plugin edit: a full before/after YAML diff catches silently dropped fields as
  well as wrong references. A reference-only check does not.

## Header and directory contract

- The **plugin header version must be 1.7** for SSE/VR. Version 1.0 is flagged as Oldrim/wrong game by tooling.
  In YAML this is `ModHeader: Stats: Version: 1.7`.
- Deserialization needs a `spriggit-meta.json` in the root of the YAML directory:

```json
{"PackageName": "Spriggit.Yaml.Skyrim", "Version": "0.41.0", "Release": "SkyrimSE", "ModKey": "YourMod.esp"}
```

- Records live in typed folders as one file each, named `<EditorID> - <FormID>_<Plugin>.yaml`: SNDR →
  `SoundDescriptors/`, SOUN → `SoundMarkers/`, and so on. Adding a record means cloning an existing file of the same
  type in the same folder.

## Command-line semantics

- `serialize --InputPath <plugin> --OutputPath <dir> --GameRelease SkyrimSE --PackageName Spriggit.Yaml
  --PackageVersion <installed version>`.
- `--GameRelease` is **only** for serialize, never for deserialize. `--PackageVersion` is **required** whenever
  `--PackageName` (and/or `--GameRelease`) is set, or the tool refuses with "PackageVersion needs to be set".
- Pass the version the tool actually reports, not a remembered number.
- Use `-u` / `--ErrorOnUnknown` on serialize: it makes an unknown field or record an error instead of a silent drop.
  Make it the default.
- **`spriggit --version` exits 1 even when it works** (MEASURED on 0.41.0, globally installed and through a local tool
  runner alike): it prints the version lines, then returns 1. Probe it by its **output**, never by its exit status, and
  not with `| grep -q` under a shell that treats SIGPIPE as failure — grep closing the pipe early fails the pipeline.
- A recorded pin (0.41.0 at the time of the source) exists only so drift is noticed; the version in use is what the
  output has to be judged against.

## What a round trip does to the bytes

- **A controlled no-op round trip can be byte-identical** (MEASURED 2026-05-18: serialize → deserialize unchanged →
  serialize produced a byte-for-byte identical plugin, with `:Skyrim.esm` references intact).
- **The bytes are only stable once the tool has written the file itself.** MEASURED 2026-10-05 on a 1,549-byte plugin
  another tool had written (8 STAT records): one serialize → deserialize gave the same size but **1,247 of 1,549 bytes
  different**, because records come out in a different order. Re-serializing produced YAML identical to the first
  serialize (10 of 10 files), and a second deserialize reproduced the first output byte for byte — so the first pass
  **canonicalises the order** and the result is a fixed point.
- Therefore: **prove a round trip by re-serializing and diffing the YAML. An ESP byte-compare fails on correct
  output.**
- A round trip also rewrites the **order of a script's VMAD properties** (MEASURED on one plugin: property order
  changed and nothing else in that record). A byte comparison then reports a difference that is not a change; compare
  the properties (names, types, values).
- The older belief that this format "corrupts master prefixes on round-trip" was a **misdiagnosis**. The real cause of
  a re-mastered reference (`:Skyrim.esm` → `:YourMod.esp`) is an **over-broad ModKey remap during a manual mod split** —
  a blanket plugin-name replace that sweeps up legitimate field references.

## Silent drop of unknown fields

- If a YAML field name does not match a known property, deserialization **drops the data with zero error, zero warning,
  zero log line**, returns success, and the resulting plugin simply lacks the field. The plugin then loads in game and
  the feature tied to that field is missing — hours of misdiagnosis.
- Mandatory verification for every **new** field you write:

1. edit the YAML and deserialize to a temporary plugin;
2. re-serialize that plugin back to YAML;
3. grep the re-serialized YAML for the field you just wrote;
4. absent → the field name is wrong or does not exist for that record type. Try alternates.

- Finding the right property name: xEdit's display name often diverges from the schema's property name, so verify
  against the schema (`mutagen-reference`), never against a record editor's column label.
- Known name trap: MGEF's impact data set link is **`ImpactData`**, not `ImpactDataSet`, even though the linked record
  type is IPDS. Discovered while cloning an MGEF.

## Bulk reference remaps are the real hazard

- Bulk ModKey/master remaps (a mod split, a find-replace over YAML) are what actually corrupt references. The round
  trip itself is trustworthy; the blanket rename is not.
- **Standing practice:** inventory cross-references (every FormID plus its target master, per field) before and after
  any bulk plugin operation, and diff the two. A change you intend is accepted as the new baseline; anything else is a
  bug.
- Verify every plugin edit with a full before/after YAML diff, not a reference-only check, because only the full diff
  also catches silently dropped fields.

## Write paths

When a generated YAML tree and the tool that reads it are driven from different tools, give **both** the same explicit
absolute path. A relative `/tmp` style path can resolve to two different locations, and then the new records silently
never deserialize — the tool reads an empty or stale directory and reports success. One directory, one absolute path,
read back before deserializing.

## A minimal WEAP record (visible weapon)

`BasicStats` and `Data` are different sections; swapping them yields an invisible weapon. The `Data` block's
`Unused`/`Unknown2`/`Unknown3` fields are always present in working records — omitting them breaks the record.

```yaml
FormKey: XXXXXX:Mod.esp
EditorID: MyWeapon
ObjectBounds:
  First: -32768, -32768, -32768
  Second: 32767, 32767, 32767
Name:
  TargetLanguage: English
  Value: My Weapon
Model:
  File: weapons\path\to\mesh.nif
  Data: 0x020000000000000000000000
EquipmentType: 013F42:Skyrim.esm
Keywords:
- 01E711:Skyrim.esm
Description:
  TargetLanguage: English
  Value: ''
ImpactDataSet: 013CAC:Skyrim.esm
BasicStats:
  Value: 100
  Weight: 5.0
  Damage: 12
Data:
  AnimationType: OneHandSword
  Unused: 0x000000
  Speed: 1.0
  Reach: 1.0
  Flags: []
  NumProjectiles: 1
  AnimationAttackMult: 1
  Unknown2: 1061997773
  Unknown3: 0x000000000000000000000000
  Skill: OneHanded
  Stagger: 0.5
Critical:
  Damage: 1
  PercentMult: 10
  Flags: []
  Unused2: 0x000000
DetectionSoundLevel: Normal
```

- `Critical.Flags: [OnDeath]` was rejected by the parser in the source's testing while `Flags: []` worked; `OnDeath`
  is valid elsewhere but not in the critical-data flag enum. Use `[]`.
- `Model.Data: 0x020000000000000000000000` is the MODT subrecord present in every working record.
- `EquipmentType` and the RightHand/BothHands split per weapon kind are in
  [records-and-plugins.md](records-and-plugins.md).

## Sound records: every playable sound is two records

- **SNDR** (sound descriptor) holds the WAV/XWM paths, output model and category; it **cannot** be played from a
  script.
- **SOUN** (sound marker) is a thin wrapper referencing one SNDR. The Papyrus `Sound` type **is** SOUN.
- So a script needs the **SOUN** FormID. `GetFormFromFile(id, "plugin.esp") as Sound` silently returns `None` when the
  ID points at the SNDR — no log line, total silence.

```yaml
# SoundMarkers/MySoundMarker - 00085E_YourMod.esp.yaml
FormKey: 00085E:YourMod.esp
EditorID: MySoundMarker
SoundDescriptor: 000857:YourMod.esp
```

- Adding one: serialize, clone an existing SNDR (`SoundFiles: [FX\...\file.xwm]`) and SOUN (point `SoundDescriptor` at
  the new SNDR), keep them in `SoundDescriptors/` and `SoundMarkers/`, deserialize.
- Output model and audio category for scripted action SFX, WAV format and the WAV→XWM pipeline:
  [nif-and-audio.md](nif-and-audio.md).

## Music records: FNAM flags are edited in YAML, not by value

The MUSC/MUST distinction and the flag meanings are in [nif-and-audio.md](nif-and-audio.md); the *editing* rule is
here:

- Correct flag names in a YAML `Flags` list: `PlaysOneSelection`, `AbruptTransition`, `CycleTracks`,
  `MaintainTrackOrder`, `DucksCurrentTrack` (0x20).
- **Do not set a MUSC flag through a path-based tool with a binary string** — xelib's `setValue` wrote `0x34` where
  `0x0B` was intended, with no error (MEASURED). Use the YAML round trip for FNAM edits.

```yaml
Flags:
- AbruptTransition
- CycleTracks
- DucksCurrentTrack
```

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
