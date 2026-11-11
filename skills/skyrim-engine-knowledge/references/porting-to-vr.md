# Porting an SSE mod to VR: the checklist

A guided pass over one mod against every known VR incompatibility. Each item names the file that explains it; do not
re-derive the explanation here. **This is a porting procedure, not a review gate** — the review procedure is in the
troubleshooting skill.

## Step 1 — SKSE dependency

- Does the mod require SKSE64? Then it needs an SKSEVR or multi-runtime equivalent, or it cannot run.
- Look for an Address Library dependency: the VR Address Library is a different file with different IDs, and a DLL built
  against the SE IDs will not resolve.
- Find every DLL in the mod (`Data/SKSE/Plugins/*.dll`) and ask which runtime it was compiled against. A
  CommonLibSSE-NG build that declares VR covers all of them in one file.
- A page that claims VR support is provisional until the DLL loads and the SKSE log says so — see the troubleshooting
  skill's *SKSE DLLs* reference. `openvr` strings inside a DLL prove nothing.

## Step 2 — Papyrus script audit

Decompile every `.pex` (or read the shipped `.psc`) and check for:

- [ ] `PlayIdle()` on the player — unreliable in VR: IK overrides the upper-body skeleton, and even a fired idle fights
      the pose. Bypass the animation with timed script steps.
- [ ] `DisablePlayerControls()` **alone** — does not stop thumbstick movement. Add `SetDontMove(true)`.
- [ ] `SetVehicle()` — HMD desync. Remove it.
- [ ] `ForceThirdPerson()` / `ForceFirstPerson()` — cannot control the VR camera.
- [ ] `Input.GetMappedKey()` / the SKSE input API — returns -1 for VR controllers. Use the VRIK globals.
- [ ] `Game.ShakeCamera()` — mostly inert in VR; leave it in and document it.
- [ ] `SetAngle()` on the player — does not control HMD orientation.
- [ ] `Utility.Wait()` under 100 ms in a sequencing chain — unreliable; merge the gaps.
- [ ] `Cell.GetNthRef()` for live actor detection — unreliable; use a processing-level query.
- [ ] Any dependency on a script that does not exist on VR (e.g. a target-selection framework) — the script name does
      not resolve and the feature silently does nothing.

Detail: [papyrus-runtime.md](papyrus-runtime.md) and [vr-papyrus-and-input.md](vr-papyrus-and-input.md).

## Step 3 — Skeleton

- [ ] Custom skeleton nodes: **`PreWEAPON` and `PreSHIELD` crash VR.** Remove them.
- [ ] A custom skeleton needs the "XP32 First Person Skeleton CTD Bugfix" equivalent for VR.
- [ ] `.hkx` behaviour files work, but test them with the IK overlay active.

Detail: [vr-differences.md](vr-differences.md), mesh side in [nif-and-audio.md](nif-and-audio.md).

## Step 4 — Physics and combat

- [ ] Havok tuned for 60 Hz? VR runs at 90 and the default Havok rate is 60, so the physics rate needs the INI tweak.
- [ ] Collision assumptions: VR is player capsule vs **enemy ragdoll**, and the player capsule is narrower.
- [ ] Melee hit detection: in VR it is layered (vanilla, hand-interaction, optional collision plugin, optional
      active-ragdoll plugin). Find out which layer the mod assumes, and check the layer's real range limit before
      assuming a longer weapon reaches further.
- [ ] Weapon reach: verify against the VR stack, not against SSE numbers. The engine's own melee range is capped.
- [ ] A weapon with extended collision geometry on the weapon layer routes projectile damage to its owner — see the
      `OL_WEAPON` section.

Detail: [vr-papyrus-and-input.md](vr-papyrus-and-input.md).

## Step 5 — UI and menus

- [ ] SkyUI dependency → needs the SkyUI VR fork specifically.
- [ ] Custom menus or widgets → the VR UI is reworked for controllers.
- [ ] MCM menus → must go through the VR fork's MCM.
- [ ] Book content → treated as a 2D HUD layer, and text scales with UI scaling.
- [ ] ImageSpace effects that were tuned for a flat screen → the seam-vs-UI trade-off is real.

Detail: [vr-differences.md](vr-differences.md).

## Step 6 — Animations

- [ ] OAR animations are fine (native VR support); DAR needs its VR fix or conversion to OAR.
- [ ] Any animation-motion framework: check its page for current VR support and the minimum version the mod needs —
      recorded status ages fast.
- [ ] Re-check the framework table's unresolved rows before promising a port (SCAR/BFCO, Precision).
- [ ] Animation priorities must be higher than the combat-animation frameworks' for the intended clip to play.

Detail: the framework table in [vr-differences.md](vr-differences.md).

## Step 7 — Records

Walk the plugin as text if a YAML round trip is available ([esp-yaml-and-spriggit.md](esp-yaml-and-spriggit.md)) and
check:

- [ ] Casting types consistent on every spell (all effects on a spell must match).
- [ ] ONAM subrecords present if the plugin is ESM-flagged.
- [ ] Light-plugin FormID range: `xx000800`-`xx000FFF` is the safe range; a header-1.71 plugin may sit below `0x800`,
      and VR has no native persistent-reference ESL support, so test such a plugin alone.
- [ ] VMAD properties: minimise them (`GetFormFromFile` on the mod's **own** forms), and check every lookup for `None`.
- [ ] Condition functions that gate reused vanilla records (they are what makes a reused effect fire on some targets).
- [ ] Sound records: a SOUN wrapper per playable SNDR, or the script gets `None` silently.
- [ ] Weapons: `BasicStats` vs `Data`, `AnimationType`, `WNAM` and the `EquipmentType` of a same-kind vanilla weapon.

Detail: [records-and-plugins.md](records-and-plugins.md).

## Step 8 — Build the port

1. Put any record changes in a **patch plugin in a new MO2 mod folder** — never inside the original author's mod folder,
   and never a bare copy into `Data/`.
2. Rewrite the incompatible scripts in that same new folder, with the `.pex` compiled from your `.psc` (skill
   `papyrus-compiler`).
3. Record what changed and why, one line per item above, so the next person can re-check it.
4. Test with the IK, hand-interaction and OpenXR stack the user actually runs. Only the user tests in game; report
   "built, NOT tested in game" and name what they must enable, regenerate or restart.

## The report to hand back

- **Compatible as-is** — items that work unchanged.
- **Needs patching** — what needs a script rewrite or a record patch, and in which new mod folder.
- **Incompatible** — what cannot work in VR, and any workaround, stated as a workaround.
- **Recommended tests** — the specific in-game scenarios the user must check, one line each, with what "passing" looks
  like.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
