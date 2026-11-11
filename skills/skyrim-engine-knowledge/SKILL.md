---
name: skyrim-engine-knowledge
description: >-
  Skyrim engine knowledge learned by debugging: Papyrus runtime behaviour, record and plugin structure, what a change
  costs on an existing save, vanilla engine quirks, VR-only differences, NIF/audio format traps, and a porting
  checklist for getting an SE mod onto VR. Load it when the question is "how does the engine actually behave" or
  "why did this work on paper and fail in game" — script timing, a spell that fires on some targets, an invisible
  weapon, a light plugin that will not load, an update that is or is not safe on a live save, a mesh that crashes.
  Not for live reads of a load order (skill skyrim-troubleshooting), not function signatures (papyrus-reference),
  not record schema (mutagen-reference), not compiling (papyrus-compiler), not SKSE C++ (skse-plugin-authoring).
compatibility: >-
  None. The references are static knowledge and the lookups they name are offline. Anything that reads this machine's
  live load order, save or logs lives in skyrim-troubleshooting.
---

# Skyrim engine knowledge

Hard-won facts about how Skyrim SE 1.5.97 / AE (first) and Skyrim VR (second, in its own files) actually behave. Every
line is meant to be a fact or a labelled claim; nothing here is a general programming tutorial.

**The rule for this file and its references:** a fact is only worth what its evidence is. Each claim carries one of
these when the difference matters:

- **MEASURED** — observed on one install, with the date the source records. True there, not necessarily everywhere.
- **READ** — read out of a wiki, a record, a decompiled script or a changelog.
- **INFERRED** — a conclusion nobody checked.
- **UNSOURCED** — community claim, not checked here.

Never promote an INFERRED or UNSOURCED claim to fact in a report, a code comment or a patch description. When the
question is about this machine's install, the live check wins over any entry here.

## Route the question

| Question | File | Read it for |
|---|---|---|
| Why did my script fire twice / not at all / late? What does `Wait` really do? Which event fires when? | [references/papyrus-runtime.md](references/papyrus-runtime.md) | lifecycle, threading and budget, `Wait`, updates, states, magic-effect start/finish, ability vs spell, null guards, performance, conditions, NaN, VM memory, real-time detection limits |
| What is wrong with this record or plugin? Which ID range may a light plugin use? Does this field really do that? | [references/records-and-plugins.md](references/records-and-plugins.md) | VMAD, ONAM, temporary references, ESM/ESP/ESL ranges, override resolution, archives, spell area in feet, explosion flags, WEAP fields, navmesh, cleaning, strings, masters, the Creation Kit's bugs and fragments |
| How do I author or diff a plugin as text without corrupting it? | [references/esp-yaml-and-spriggit.md](references/esp-yaml-and-spriggit.md) | YAML round trips, header and metadata contract, CLI semantics, silent field drops, the canonical reorder, bulk-remap hazards, sound and weapon record templates |
| Is this update / removal safe on the save I am playing? | [references/save-safety.md](references/save-safety.md) | why plugin removal is unsupported and what a lobotomy is, the full update rubric (one row per kind of change), the DLL gate, adding a mod, the per-session routine |
| The engine did something odd and no record explains it | [references/engine-quirks.md](references/engine-quirks.md) | vanilla bugs, native-over-script patterns, stagger and bleed the way vanilla does it, ImageSpace, abilities, Papyrus INI keys, MCM-Helper-vs-SKSE-INI, version-sensitive plugin traps, live-game probing |
| Anything VR | [references/vr-differences.md](references/vr-differences.md) | separate build, SKSEVR, skeleton and animation, camera, UI, weather, INIs VR really reads, physics, playroom, runtime stack, framework VR status, breakage categories |
| VR scripts, controller input, weapon reach, hit detection | [references/vr-papyrus-and-input.md](references/vr-papyrus-and-input.md) | player control and immobilising, moving the player, the VRIK input API, weapons at runtime, `OL_WEAPON` damage routing, PLANCK, VR testing protocol |
| A mesh or a sound is broken, or a tool made it worse | [references/nif-and-audio.md](references/nif-and-audio.md) | PyFFI vs PyNifly limits, NifSkope damage, validation gates, blade stretching, Havok units, skeleton CTDs, SNDR/SOUN, WAV/XWM/FUZ, music records and ducking |
| Get this SSE mod running on VR | [references/porting-to-vr.md](references/porting-to-vr.md) | the eight-step porting checklist and the report to hand back |

## What this skill does not answer

- **Live load order, conflicts, logs, saves** → `skyrim-troubleshooting`. This skill says what a symptom *means*; that
  one says which tool to point at it.
- **Function, event and property signatures** → `papyrus-reference` (offline corpus, and the "never invent a signature"
  rule). Its silent-biters file covers the compile-clean, runtime-wrong cases in signature form.
- **Record schema**: field names, types, cardinality, enum values → `mutagen-reference`. This skill says which fields
  behave counter-intuitively.
- **Compiling `.psc`** → `papyrus-compiler`.
- **Writing or auditing an SKSE DLL** → `skse-plugin-authoring`.
- **Crash addresses, REL::IDs, thread snapshots, Ghidra** → `skyrim-reverse-engineering`.

## Ten that fail silently

Each is a whole debugging round. The file after the dash has the mechanism.

1. `RemoveSpell` does not fire `OnEffectFinish`; `DispelSpell` does but silently excludes abilities — [papyrus-runtime](references/papyrus-runtime.md).
2. All effects on one spell must share a casting type, or the spell never fires — [papyrus-runtime](references/papyrus-runtime.md).
3. A non-auto property stays blank after save/load, so the value in the plugin never reaches the actor — [papyrus-runtime](references/papyrus-runtime.md).
4. An unguarded `Math.Acos`/`Asin` on NaN errors every tick and can degrade the VM into a freeze — [papyrus-runtime](references/papyrus-runtime.md).
5. `GetActorValue("IsBlocking")` is not an actor value; it errors every call — [papyrus-runtime](references/papyrus-runtime.md).
6. A soft `GetFormFromFile` dependency on another mod returns `None` the day that mod is disabled — copy the record — [papyrus-runtime](references/papyrus-runtime.md).
7. A reused vanilla magic effect carries gating Conditions, so it fires on some targets and not others — [records-and-plugins](references/records-and-plugins.md).
8. Weapon `BasicStats` and `Data` are different sections: swapping them gives an invisible weapon — [records-and-plugins](references/records-and-plugins.md).
9. Spell effect `Area` is in **feet**, not game units — `Area=60` is an 18 m radius — [records-and-plugins](references/records-and-plugins.md).
10. A light plugin's new records below object ID `0x800` depend on the runtime and the header version, not on a rule — [records-and-plugins](references/records-and-plugins.md).

Two more that are not silent, only expensive: a crash log written as `.LOG` beside old `.txt` dumps (the triage
reference in `skyrim-troubleshooting`), and a recompiled `.pex` that only loads at game startup (same skill).

## Platform order

1. **SE 1.5.97** — the reference runtime for every non-VR statement here.
2. **AE 1.6.x** — the same non-VR statements, minus the reverse-engineering addresses, and with the light-plugin
   header-1.71 behaviour.
3. **VR** — a separate engine build. If a statement does not say VR and is in a non-VR file, assume it does not apply.
   Conversely, nothing in the two VR files applies to SE or AE.

## Reading the references

- Read the file whole for the topic; they are topic files, not answers to one question.
- A fact that names a version, a plugin build or a measured date is time-stamped on purpose. Re-check it before acting;
  the *mechanism* next to it is the durable part.
- When a reference names a third-party plugin, an external tool or a command, it says so. This repo installs none of
  them, and a claim about one is about a build the source's author had.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
