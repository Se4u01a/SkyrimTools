# VR differences (nothing here applies to SE or AE)

Skyrim VR is a separate engine build. Everything in this file is VR-only unless a line says otherwise; on SE 1.5.97 or
AE none of it applies. The scripting and input half is [vr-papyrus-and-input.md](vr-papyrus-and-input.md); porting a
mod is [porting-to-vr.md](porting-to-vr.md).

## Engine foundation

- Skyrim VR is functionally based on SSE but is a **separate engine build** — not compatible with SE or Oldrim, and not
  addressed by SE/AE addresses.
- The record-library game mode for VR is `gmSSE=4`; there is no VR-specific mode.
- Its registry key is the **Skyrim Special Edition** one, not a VR key: tools that find the game through the registry
  work, and that is exactly why they can find the wrong install (troubleshooting skill, *conflicts and paths*).

## SKSE

- **SKSEVR is a completely separate build from SKSE64.** The address libraries differ entirely — thousands of addresses
  differ between SE and VR — so an SE plugin needs manual offset work before it can run on VR.
- CommonLibSSE-NG supports SE, AE and VR in a single multi-runtime build; that is the normal way to ship one DLL for
  all three. `skse-plugin-authoring` covers writing one.
- **The single biggest cause of VR mod breakage is a mod that requires SKSE64 and has no SKSEVR or multi-runtime
  build.** SKSE then refuses the DLL, silently, and the feature is simply absent.

## Animation and skeleton

- VR uses the same Havok Behaviour graph as SSE: `.hkx` files and Nemesis patches work.
- The critical difference: VR's "first person" **is the HMD's physical orientation**, not the game camera. `SetAngle`,
  `ForceThirdPerson` and `ForceFirstPerson` do not control the HMD view.
- `SetVehicle` desyncs the HMD: the game moves the player's position while the HMD anchor stays physically fixed.
- **Skeleton:** VR is extremely particular about skeleton structure. **Remove `PreWEAPON` and `PreSHIELD` nodes** (keep
  the vanilla skeleton) or expect CTDs: VR appears to do a text-contains search for WEAPON/SHIELD nodes and is confused
  by the `Pre*` prefixes. "XP32 First Person Skeleton CTD Bugfix" is critical for custom skeleton users.
- VRIK maps head and arms through an IK rig and displays a virtual body that follows the player.
- Animation replacers: OAR has native VR support and DAR animations are auto-converted to OAR format on load. Animation
  priorities must be higher than MCO/ADXP for the intended clip to play.

## Camera and UI

- The HMD position/rotation is the primary camera. A `PlayerCamera` exists but is subordinate to the VR camera, so
  standard SE camera interactions may not behave identically.
- `Game.ShakeCamera()` adds noise to the third-person camera node; in VR it is mostly inert (minor artifacts at best,
  nauseating at worst). It is generally safe to leave in.
- The UI is reworked for controllers: menu processing is limited to up/down/right/left controller signals.
- **SkyUI is incompatible; a SkyUI VR fork is required**, and MCM menus must go through that fork.
- Book content is treated as a 2D HUD layer; text scales with UI scaling.
- ImageSpace post-processing fights the UI in VR — see [engine-quirks.md](engine-quirks.md).

## Weather and INIs

- `Weather.SetActive()` transitions over ~2 s; `Weather.ForceActive(True)` snaps instantly. The snap is jarring in a
  headset but functional. Weather renders in full stereo.
- **Which INI Skyrim VR reads is not the generic order.** MEASURED on one install (2026-10-11/12, read back live after
  a relaunch): Skyrim VR did **not** read `Documents/My Games/Skyrim VR/Skyrim.ini` for `[Display]` sun-shadow
  settings — values written there were absent from the live value after a relaunch. Put user overrides in
  `SkyrimVR.ini` (or `SkyrimPrefs.ini`) and confirm each one live. "Skyrim.ini, then SkyrimVR.ini, then
  SkyrimPrefs.ini" does not by itself prove a key is read from a given file.
- Shadows that step "bit by bit" while standing still but move smoothly while walking come from
  `fSunStaticTimeUpdateScale:Display` (live VR default 0.10): `1.0` made the steps larger, `0` made them smooth. With
  `bDisableShadowJumps=1` the `fSunShadowUpdateTime`/`fSunUpdateThreshold` pair had no visible effect.
- **A frame-rate-driven plugin can differ between the headset and the desktop view.** A shadow-scaling plugin that
  holds a target FPS sat at its minimum distance while VR ran below the target, so distant shadows were missing in the
  headset and present in the mirror; setting minimum = maximum stopped it. Symptom "VR and desktop view differ": look
  for plugins that react to frame rate.
- Cloud shadows in a shader suite were invisible until a cubemap resolution went from 128 to 256, because the
  cloud-shadow texture is sized from it (MEASURED, one install, one version).

## Physics

- Havok is locked to **60 Hz by default** and was not updated for VR's 90 Hz requirement; an INI tweak raises the rate.
  Physics and logic tuned for 60 Hz can behave differently at 90.
- **Player collision differs:** SE is player capsule vs enemy capsule; VR is player capsule vs **enemy ragdoll**, and
  the player capsule is narrower than in the base game. This changes melee combat materially.

## VR playroom

- Scripts running in the VR playroom cause incompatibilities with some mods.
- A script-tweak plugin can pause non-playroom scripts until the player leaves the playroom.

## Runtime stack

- Skyrim VR ships with OpenVR (SteamVR) support. OpenComposite bypasses SteamVR and goes straight to OpenXR, which
  brings significant performance gains and lower CPU/GPU load — especially for a standalone headset via a streaming app.

## Frameworks: VR status as recorded

**Status claims age faster than anything else here. Verify on the mod page and in game.**

| Framework | VR status as recorded |
|---|---|
| SKSEVR | supported; a separate build from SKSE64 |
| Nemesis | works (behaviour patches are version-agnostic `.hkx`) |
| OAR (replacing DAR) | native VR support; DAR animations auto-convert |
| DAR (original) | the VR build has an `IsInCombat` offset bug — use a VR fix or switch to OAR |
| Animation Motion Revolution | recorded as VR-compatible after a CTD was fixed; the porting checklist says check the page for current support and the version a mod needs. Unresolved here. |
| Payload-style native payload mod | VR support declared since a 1.1.0 release via a VR Address Library |
| IFrame Generator RE | VR-compatible (CommonLibSSE-NG) |
| SCAR | the framework table records "a dedicated VR port exists (BFCO)"; the porting checklist corrects that BFCO is a separate mod, not a VR port of SCAR. **Sources disagree — check before relying on it.** |
| MCO/ADXP | works at the animation level in VR |
| True Directional Movement | no VR port; non-functional in VR (its script name does not even resolve — see [vr-papyrus-and-input.md](vr-papyrus-and-input.md)) |
| VRIK | VR-only; overrides skeleton IK from the controllers, and is the input API that works (see the VR scripting file) |
| Precision | the framework table records "works in VR via OAR versions"; the reach section records "Precision does not exist for VR — weapon collision is handled by HIGGS/VRIK". **Sources disagree; do not assume an SE/AE collision mod applies.** |
| HIGGS | VR-only; hand interaction and gravity gloves |
| Papyrus Extender | a community-maintained VR build exists (the original author has no headset); see the duplicate-native trap in the troubleshooting skill's *SKSE DLLs* |

## Common mod breakage categories, in order of frequency

1. **An SKSE dependency with no SKSEVR or multi-runtime port.**
2. **UI assumptions** — 2D menus and mouse input that VR does not have.
3. **Address or function offset mismatches** — SE addresses do not map to VR.
4. **Skeleton structure** — `PreWEAPON`/`PreSHIELD` nodes crash.
5. **Controller input paradigm** — keyboard/mouse mods do nothing.
6. **Frame-rate constraints** — physics and logic tuned for 60 Hz against a 90 Hz headset.
7. **ImageSpace and visual conflicts** — post-processing against UI rendering.
8. **Physics collision differences** — player ragdoll vs capsule.

## VR log locations

- Papyrus: `Documents/My Games/Skyrim VR/Logs/Script/Papyrus.<n>.log`.
- SKSE: `Documents/My Games/Skyrim VR/SKSE/sksevr.log` (the SE/AE equivalent is `skse64.log`).
- Crash logs: the same `SKSE` folder, written by whatever crash logger is installed. A machine can have all three
  folders at once and the wrong one reads perfectly — the troubleshooting skill's *conflicts and paths* reference has
  the rules.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
