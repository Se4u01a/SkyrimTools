# NIF meshes and audio: format knowledge and traps

What the file formats do, and which tool can safely touch which. The tool catalogue itself (which editor is installed,
where) is `skyrim-local-toolbox`; this file is the format knowledge. Record authoring is
[esp-yaml-and-spriggit.md](esp-yaml-and-spriggit.md); record fields are [records-and-plugins.md](records-and-plugins.md).

## NIF: two Python libraries with disjoint capabilities

### PyFFI — LE-format `NiTriShape` geometry only

- **It cannot read `BSTriShape` at all** (`Unknown block type 'BSTriShape'`), which is every SSE-format
  (`user_version_2=100`) NIF.
- **Never author animation controllers with it.** It can construct `NiControllerManager`/`NiControllerSequence` blocks
  and its own readback passes, but the written NIF **crashes to desktop the instant it is placed**, because it omits
  header string-table registrations the engine requires. Confirmed in game: a PyFFI-authored `SpecialIdle` spinner
  CTD'd on `placeatme` despite a clean PyFFI readback.
- Building from a **fresh empty `NifFormat.Data()`** corrupts the header on write. Always load an existing valid NIF and
  restructure it.
- So PyFFI stays useful for LE-format `NiTriShape` geometry edits: vertex shifts, bounds, collision dimensions,
  transform values, and a mesh split/subdivision.
- **It does not need a dedicated Python 3.10.** The only real version blocker is one unconditional
  `from distutils.cmd import Command` in an unused helper, and `distutils` was removed from the standard library in
  3.12; installing `setuptools` beside it fixes that, because setuptools ships a vendored `distutils` and an import
  shim (the official migration path). Verified end to end on Python 3.14. The separate `time.clock` monkey-patch
  (`time.clock = time.perf_counter`) is unrelated and required on every interpreter, because `time.clock` was removed
  in Python 3.8.

### PyNifly — SSE `BSTriShape` and all animation/controller authoring

- It wraps the nifly library (the engine behind BodySlide/Outfit Studio), reads and writes SSE including
  `BSTriShape`, and has correct `.New()` factories for `NiControllerManager`, `NiControllerSequence`,
  `NiMultiTargetTransformController`, `NiTransformData`, `NiTransformInterpolator`, `NiDefaultAVObjectPalette`,
  `BSXFlags` and `NiTextKeyExtraData`. Those factories are what register the header strings PyFFI botches.
- That is what makes self-spinning, telescoping and keyframe-animated effect meshes possible: a
  `NiControllerSequence` named `SpecialIdle` **auto-loops on a placed activator with zero scripting**.
- Verified on version 27.2.0: importing it as a package (`from pyn import pynifly`) after putting the add-on folder on
  `sys.path` loads its bundled `NiflyDLL.dll` itself; the DLL actually loaded is `io_scene_nifly/NiflyDLL.dll`, not the
  copy under `pyn/`. An animation round trip authored byte-identical controller stacks on 27.2.0 and 29.1.0.
- One version's Blender add-on (29.1.0) strips `BSEffectShaderProperty` on an import/export round trip when the diffuse
  texture is not on disk.
- **Never round-trip an animated NIF through Blender** (import → export): the add-on drops the animation controllers
  (Blender has no animation export for them). Repair animated NIFs with the library directly.
- A Blender round trip shares the nifly library, so Blender is **not** an independent parser.

### NifSkope

- It is the independent **visual** validator, and it also converts a NIF to the SSE stream version on save. That
  conversion can strip texture slots and change the shader-property structure, which then crashes setups using a
  shader suite or PBR in VR. A scripted library edit avoids this entirely.
- It cannot show what a headless render cannot; and a collision-block inspection needs a GUI (see below).

## A library save can change what you did not touch

MEASURED on one install: saving with the default optimisation changed a particle light's **bounds** in a mesh whose
collision was being replaced; a strict before/after visual comparison caught it. Preserving the original took an
explicit `SetBounds` with the original values and `Save(optimize=false, sortBlocks=false)`.

**Collision triangle count can cause a local stutter.** On that install a replacement brazier mesh whose collision had
2,120 triangles stuttered near it; a loose override with a 76-triangle collision aligned to the original bounds fixed it
(user-confirmed A/B, not a measured FPS delta). A high triangle count alone does not prove a mesh causes stutter; a
hitch-reporting tool that names the blocking thread separates a main-thread stall from a runtime wait.

## Validate before the game sees the file

A crash-to-desktop must be caught in tooling, not in the headset. Three independent gates, in order:

1. **Author with a valid-by-construction tool** (PyNifly, not hand-rolled PyFFI blocks).
2. **Cross-validate with an independent, stricter parser** (PyNifly) — and check the **specific crashable subsystem**
   (the controller, the shader block), because a geometry-only read passes while the animation stack is malformed.
3. **Diff against a known-good structure**, and render to an image so a mesh or glow fix can be confirmed without
   launching the game.

The miss that taught this: a PyFFI-authored NIF was "verified" by reading it back **with PyFFI** — the same buggy tool,
so self-consistent did not mean engine-valid. Cathedral Assets Optimizer-style "optimisers" were not adopted as a gate
either: they mutate LE meshes toward the SSE format, which is the opposite of what a read-only gate needs.

## Editing geometry: stretching a blade

- Matrix-stretching a sparse low-poly blade by a large factor tears it into invisible slivers, and the worst offenders
  are the thin cutting-edge triangles, which taper to ~0 area.
- Fix 1: **subdivide** first (midpoint subdivision, crack-free through a shared edge-midpoint dict) so the stretch
  spreads over many short segments instead of a few long ones.
- Fix 2: keep the split threshold on a **UV or material boundary** — pulling geometry whose UVs map to a different
  texture region (a gold guard vs a steel blade) into the stretch smears and tears that region.
- Thicken the thin dimension (~×2) so the edge bevel has body.

## Collision blocks, units and skeletons

- **1 Havok unit ≈ 70 game units**, and it applies to `bhk*` collision blocks only (`bhkBoxShape` dimensions,
  `bhkConvexTransformShape` translations, capsule lengths). A ~5,000-game-unit shape is ~71 Havok units; get this wrong
  and the collision geometry lands far from the visual mesh.
- Many NIF tools (a texture/string/shader editor, a record inspector's NIF module) **cannot inspect `bhk*` collision**.
  Collision inspection needs NifSkope or a purpose-built parser; the useful operations from a script are
  `block.dimensions.y` on a `bhkBoxShape`, `block.transform.m_42` on a `bhkConvexTransformShape`, and `block.shape` for
  the child of a convex transform.
- **`PreWEAPON` and `PreSHIELD` skeleton nodes crash Skyrim VR** (a text-contains search for WEAPON/SHIELD nodes is
  confused by the prefix). Remove them, or rename to drop the prefix. See [vr-differences.md](vr-differences.md).
- **Orphaned extended skeletons cause a Havok contact-solver CTD.** A partially uninstalled creature mod can leave
  extended `skeleton.nif` files in `Data/meshes/actors/<creature>/character assets/` after its plugin, physics
  configurations and framework are gone. The extended ragdoll/collision (`bhkRagdollConstraint`, `bhkRigidBody`,
  `bhkCapsuleShape`) then faults the solver: an `EXCEPTION_ACCESS_VIOLATION` in the physics path
  (`hkpConstraintInstance` / `hkpRigidBody` / `hkpSimulationIsland`) while the creature touches world geometry,
  independent of combat. Fix: restore the **vanilla** `skeleton.nif` for that creature (extract it from the game's
  mesh archive).

## Sound records: SNDR vs SOUN

- **SNDR** (sound descriptor) stores the audio file paths, output model and category. A script cannot play it.
- **SOUN** (sound marker) is a thin wrapper referencing one SNDR, and that is what the Papyrus `Sound` type is.
- `GetFormFromFile(id, "plugin.esp") as Sound` returns `None` **silently** when the ID is a SNDR: no log line, no
  sound. Every playable sound therefore needs two records, and the script uses the SOUN's FormID. The YAML layout for
  both records is in [esp-yaml-and-spriggit.md](esp-yaml-and-spriggit.md).
- Output model for scripted action SFX: `000EC7:Skyrim.esm` (a stereo radius 09000 voice/shout model). Do **not** use
  `0FD93D:Skyrim.esm`, which is for ambient environmental emitters.
- Audio category for action SFX: `0172A1:Skyrim.esm` (`AudioCategorySFX`), not `01A0BD:Skyrim.esm`
  (`AudioCategoryMAG`, magic effects).
- WAV that will be played positionally on an object (`Sound.Play(objectRef)`) should be **mono** — stereo may not
  position correctly in 3D. The format the source used: 44,100 Hz, 16-bit PCM.
- A SNDR pointing at a **missing** `.xwm` plays silence and does not crash, so files can be added later.

## Audio files: WAV, XWM, FUZ

- Skyrim voice files are `.fuz` containers holding an **XWM** (the compressed audio) and a **LIP** (lip-sync data for
  facial animation). Replacing a voice line means WAV → XWM → FUZ, with a matching LIP when lip-sync matters.
- The WAV→XWM encoder accepts **only 1, 2 or 6 channels** and PCM input; a multichannel source (e.g. a 7.1.4 WAV) fails
  with an unsupported-channels error. Normalise first, then encode:

```bash
ffmpeg -y -i "in.wav" -acodec pcm_s16le -ar 44100 -ac 2 "_pcm.wav"
xWMAEncode.exe "_pcm.wav" "Data/Sound/FX/.../out.xwm"
```

- An archive tool that can list a BSA/BA2 index natively may still need a separate external tool for create/extract/
  repack, and that tool may refuse an output folder that does not exist yet ("Folder does not exist") — create it first.

## Music: MUSC vs MUST

- **MUSC** = music **type container**: what the music manager tracks on its priority stack. It carries FNAM flags, PNAM
  (priority + ducking dB), WNAM fade duration and TNAM (the track list). The Papyrus `MusicType` form type maps to MUSC.
- **MUST** = music **track**: an individual audio entry, referenced from MUSC's TNAM. Tracks are **not** on the priority
  stack, so asking the manager for a MUST's status always reports -1. Always pass the MUSC container.
- Key vanilla MUSC records: `MUSCombat 0x0003418E`, `MUSCombatBoss 0x000D777A`, `MUSExploreMountain 0x000B9DCE`.

FNAM flags on MUSC: bit 0 `0x01` Plays One Selection, bit 1 `0x02` **Abrupt Transition** (switch immediately instead of
waiting for the current track to end), bit 2 `0x04` Cycle Tracks, bit 3 `0x08` Maintain Track Order, bit 5 `0x20`
DucksCurrentTrack.

- Vanilla `MUSCombat` is `0x09` (PlaysOneSelection + MaintainTrackOrder). Without Abrupt Transition the engine queues
  combat music and waits for the current exploration track to finish; with exploration tracks of 60-120+ s and no cue
  points, a short fight ends before combat music ever fires.
- One large music overhaul overrides `MUSCombat` to `0x24` (CycleTracks + DucksCurrentTrack) on purpose: its 88 combat
  tracks need CycleTracks to cycle the pool. **Removing CycleTracks makes the engine fail to play any track and leaves
  the manager deadlocked** — MUSCombat never becomes Playing, the exploration track is cut by AbruptTransition, and the
  result is total silence. Preserve that mod's flags when patching MUSCombat; adding AbruptTransition on top gives
  `0x26`. The flag names to write are in [esp-yaml-and-spriggit.md](esp-yaml-and-spriggit.md).
- **`MusicType.Add()` from Papyrus bypasses engine ducking.** The engine's native trigger applies PNAM ducking (a
  combat type with ducking 100 dB makes exploration music inaudible); a scripted `Add()` leaves the exploration track
  audibly layered underneath. Any scripted "force combat music" workaround produces the "two tracks at once" symptom.
  Rely on the engine's own combat trigger.
- **Stacking pattern to recognise:** a boss-music plugin whose scripted actors each call `Add()` on combat entry at the
  same priority, with `Remove()` only on `OnDying`. Several boss-tagged actors in one fight stack entries, escaped or
  despawned actors leak theirs, and the stack corrupts the manager until combat music stops firing in later encounters.
  Diagnosing it: the boss container and the combat container both reporting "playing" at the same time confirms it.
- **A "combat music fix" DLL that hooks actor death and asks `IsInCombat()` can break multi-enemy fights**: in the
  window after one kill and before the next target, `IsInCombat()` reads false, so it force-terminates music while the
  fight continues. Observed stopping combat music 3-4 s in; keep it disabled. (A named plugin on one install — verify
  before applying, the shape of the bug is what matters.)

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
